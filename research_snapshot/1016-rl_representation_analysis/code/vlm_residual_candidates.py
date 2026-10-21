"""Preserve both residual constructions and equal/unequal main-space controls as they finish."""
from common import *
import numpy as np
from vlm_core import VOUT
from vlm_selection import score,neighbor_indices,finite
from vlm_fits import make
from vlm_results import summarize
from vlm_funnel import arms,fit_work
from vlm_replay import choose
from vlm_repair_queue_v2 import stage
from repair_queue_v2 import atomic_unique as atomic

RUN='vlm_repair_20261016_v2'

def select(block,source):
    folder=source/'scan/results';entries=read(source/'scan/CONFIGS.json');records=[]
    paths=list(folder.glob(block+'__*.json'))
    for path in paths:
        r=read(path)
        if r['status']!='COMPLETE':continue
        with np.load(ROOT/r['array_path']) as data:matrix=np.array(data['metrics'])
        result_hash=sha(path)
        for rec in r['shortlisted']:
            if rec['config']['kind'] not in ['basis_residual','variance_residual'] or rec['cutoff_degenerate_any'] or rec['metrics']['auc'] is None:continue
            cc=int(rec['centering']=='pooled_centered');near=neighbor_indices(rec['config'],entries);values=matrix[cc,5,near,0];values=values[np.isfinite(values)];supported=int((values>=max(.55,rec['metrics']['auc']-.03)).sum())
            stable=finite(rec['auc_fold_min'])>.55 and finite(rec['metrics']['session_positive_fraction'])>=.65 and supported>=1 and all(finite(n['metrics']['auc'])>.55 for n in rec.get('other_sampling_seeds',[]))
            records.append(dict(rec,cell=r['cell'],block=block,group=r['cell'].split('__')[1],analysis_source='scan',source_result_sha256=result_hash,moment=dict(path=r['moment_path'],sha256=r['moment_sha256']),cell_proof_path=str((source/'cells'/(r['cell']+'.json')).relative_to(ROOT)),neighbor_supported=supported,neighbor_tested=len(values),neighbor_auc=values.tolist(),stable_cv_region=stable,rank_band='residual_family_supplement'))
    result=[]
    for kind in ['basis_residual','variance_residual']:
        for equal in [True,False]:
            group=[r for r in records if r['config']['kind']==kind and r['config']['equal']==equal]
            if group:result.append(max(group,key=lambda r:(r['stable_cv_region'],score(r),r['neighbor_supported'])))
    return result

def main():
    setup('vlm_repair/residual_supplement');from threadpoolctl import threadpool_limits
    base=ROOT/'runs'/RUN;folder=VOUT/'residual_development';folder.mkdir(exist_ok=True);done=set()
    blocks=[b['name'] for b in read(VOUT/'PIVOT_PLAN.json')['blocks']];coarse=read(VOUT/'development/COARSE_PANEL.json');replay=read(VOUT/'replay/PANEL.json')
    while True:
        for block in sorted(blocks,key=lambda b:b!='interface_post'):
            lock=folder/(block+'.json')
            if not lock.exists():
                source=VOUT/'early_interface' if block=='interface_post' else VOUT
                canonical=block+'__'+('patch_mean' if block.startswith(('vision','bridge')) else 'valid_mean')
                if block!='interface_post' and not (source/'scan/receipts'/(canonical+'.json')).exists():continue
                selected=select(block,source)
                primary=read(VOUT/'development'/(block+'.json'))['selected'] if (VOUT/'development'/(block+'.json')).exists() else []
                selected=[r for r in selected if not any(r['cell']==p['cell'] and r['config']==p['config'] and r['centering']==p['centering'] for p in primary)]
                atomic(lock,dict(status='FROZEN',time=stamp(),block=block,selected=selected,source_root=str(source.relative_to(ROOT)),coverage='all completed full-grid regions at this prospective block cutoff; target remainder explicitly pending',family_holm_maximum=1000))
            selection=read(lock)
            for spec in selection['selected']:
                with threadpool_limits(limits=2):fit,confirmation=fit_work(spec)
                completed=folder/'fits'/(fit['id']+'.json')
                if not completed.exists():atomic(completed,dict(fit=fit,confirmation=confirmation))
                name='coarse_'+fit['id']
                if not (base/'stages'/name/'PROTOCOL.json').exists():stage(base,name,coarse,arms(fit),[0],chunk=2,arm_chunk=64);print('RESIDUAL_COARSE_APPENDED',block,fit['id'],flush=True)
            if block in done:continue
            summaries=[]
            for spec in selection['selected']:
                ident=digest(spec)[:20];r=summarize(base,'coarse_'+ident)
                if r is None:break
                summaries.append(r)
            if len(summaries)!=len(selection['selected']):continue
            name='replay_residual_'+block
            if summaries and not (base/'stages'/name/'PROTOCOL.json').exists():
                candidates=choose(summaries);stage(base,name,replay,candidates,[0],chunk=4,arm_chunk=64);print('RESIDUAL_REPLAY_APPENDED',block,len(candidates),flush=True)
            done.add(block)
        atomic(folder/'STATUS.json',dict(status='RUNNING',time=stamp(),blocks_with_frozen_residual_selection=len(list(folder.glob('*.json')))-1,blocks_replayed=len(done),targets=len(blocks)))
        if len(done)==len(blocks):break
        time.sleep(30)
if __name__=='__main__':main()
