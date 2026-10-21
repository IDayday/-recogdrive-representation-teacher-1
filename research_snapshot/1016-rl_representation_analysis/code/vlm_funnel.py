"""Rolling frozen per-block development, exploration-only fits, append-only repair screens."""
from common import *
import argparse
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic
RUN='vlm_repair_20261016_v2'

def fit_work(spec):
    from threadpoolctl import threadpool_limits
    from vlm_fits import make
    from vlm_selection import confirm
    with threadpool_limits(limits=2):
        fit=make(spec);confirmation=confirm(fit)
    return fit,confirmation

def panel():
    rows=[r for r in read(ROOT/'manifests/natural_s0.json') if r['subset']=='exploration'];chosen=[]
    for label,n in [('failure',16),('high_quality',8),('intermediate',8)]:
        group=sorted([r for r in rows if r['quality']==label],key=lambda r:digest(dict(token=r['token'],vlm_coarse_root=20261016)))
        used=set();take=[]
        for r in group:
            if r['session'] in used:continue
            take.append(r);used.add(r['session'])
            if len(take)==n:break
        assert len(take)==n;chosen.extend(take)
    assert len({r['token'] for r in chosen})==32;return chosen

def arms(fit):
    result=[]
    methods=['mean','contract','remove','ot','quality','local','project','soft_clip','support_projection','qda_gradient']
    if fit['r']>1024:methods=['mean','contract','quality','project','soft_clip']
    for method in methods:
        for alpha in [.1,.25,.5,1.]:
            for cap in [.005,.01,.025,.05,.1]:
                a=dict(fit_path=fit['path'],fit_sha256=fit['sha256'],fit_id=fit['id'],block=fit['block'],group=fit['group'],method=method,alpha=alpha,cap=cap,gate='none',config=fit['config'],centering=fit['centering'],r=fit['r'])
                a['id']='vr_'+digest(a)[:18];result.append(a)
    return result

def main():
    setup('vlm_repair/funnel');from vlm_selection import block_candidates
    from vlm_repair_queue_v2 import stage
    folder=VOUT/'development';folder.mkdir(exist_ok=True);base=ROOT/'runs'/RUN
    panel_path=folder/'COARSE_PANEL.json'
    if not panel_path.exists():atomic(panel_path,panel())
    rows=read(panel_path);blocks=[b['name'] for b in read(VOUT/'PIVOT_PLAN.json')['blocks']];pending={};submitted=set();frozen={}
    with ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn')) as pool:
        while True:
            failures=list((VOUT/'failures').glob('*.json'))+list((VOUT/'early_interface/failures').glob('*.json'))
            if failures:raise RuntimeError('Original failure '+str(failures[0]))
            for block in sorted(blocks,key=lambda n:n!='interface_post'):
                selection_path=folder/(block+'.json')
                if block not in frozen:
                    if selection_path.exists():frozen[block]=read(selection_path)
                    else:
                        choice=block_candidates(block,VOUT/'early_interface','scan',['scan']) if block=='interface_post' else block_candidates(block)
                        if choice is None:continue
                        atomic(selection_path,choice);frozen[block]=choice
                        print(json.dumps(dict(event='BLOCK_FROZEN',block=block,selected=len(choice['selected']))),flush=True)
                for selected in frozen[block]['selected']:
                    key=digest(selected)[:20]
                    if key in submitted:continue
                    pending[pool.submit(fit_work,selected)]=(key,selected);submitted.add(key)
            for future,(key,spec) in list(pending.items()):
                if not future.done():continue
                del pending[future]
                try:fit,confirmation=future.result()
                except AssertionError as error:
                    atomic(folder/'rejected_fits'/(key+'.json'),dict(status='INELIGIBLE_REFIT',time=stamp(),spec=spec,reason=repr(error)));continue
                dest=folder/'completed_fits'/(fit['id']+'.json')
                if not dest.exists():atomic(dest,dict(fit=fit,confirmation=confirmation))
                name='coarse_'+fit['id'];protocol=base/'stages'/name/'PROTOCOL.json'
                if not protocol.exists():
                    if not (VOUT/'INTERVENTION_OPERATORS_V2_PASS.json').exists():
                        atomic(folder/'FIRST_FIT_READY.json',fit);continue
                    count=stage(base,name,rows,arms(fit),[0],chunk=2,arm_chunk=64)
                    print(json.dumps(dict(event='COARSE_APPENDED',fit=fit['id'],block=fit['block'],r=fit['r'],arms=len(arms(fit)),tasks=count)),flush=True)
            # Fits completed before the operator smoke are appended after the gate opens.
            if (VOUT/'INTERVENTION_OPERATORS_V2_PASS.json').exists():
                for p in sorted((folder/'completed_fits').glob('*.json')):
                    fit=read(p)['fit'];name='coarse_'+fit['id']
                    if not (base/'stages'/name/'PROTOCOL.json').exists():
                        count=stage(base,name,rows,arms(fit),[0],chunk=2,arm_chunk=64);print(json.dumps(dict(event='COARSE_APPENDED',fit=fit['id'],block=fit['block'],r=fit['r'],arms=len(arms(fit)),tasks=count)),flush=True)
            status=dict(status='DEVELOPING',time=stamp(),blocks_frozen=len(frozen),blocks_total=len(blocks),pending_fits=len(pending),fits_completed=len(list((folder/'completed_fits').glob('*.json'))),coarse_stages=len(list((base/'stages').glob('coarse_*/PROTOCOL.json'))))
            atomic(folder/'STATUS.json',status)
            if len(frozen)==len(blocks) and not pending and (VOUT/'INTERVENTION_OPERATORS_V2_PASS.json').exists():break
            time.sleep(5)
    atomic(folder/'ALL_COARSE_APPENDED.json',dict(status='PASS',time=stamp(),blocks=len(frozen),fits=status['fits_completed'],stages=status['coarse_stages']))
if __name__=='__main__':main()
