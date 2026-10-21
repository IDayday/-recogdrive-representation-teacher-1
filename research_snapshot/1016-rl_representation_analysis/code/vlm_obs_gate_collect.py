"""Only locked gate-site test features; prefetch CPU input beside native GPU work."""
from common import *
import numpy as np
import traceback
from concurrent.futures import ThreadPoolExecutor
from vlm_core import VOUT,raw_features,VISION_GROUPS,LANGUAGE_GROUPS
from vlm_intervene_v4 import Engine
from vlm_repair_queue_v6 import Fits
from vlm_obs_qda_gate import OUT,quadratic
from vlm_obs_gate_policy import test_lock
from vlm_scan import metadata,save_npz
from repair_queue_v2 import atomic_unique as atomic


def pools(engine,cells):
    """Use the complete original pooling GEMM, preserving native rounding."""
    import torch
    values=[];lengths=[]
    for cell in cells:
        block,group=cell.split('__',1)
        matrix,valid=engine.vm if block.startswith('vision') else engine.bm if block.startswith('bridge') else engine.lm
        groups=VISION_GROUPS if block.startswith(('vision','bridge')) else LANGUAGE_GROUPS
        h=engine.prefix[block];all_values=matrix@h.reshape(-1,h.shape[-1]).float()
        all_values[~valid]=float('nan');v=all_values[groups.index(group)];values.append(v);lengths.append(len(v))
    # One small device return for all requested sites.
    combined=torch.cat(values).cpu().numpy();result={};begin=0
    for cell,n in zip(cells,lengths):result[cell]=combined[begin:begin+n].copy();begin+=n
    return result


def engineering(engine,locked,cells):
    import torch
    from repair_engine import baseline_row
    from repair_score import score_group
    marker=OUT/'FEATURE_ENGINEERING_PASS.json'
    if marker.exists():return read(marker)
    rows,q,exp,fold,sessions,high=metadata();index={r['token']:i for i,r in enumerate(rows)}
    chosen=read(ROOT/'repair_v1/anchors.json')[:2];known={r['token'] for r in chosen}
    with np.load(ROOT/read(OUT/'RISKS_READY.json')['path']) as z:
        for role in locked['roles'].values():
            risk=z['risk'][:,role['gate']['column']]
            for mask,largest in [(exp,True),(exp&(q>.9)&(risk<=role['gate']['threshold']),False)]:
                at=np.flatnonzero(mask);assert len(at)
                i=int(at[np.argmax(risk[at])] if largest else at[0])
                if rows[i]['token'] not in known:chosen.append(rows[i]);known.add(rows[i]['token'])
    fits=Fits();checks=[]
    cached={cell:np.load(ROOT/read(VOUT/'cells'/(cell+'.json'))['path'],mmap_mode='r') for cell in cells}
    with torch.no_grad():
        for row in chosen:
            features=raw_features(row);hidden=engine.forward_native(features);value=pools(engine,cells)
            for cell in cells:assert np.array_equal(value[cell],cached[cell][index[row['token']]]),cell
            before=baseline_row(row);base=engine.trajectory(features,hidden,seed(row['token']))
            assert np.array_equal(base.cpu().numpy(),before['trajectory'])
            records=[dict(arm='baseline',trajectory=base.cpu().numpy().tolist())];decisions=[]
            for policy in {r['id']:r for r in locked['roles'].values()}.values():
                gate=policy['gate'];risk=float(quadratic(value[gate['fit']['cell']][None,:],gate['fit'])[0]);active=np.isfinite(risk) and risk>gate['threshold'];arm=policy['parent']
                if arm['method']=='combination':condition,post,stat=engine.combined(arm['parts'],fits.get)
                else:edited,stat=engine.edited(arm,fits.get(arm));condition,post=engine.suffix(arm['block'],edited)
                prediction=engine.trajectory(features,condition,seed(row['token']),post)
                repeat=engine.trajectory(features,condition,seed(row['token']),post);assert torch.equal(prediction,repeat)
                assert float(stat[0]/stat[1].clamp(min=1e-12))<=arm['cap']+1e-6
                final=prediction if active else base
                records.append(dict(arm=policy['id'],trajectory=final.cpu().numpy().tolist()))
                decisions.append(dict(id=policy['id'],risk=risk,threshold=gate['threshold'],active=bool(active)))
            scored=score_group(dict(metric_cache=row['metric_cache'],metric_sha256=before['metric_sha256'],scoring=engine.cfg['scoring'],records=records))
            assert scored[0]['score']==before['score'];engine.verify_engine()
            checks.append(dict(token=row['token'],pooled_features_bit_exact_existing_training_cache=True,decisions=decisions,records=scored))
    assert any(d['active'] for c in checks for d in c['decisions'])
    assert any(not d['active'] for c in checks for d in c['decisions'])
    result=dict(status='PASS',time=stamp(),actual_checks=checks,both_gate_branches_exercised=True,
        trajectories_repeat_exact=True,old_RL_Base_trajectory_and_scores_exact=True,no_test_access=True)
    atomic(marker,result);return result


def read_input(row):
    started=time.monotonic();x=raw_features(row);return x,time.monotonic()-started


def main():
    setup('vlm_repair/obs_gate_collect');compatibility();OUT.mkdir(exist_ok=True)
    while not (OUT/'FINAL_LOCK.json').exists():
        if (OUT/'NO_COMPETITIVE_CANDIDATES.json').exists():return
        time.sleep(30)
    test_lock()
    import torch,psutil
    assert torch.cuda.device_count()==1 and psutil.virtual_memory().available>8*1024**3
    for p,h in read(VOUT/'OBS_QDA_GATE_COLLECT_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    dest=OUT/'test_features';dest.mkdir(exist_ok=True)
    atomic(dest/'PREFLIGHT.json',dict(status='PASS',time=stamp(),devices=1,
        device_name=torch.cuda.get_device_name(0),device_memory=torch.cuda.get_device_properties(0).total_memory,
        available_host_memory=psutil.virtual_memory().available,checkpoint=read(ROOT/'configs/baseline.json')['checkpoint']))
    locked=read(OUT/'FINAL_LOCK.json');cells=sorted({r['gate']['fit']['cell'] for r in locked['roles'].values()})
    assert 1<=len(cells)<=2;engine=Engine();engineering(engine,locked,cells)
    # Test observations are first read here, after the own gate/parent lock.
    rows=read(ROOT/'candidate_repair_v1/analysis/final_test/rows.json');assert len(rows)==12146
    protocol=dest/'PROTOCOL.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN_BEFORE_TEST_FEATURE_COLLECTION',time=stamp(),
        cells=cells,cases=len(rows),chunk=16,source_lock_sha256=sha(OUT/'FINAL_LOCK.json'),rows_sha256=digest(rows),
        natural_observation_only=True,no_test_labels_or_GT_for_risk=True))
    assert read(protocol)['source_lock_sha256']==sha(OUT/'FINAL_LOCK.json')
    with torch.no_grad(),ThreadPoolExecutor(max_workers=1) as reader:
        for begin in range(0,len(rows),16):
            receipt=dest/'receipts'/f'{begin:06d}.json'
            if receipt.exists():continue
            batch=rows[begin:begin+16];values=[];timing=dict(read_decode_cpu_seconds=0.,input_wait_seconds=0.,native_forward_wall_seconds=0.,device_return_wall_seconds=0.)
            future=reader.submit(read_input,batch[0])
            for i,row in enumerate(batch):
                t=time.monotonic();features,read_seconds=future.result();timing['input_wait_seconds']+=time.monotonic()-t;timing['read_decode_cpu_seconds']+=read_seconds
                if i+1<len(batch):future=reader.submit(read_input,batch[i+1])
                t=time.monotonic();engine.forward_native(features);timing['native_forward_wall_seconds']+=time.monotonic()-t
                t=time.monotonic();values.append(pools(engine,cells));timing['device_return_wall_seconds']+=time.monotonic()-t;engine.verify_engine()
            path=dest/'arrays'/f'{begin:06d}.npz';t=time.monotonic()
            hashed=save_npz(path,**{c:np.stack([v[c] for v in values]) for c in cells},test_indices=np.arange(begin,begin+len(batch)))
            timing['write_seconds']=time.monotonic()-t
            atomic(receipt,dict(status='COMPLETE',time=stamp(),begin=begin,end=begin+len(batch),tokens=[r['token'] for r in batch],path=str(path.relative_to(ROOT)),sha256=hashed,timing=timing))
            print('OBS_GATE_FEATURE_BATCH',begin+len(batch),len(rows),flush=True)
    assert len(list((dest/'receipts').glob('*.json')))==760
    atomic(dest/'COLLECTION_COMPLETE.json',dict(status='PASS',time=stamp(),cases=len(rows),cells=cells,
        source_lock_sha256=sha(OUT/'FINAL_LOCK.json'),source_protocol_sha256=sha(protocol),chunks=760))


if __name__=='__main__':
    try:main()
    except BaseException as exc:
        atomic(OUT/'failures/feature_collect.json',dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()));raise
