from common import *
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from vlm_core import VOUT
from vlm_intervene_v2 import Engine as Prior
from vlm_intervene_v3 import Engine as Next
from vlm_repair_queue_v2 import Fits,run_task
from repair_queue_v2 import init_score_unique,atomic_unique as atomic

def main():
    setup('vlm_repair/v3_probe');compatibility();base=VOUT/'performance_panel';task=read(base/'tasks.json')[0];all_runs=[];reference=None
    import torch
    with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_score_unique) as pool:
        for cls in [Prior,Next]:
            e=cls();fits=Fits();samples=[]
            for i in range(3):
                began=time.monotonic();records,timing=run_task(e,fits,task,base,pool,prefetch=True);elapsed=time.monotonic()-began
                if reference is None:reference=records
                else:assert records==reference,'Trajectory, score and actual norm/gate differences forbidden'
                samples.append(elapsed);print(cls.__module__,i,elapsed,flush=True)
            all_runs.append(dict(engine=cls.__module__,seconds=samples,warm_seconds=samples[1:],median_warm=float(sorted(samples[1:])[0]+sorted(samples[1:])[1])/2))
            del e,fits;torch.cuda.empty_cache()
    ratio=all_runs[1]['median_warm']/all_runs[0]['median_warm'];adopt=ratio<=.9
    atomic(VOUT/'V3_EQUIVALENCE_PERFORMANCE.json',dict(status='PASS',time=stamp(),trials=all_runs,ratio=ratio,adopt=adopt,threshold='at least10percent shorter full engineering task including CPU read/scoring; exact trajectories/scores/actual edit metrics',exact_records=True,real_cases=2,seeds=[0,1],synthetic_edit_calibration_only=True,code_sha256=sha(ROOT/'code/vlm_intervene_v3.py')))
if __name__=='__main__':main()
