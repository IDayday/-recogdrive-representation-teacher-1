from common import *
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from vlm_core import VOUT,raw_features
from vlm_intervene_v2 import Engine as Original
from vlm_intervene_v4 import Engine as Extended
from vlm_repair_queue_v2 import Fits,run_task as reference
from vlm_repair_queue_v6 import run_task as candidate
from repair_queue_v2 import init_score_unique,atomic_unique as atomic

def main():
    setup('vlm_repair/v6_equivalence');compatibility();folder=VOUT/'v5_probe';task=read(folder/'tasks.json')[0]
    import torch
    with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_score_unique) as pool:
        old=Original();f=Fits();expected,_=reference(old,f,task,folder,pool);del old,f;torch.cuda.empty_cache()
        new=Extended();f=Fits();actual,_=candidate(new,f,task,folder,pool);assert actual==expected
        regions=[]
        with torch.no_grad():
            for row in read(ROOT/'repair_v1/anchors.json')[:2]:
                hidden=new.forward_native(raw_features(row))
                for block in ['language_input','language_14','language_norm','interface_post']:
                    for group in ['command_v2','requirements_v2']:
                        mask,valid=new.mask(block,group);assert valid and int(mask.sum())>0
                        dimension=new.prefix[block].shape[-1];basis=torch.eye(dimension,device='cuda')[:,:8];fit=dict(basis=basis,center=basis.new_zeros(dimension),mh=basis.new_ones(8),mf=basis.new_zeros(8))
                        arm=dict(block=block,group=group,method='mean',gate='none',alpha=.5,cap=.01);edited,stats=new.edited(arm,fit);assert float(stats[0]/stats[1])<=.010001;new.suffix(block,edited)
                        regions.append(dict(token=row['token'],block=block,group=group,tokens=int(mask.sum())))
        new.verify_engine()
    atomic(VOUT/'V6_EQUIVALENCE.json',dict(status='PASS',time=stamp(),old_region_trajectories_scores_edits_exact=True,old_actual_cases=3,old_arms=64,seeds=[0,1],new_region_checks=regions,code_sha256={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'code/vlm_intervene_v4.py',ROOT/'code/vlm_repair_queue_v6.py']}))
    print('V6_OLD_EXACT_NEW_REGIONS_PASS',flush=True)
if __name__=='__main__':main()
