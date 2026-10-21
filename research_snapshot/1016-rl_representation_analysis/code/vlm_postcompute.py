"""CPU-only acceptance after GPU stages; main job and queues always stay open."""
from common import *
import subprocess,traceback
from vlm_core import VOUT
from vlm_semantic import SEM
from repair_queue_v2 import atomic_unique as atomic

def run(script,arguments=()):
    dest=VOUT/'postcompute';dest.mkdir(exist_ok=True)
    with (dest/(script+'.log')).open('a') as stream:
        subprocess.run([sys.executable,'-u','-B',str(ROOT/'code'/script),*arguments],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=True)

def main():
    setup('vlm_repair/postcompute')
    while not (VOUT/'final/PRIMARY_INFERENCE_COMPLETE.json').exists():time.sleep(30)
    if not (VOUT/'final/SCIENTIFIC_ACCEPTANCE.json').exists():run('vlm_final_accept.py',['--study','primary'])
    while True:
        if (SEM/'repair/INFERENCE_COMPLETE.json').exists():
            if not (SEM/'repair/SCIENTIFIC_ACCEPTANCE.json').exists():run('vlm_final_accept.py',['--study','semantic'])
            break
        if (SEM/'repair/NO_COMPETITIVE_CANDIDATES.json').exists():break
        time.sleep(30)
    for script in ['vlm_final_statistics.py','vlm_oracle_all.py','vlm_oracle_policy_groups.py','vlm_readout_report.py','vlm_multiple_comparisons.py']:run(script)
    atomic(VOUT/'POSTCOMPUTE_REVIEW_READY.json',dict(status='READY_FOR_REVIEW',time=stamp(),primary_science_accepted=True,
        semantic_science_accepted=(SEM/'repair/SCIENTIFIC_ACCEPTANCE.json').exists(),semantic_no_competitive=(SEM/'repair/NO_COMPETITIVE_CANDIDATES.json').exists(),
        report_and_visual_review_pending=True,full_grid_progress_must_be_reviewed=True,resources_and_queues_retained=True))
    print('POSTCOMPUTE_REVIEW_READY',flush=True)

if __name__=='__main__':
    try:main()
    except BaseException as e:
        atomic(VOUT/'failures/postcompute.json',dict(status='FAILED',time=stamp(),error=repr(e),traceback=traceback.format_exc()));raise
