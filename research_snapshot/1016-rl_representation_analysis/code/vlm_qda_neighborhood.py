"""Prospective neighboring-rank repair spaces, selected from cached CV only."""
from common import *
import numpy as np
from vlm_core import VOUT
from vlm_scan import metadata,metric_dict
from vlm_space import metrics
from vlm_selection import finite
from repair_queue_v2 import atomic_unique as atomic

DEST=VOUT/'late_token_coverage'


def select():
    path=DEST/'QDA_SELECTION_LOCK.json'
    if path.exists():return read(path)
    protocol=read(VOUT/'LATE_TOKEN_COVERAGE_PROTOCOL_v3.json')
    rows,q,exp,fold,sessions,high=metadata()
    base=np.load(ROOT/'candidate_repair_v1/analysis/navtrain_full_locked/scores.npy',mmap_mode='r')[:,:,0,0]
    assert np.array_equal(base[0],q)
    selected=[];records=[]
    for site in read(VOUT/'qda_controls/PROTOCOL.json')['sites']:
        parent=site['fit'];cell=parent['cell'];result=read(VOUT/'qda_controls/results'/(cell+'.json'))
        assert sha(ROOT/result['array_path'])==result['array_sha256']
        with np.load(ROOT/result['array_path']) as z:
            indices=np.array(z['evaluation_indices']);oof=np.array(z['oof']);fm=np.array(z['fold_metrics'])
        pca=[(i,r) for i,r in enumerate(result['records']) if r['config']['kind']=='success_pca']
        population=parent['class_sizes'][0]
        sw=np.where(q[indices]<.7,1.,population/max(int((q[indices]>.9).sum()),1))
        for pos,(i,record) in enumerate(pca):
            rank=record['config']['r']
            if rank not in protocol['qda_neighborhood']['ranks']:continue
            noise=[]
            for j in [1,2]:
                keep=(base[j,indices]<.7)|(base[j,indices]>.9)
                values=metrics(oof[keep,i],base[j,indices[keep]]<.7,sessions[indices[keep]],sample_weight=sw[keep])[0]
                noise.append(dict(seed_index=j,metrics=metric_dict(values)))
            near=[pca[j][1]['cv']['auc'] for j in [pos-1,pos+1] if 0<=j<len(pca)]
            # Endpoints have one immediate neighbor; include the second inward
            # neighbor so every retained dimension has two prespecified checks.
            if len(near)<2:near.append(pca[2 if pos==0 else -3][1]['cv']['auc'])
            m=record['cv'];supported=sum(v>=max(.55,m['auc']-.03) for v in near)
            ok=(finite(m['auc'])>=.60 and finite(m['standardized_gap'])>=.20
                and finite(m['weighted_ap'])>finite(m['class_prevalence'])
                and record['cv_fold_min']>.55 and finite(m['session_positive_fraction'])>=.65
                and all(finite(n['metrics']['auc'])>.55 for n in noise) and supported>=2)
            records.append(dict(cell=cell,r=rank,eligible=ok,cv=m,other_sampling_seeds=noise,neighbor_auc=near))
            if not ok:continue
            source=read(VOUT/'rapid/results'/(cell+'.json'))
            spec=dict(cell=cell,block=parent['block'],group=parent['group'],
                config=dict(kind='success_pca',r=rank,ks=None,kf=None,equal=None,replicate=None),
                centering=parent['centering'],metrics=m,auc_fold_min=record['cv_fold_min'],
                auc_fold_std=float(np.std(fm[:,i,0])),other_sampling_seeds=noise,
                source_result_sha256=sha(VOUT/'qda_controls/results'/(cell+'.json')),
                moment=dict(path=source['moment_path'],sha256=source['moment_sha256']),
                cell_proof_path=parent['cell_proof_path'],analysis_source='cached_quadratic_cv',
                stable_cv_region=True,neighbor_supported=supported,neighbor_auc=near,
                selection_readout='fixed_5_percent_shrink_QDA',
                existing_qda_confirmation_id=record['id'],late_group='qda_'+site['component']+'_r'+str(rank))
            selected.append(spec)
    assert len(selected)<=16
    result=dict(status='FROZEN_BEFORE_NEIGHBOR_REPAIR',time=stamp(),selected=selected,records=records,
        selection_uses_only_exploration_OOF=True,test_accessed=False,validation_used_for_selection=False,
        code_sha256=sha(Path(__file__)),protocol_sha256=sha(VOUT/'LATE_TOKEN_COVERAGE_PROTOCOL_v3.json'))
    atomic(path,result);return result


if __name__=='__main__':
    setup('vlm_repair/qda_neighborhood');r=select();print('QDA_NEIGHBOR_SELECTION',len(r['selected']),flush=True)
