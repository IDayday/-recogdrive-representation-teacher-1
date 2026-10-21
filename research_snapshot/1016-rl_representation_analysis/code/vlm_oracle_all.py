"""Incremental all-method bounds; evaluated populations and true seed IDs never mix."""
from common import *
import numpy as np
from repair_oracle_inventory_v2 import category
from repair_oracle_extended import detail
from repair_queue_v2 import atomic_unique as atomic
from vlm_core import VOUT
OUT=VOUT/'oracle_all'

def sources():
    for root in ['repair_v1/analysis','candidate_repair_v1/analysis','vlm_repair_v1/analysis']:
        for path in sorted((ROOT/root).glob('*/scores.npy')):
            folder=path.parent
            if not (folder/'SUMMARY.json').exists():continue
            summary=read(folder/'SUMMARY.json');assert summary['status']=='COMPLETE'
            rows=read(folder/'rows.json');arms=read(folder/'arms.json');seeds=summary['protocol']['seeds']
            yield dict(id=folder.parent.parent.name+'__'+folder.name,path=path,rows=rows,arms=arms,seeds=seeds,
                scope='Actually executed policy with its internal gate; enriched panel means are not population PDMS.')
    acceptance=VOUT/'legacy_ungated_test/ACCEPTANCE.json'
    if acceptance.exists():
        d=read(acceptance);folder=ROOT/'candidate_repair_v1/analysis/final_test'
        yield dict(id='legacy_ungated_test__failure_gated',path=VOUT/'legacy_ungated_test/failure_gated_scores.npy',rows=read(folder/'rows.json'),arms=[x['arm'] for x in d['methods']],seeds=[0,1,2,3,4],
            scope='Only Base-failed outputs actually inferred; every nonfailure was exactly retained Base. This is an external-failure-gated policy, not unconditional ungated inference.')

def derive(source):
    path=source['path'];score_sha=sha(path);target=OUT/'panels'/(source['id']+'.json')
    if target.exists():
        old=read(target);assert old['scores_sha256']==score_sha;return old
    scores=np.load(path,mmap_mode='r');rows=source['rows'];arms=source['arms'];seeds=source['seeds'];assert scores.shape==(len(seeds),len(rows),len(arms)+1,7)
    base=np.asarray(scores[:,:,0,:]);failed=base[:,:,0]<.7;records=[];best=base.copy();all_best=base.copy()
    for i,a in enumerate(arms,1):
        value=np.asarray(scores[:,:,i,:]);positive=value[:,:,0]>base[:,:,0]
        fg=np.where(failed[:,:,None],value,base);benefit=np.where(positive[:,:,None],value,base);fb=np.where((failed&positive)[:,:,None],value,base)
        records.append(dict(arm=a,category=category(a),internal_gate=a.get('gate',a.get('legacy_arm',{}).get('gate','none')),
            actual=detail(value,base,rows),external_failure_only=detail(fg,base,rows),external_benefit_only=detail(benefit,base,rows),external_failure_and_benefit=detail(fb,base,rows)))
        use=value[:,:,0]>all_best[:,:,0];all_best[use]=value[use]
        if category(a)=='repair':
            use=value[:,:,0]>best[:,:,0];best[use]=value[use]
    result=dict(status='PASS',time=stamp(),id=source['id'],scope=source['scope'],source_path=str(path.relative_to(ROOT)),scores_sha256=score_sha,
        rows_sha256=digest(rows),arms_sha256=digest(arms),seeds=seeds,cases=len(rows),methods=records,
        genuine_plus_base=detail(best,base,rows,ci=True),failure_only_genuine_plus_base=detail(np.where(failed[:,:,None],best,base),base,rows,ci=True),
        all_computed_including_null_and_gt_plus_base=detail(all_best,base,rows,ci=True),
        single_seed_stability_is_not_repeat_sampling_stability=len(seeds)==1,positive_score_ties_retain_base_or_first=True)
    atomic(target,result);return result

def merge(sources):
    compatible={}
    for source in sources:
        if len(source['rows']) not in [12146,17475,103288] or len(source['seeds'])<3:continue
        a=np.load(source['path'],mmap_mode='r');base=np.asarray(a[:,:,0,:]);key=digest(dict(tokens=[r['token'] for r in source['rows']],seeds=source['seeds'],baseline_all7_sha=hashlib.sha256(base.tobytes()).hexdigest()))
        compatible.setdefault(key,[]).append(source)
    output=[]
    for key,group in compatible.items():
        first=group[0];base=np.asarray(np.load(first['path'],mmap_mode='r')[:,:,0,:]);best=base.copy();methods=[];hashes=set();seen_ids={}
        for source in group:
            scores=np.load(source['path'],mmap_mode='r');assert np.array_equal(scores[:,:,0,:],base) and source['seeds']==first['seeds']
            for i,a in enumerate(source['arms'],1):
                if category(a)!='repair':continue
                value=np.asarray(scores[:,:,i,:]);hashed=hashlib.sha256(value.tobytes()).hexdigest()
                if a['id'] in seen_ids:assert seen_ids[a['id']]==hashed
                seen_ids[a['id']]=hashed
                methods.append(dict(id=a['id'],panel=source['id'],source_scope=source['scope'],score_functional_duplicate=hashed in hashes));hashes.add(hashed)
                use=value[:,:,0]>best[:,:,0];best[use]=value[use]
        failed=base[:,:,0]<.7
        output.append(dict(id=key,cases=len(first['rows']),seeds=first['seeds'],panels=[s['id'] for s in group],methods=methods,distinct_score_functions=len(hashes),
            all_case=detail(best,base,first['rows'],ci=True),failure_only=detail(np.where(failed[:,:,None],best,base),base,first['rows'],ci=True),
            baseline_all_seven_fields_and_seed_ids_exact=True,no_uncomputed_ungated_success_output_invented=True))
    return output

def main():
    setup('vlm_repair/oracle_all');inputs=list(sources());panels=[]
    for source in inputs:
        result=derive(source);panels.append(dict(id=source['id'],path=str((OUT/'panels'/(source['id']+'.json')).relative_to(ROOT)),cases=result['cases'],seeds=result['seeds'],methods=len(result['methods'])))
        print('ORACLE_PANEL_VERIFIED',source['id'],flush=True)
    snapshot=OUT/'snapshots'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')
    result=dict(status='PASS',time=stamp(),panels=panels,compatible_merged_pools=merge(inputs),
        scope='Every completed actual score matrix at snapshot time. Same policy repeated noise is not independent training. Oracle uses privileged labels/outcomes and is not deployable.',
        pending_vlm_does_not_imply_complete=True,code_sha256=sha(Path(__file__)))
    atomic(snapshot/'INDEX.json',result);atomic(OUT/'LATEST.json',dict(path=str((snapshot/'INDEX.json').relative_to(ROOT)),time=stamp()))
    print('ALL_METHOD_ORACLE_SNAPSHOT_PASS',len(inputs),str(snapshot.relative_to(ROOT)),flush=True)

if __name__=='__main__':main()
