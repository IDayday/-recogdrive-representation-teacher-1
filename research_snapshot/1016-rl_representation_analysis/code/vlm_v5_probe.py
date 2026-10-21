from common import *
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from vlm_core import VOUT
from vlm_intervene_v2 import Engine
from vlm_repair_queue_v2 import Fits,stage,run_task as original
from vlm_repair_queue_v5 import run_task as improved
from repair_queue_v2 import init_score_unique,atomic_unique as atomic

def main():
    setup('vlm_repair/v5_probe');compatibility();source=ROOT/'runs/vlm_repair_20261016_v2/stages';name='coarse_d8c3fb19a947325c5f60';arms=read(source/name/'arms.json')
    rows=read(VOUT/'development/COARSE_PANEL.json');panel=[rows[0],rows[16],rows[24]]
    folder=VOUT/'v5_probe';stage(folder,'engineering',panel,arms[:64],[0,1],chunk=3,arm_chunk=64);task=read(folder/'tasks.json')[0];e=Engine();fits=Fits();reference=None;trials=[]
    with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_score_unique) as pool:
        for label,function in [('original_cold',original),('optimized_cold',improved),('original',original),('optimized',improved)]:
            began=time.monotonic();records,timing=function(e,fits,task,folder,pool,prefetch=True);seconds=time.monotonic()-began
            if reference is None:reference=records
            else:assert records==reference,'Output, seed, score or actual edit differences forbidden'
            trials.append(dict(label=label,seconds=seconds,stages=timing));print(json.dumps(trials[-1]),flush=True)
    ratio=trials[3]['seconds']/trials[2]['seconds'];atomic(VOUT/'V5_EQUIVALENCE_PERFORMANCE.json',dict(status='PASS',time=stamp(),trials=trials,ratio=ratio,adopt=ratio<=.9,exact_records=True,actual_cases=3,actual_calibrated_arms=64,seeds=[0,1],scope='new stages only; frozen existing queue remains unchanged',code_sha256=sha(ROOT/'code/vlm_repair_queue_v5.py')))
if __name__=='__main__':main()
