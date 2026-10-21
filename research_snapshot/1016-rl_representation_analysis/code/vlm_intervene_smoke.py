from common import *
import numpy as np
from vlm_core import VOUT,raw_features
from vlm_intervene import Engine

def main():
    setup('vlm_repair/intervene_smoke');compatibility()
    import torch
    from worker import load_features
    from repair_engine import baseline_row
    from repair_score import score_group
    e=Engine();checks=[]
    with torch.no_grad():
        for row in read(ROOT/'repair_v1/anchors.json')[:2]:
            raw=raw_features(row);cached,_,_=load_features(row,e.cfg);start=time.monotonic();hidden=e.forward_native(raw);torch.cuda.synchronize();native_seconds=time.monotonic()-start
            assert torch.equal(hidden[0].cpu(),cached['last_hidden_state']);base=baseline_row(row)
            pred=e.trajectory(raw,hidden,seed(row['token']));assert np.array_equal(pred.cpu().numpy(),base['trajectory'])
            sites=[];started=time.monotonic()
            for block in list(e.prefix):
                hh,post=e.suffix(block,e.prefix[block]);assert torch.equal(hh,hidden),block
                if post is not None:assert torch.equal(e.trajectory(raw,hh,seed(row['token']),post),pred),block
                sites.append(block)
            torch.cuda.synchronize();suffix_seconds=time.monotonic()-started
            records=[dict(arm='baseline',trajectory=pred.cpu().numpy().tolist())];armchecks=[]
            for block in ['vision_12','bridge_1','language_12','language_norm','interface_post']:
                d=e.prefix[block].shape[-1];r=min(8,d);rng=np.random.default_rng(123);basis=np.linalg.qr(rng.standard_normal((d,r)))[0].astype('float32')
                fit={k:torch.tensor(v,device='cuda') for k,v in dict(basis=basis,center=np.zeros(d,dtype='float32'),mh=np.ones(r,dtype='float32'),mf=np.zeros(r,dtype='float32')).items()}
                group='patch_mean' if block.startswith(('vision','bridge')) else 'last8'
                arm=dict(block=block,group=group,method='mean',gate='none',alpha=.5,cap=.01)
                changed,stat=e.edited(arm,fit);assert float(stat[0]/stat[1])<=.0100001
                hh,post=e.suffix(block,changed);actual=e.trajectory(raw,hh,seed(row['token']),post)
                if block!='interface_post':
                    if block.startswith('vision'):module=e.model.vision_model.encoder.layers[int(block.split('_')[1])]
                    elif block.startswith('bridge'):module=e.model.mlp1[int(block.split('_')[1])]
                    elif block=='language_norm':module=e.model.language_model.model.norm
                    else:module=e.model.language_model.model.layers[int(block.split('_')[1])]
                    def replacement(module,args,output):return (changed,*output[1:]) if isinstance(output,tuple) else changed
                    handle=module.register_forward_hook(replacement)
                    try:full=e.model(**e.inputs).hidden_states[-1].float()
                    finally:handle.remove()
                    assert torch.equal(hh,full),block
                records.append(dict(arm=block,trajectory=actual.cpu().numpy().tolist()));armchecks.append(dict(block=block,actual_edit=stat.cpu().tolist(),suffix_matches_full=True))
            scored=score_group(dict(metric_cache=row['metric_cache'],metric_sha256=base['metric_sha256'],scoring=e.cfg['scoring'],records=records));assert scored[0]['score']==base['score']
            e.verify_engine();checks.append(dict(token=row['token'],prefix_sites=sites,all_zero_suffix_exact=True,cache_exact=True,baseline_score_exact=True,native_seconds=native_seconds,all_suffix_seconds=suffix_seconds,nonzero_checks=armchecks,scored=scored))
            print(json.dumps(dict(status='ANCHOR_PASS',token=row['token'],sites=len(sites),seconds=native_seconds,suffix_seconds=suffix_seconds)),flush=True)
    atomic(VOUT/'INTERVENTION_ENGINEERING.json',dict(status='PASS',time=stamp(),checks=checks,code_sha256=sha(ROOT/'code/vlm_intervene.py')))
if __name__=='__main__':main()
