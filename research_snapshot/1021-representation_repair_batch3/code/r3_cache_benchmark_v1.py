"""Independent short exact-output benchmark; frozen workers keep computing."""
from r3_common import *
import argparse
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import socket
import traceback


def main(a):
    setup('cache_benchmark_v1/'+a.node);compatibility()
    import numpy as np
    import torch
    from vlm_intervene_v4 import Engine
    from vlm_core import raw_features
    from repair_engine import baseline_row
    from repair_score import score_group
    from r3_runtime import prediction,init_scorer
    from r3_first42_rollout_v2 import FitBank
    from r3_inference_cache_v1 import constant_context
    node=next(n for n in read(ROOT/'resources/REGISTRY.json')['nodes'] if n['name']==a.node);assert socket.gethostname().startswith(node['job']+'-')
    free,total=torch.cuda.mem_get_info();assert free>32*(1<<30),dict(free=free,total=total)
    output=ROOT/'runs/cache_benchmark_v1'/a.node;assert not (output/'PASS.json').exists();atomic(output/'LIVE.json',dict(status='LOADING_MODEL',time=stamp(),pid=os.getpid(),device=os.environ.get('CUDA_VISIBLE_DEVICES'),free_bytes=free))
    engine=Engine();bank=FitBank();rows=read(BATCH1/'manifests/natural_s0.json');pack=read(ROOT/'manifests/first42_v1.json');candidates=[pack['entries'][i] for i in [0,1,8,13]];checks=[];records=[]
    with ProcessPoolExecutor(max_workers=2,mp_context=mp.get_context('spawn'),initializer=init_scorer) as pool:
        for index in [60,1]:
            row=rows[index];features=raw_features(row);reference=baseline_row(row);golden=read(ROOT/'runs/first42_engineering_v2/cases'/row['token']/'RESULT.json');expected={(v['arm'],v['seed_index']):v for v in golden['records']}
            with torch.no_grad():
                hidden=engine.forward_native(features);mask=engine.inputs['attention_mask'][0].bool()
                for entry in candidates:
                    if entry['kind']=='Base':condition,post=hidden,None
                    else:
                        changed,statistics=engine.edited(entry['arm'],bank.get(entry['root'],entry['arm']));condition,post=engine.suffix(entry['arm']['block'],changed)
                    reference_values=[];reference_interfaces=[];times={};counters={}
                    for mode in ['original','verified_cache','cached']:
                        torch.cuda.synchronize();start=time.monotonic();values=[];interfaces=[]
                        def calls():
                            for j in range(5):
                                trajectory,interface=prediction(engine,features,condition,j,row['token'],post);values.append(trajectory);interfaces.append(interface)
                        if mode=='original':calls()
                        else:
                            with constant_context(engine,verify=mode=='verified_cache') as stat:calls()
                            counters[mode]=dict(stat)
                        torch.cuda.synchronize();times[mode]=time.monotonic()-start
                        if mode=='original':reference_values=values;reference_interfaces=interfaces
                        for j,(trajectory,interface) in enumerate(zip(values,interfaces)):
                            assert torch.equal(trajectory,reference_values[j]) and torch.equal(interface,reference_interfaces[j])
                            assert trajectory.cpu().numpy().tolist()==expected[entry['id'],j]['trajectory']
                            arr=interface[0,mask].cpu().numpy();assert hashlib.sha256(arr.tobytes()).hexdigest()==expected[entry['id'],j]['interface_sha256']
                            if mode=='cached':records.append(dict(arm=entry['id'],seed_index=j,trajectory=trajectory.cpu().numpy().tolist()))
                    checks.append(dict(token=row['token'],arm=entry['id'],timing=times,counters=counters,all_trajectories_and_same_forward_interfaces_bit_exact=True))
            current=records[-len(candidates)*5:];scored=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=current)).result(timeout=1800)
            for record in scored:assert record['score']==expected[record['arm'],record['seed_index']]['score']
            engine.verify_engine();atomic(output/'LIVE.json',dict(status='CASE_COMPLETE',time=stamp(),cases=index,pid=os.getpid()))
    normal=sum(v['timing']['original'] for v in checks);cached=sum(v['timing']['cached'] for v in checks)
    proof=dict(status='PASS_SMALL_BENCHMARK_NOT_MULTIDEVICE_ADMISSION',time=stamp(),checks=checks,head_time_speedup=normal/cached,
               checkpoints_and_RNG_unchanged=True,frozen_formal_first42_run_unchanged=True,source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'code/r3_inference_cache_v1.py'))
    atomic(output/'PASS.json',proof);print(json.dumps(dict(status=proof['status'],head_time_speedup=normal/cached)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);a=p.parse_args()
    try:main(a)
    except BaseException as error:
        atomic(ROOT/'runs/cache_benchmark_v1'/a.node/'FAILED.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise
