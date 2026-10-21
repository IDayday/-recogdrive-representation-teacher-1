from common import *
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from vlm_core import VOUT
from vlm_intervene_v2 import Engine
from vlm_repair_queue_v2 import Fits,run_task,stage
from repair_queue_v2 import init_score_unique,atomic_unique as atomic

def main():
    setup('vlm_repair/operators_v2');compatibility()
    while not (VOUT/'development/FIRST_FIT_READY.json').exists():time.sleep(2)
    fit=read(VOUT/'development/FIRST_FIT_READY.json');from vlm_funnel import arms
    candidates=arms(fit);chosen=[]
    for method in sorted({a['method'] for a in candidates}):chosen.append(next(a for a in candidates if a['method']==method and a['alpha']==.5 and a['cap']==.01))
    parent=chosen[0]
    for gate in ['hard','soft']:
        a=dict(parent,gate=gate);a['id']='probe_'+digest(a)[:16];chosen.append(a)
    for control in ['reverse','haar_rotation']:
        a=dict(parent,control_kind=control);a['id']='probe_'+digest(a)[:16];chosen.append(a)
    chosen.append(dict(id='probe_combination',method='combination',parts=[dict(parent,alpha=0.),dict(parent,alpha=0.)],cap=.01))
    base=VOUT/'operator_probe';rows=read(ROOT/'repair_v1/anchors.json')[:2];stage(base,'engineering',rows,chosen,[0,1],chunk=2,arm_chunk=64)
    e=Engine();f=Fits()
    with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_score_unique) as pool:
        task=read(base/'tasks.json')[0];records,timings=run_task(e,f,task,base,pool);again,_=run_task(e,f,task,base,pool);assert records==again
    atomic(VOUT/'INTERVENTION_OPERATORS_V2_PASS.json',dict(status='PASS',time=stamp(),fit_id=fit['id'],fit_sha256=fit['sha256'],actual_inputs=len(rows),seeds=[0,1],methods=sorted({a['method'] for a in chosen}),controls=['reverse','haar_rotation'],gates=['hard','soft'],all_caps_verified=True,repeat_exact=True,records=records,timings=timings,code_sha256=sha(ROOT/'code/vlm_intervene_v2.py')))
    print('ALL_UPSTREAM_OPERATORS_V2_PASS',flush=True)
if __name__=='__main__':main()
