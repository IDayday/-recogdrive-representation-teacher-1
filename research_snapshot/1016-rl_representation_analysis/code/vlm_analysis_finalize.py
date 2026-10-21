"""Append-only CPU analyses after original postcompute and ungated diagnostics.

This independently versioned waiter never modifies a frozen inference program,
selects policies using test results, publishes a report, or stops a job/queue.
"""
from common import *
import subprocess,traceback,fcntl
from vlm_core import VOUT
from vlm_semantic import SEM
from repair_queue_v2 import atomic_unique as atomic
DEST=VOUT/'finalize_analysis_v1'

def run(script,arguments=()):
    name=script+('_'+'_'.join(arguments) if arguments else '')
    marker=DEST/'steps'/(name+'.json')
    if marker.exists():assert read(marker)['code_sha256']==sha(ROOT/'code'/script);return
    with (DEST/(name+'.log')).open('a') as stream:
        subprocess.run([sys.executable,'-u','-B',str(ROOT/'code'/script),*arguments],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=True)
    atomic(marker,dict(status='PASS',time=stamp(),script=script,arguments=arguments,code_sha256=sha(ROOT/'code'/script)))

def main():
    setup('vlm_repair/finalize_analysis');DEST.mkdir(exist_ok=True)
    for path,h in read(VOUT/'FINALIZE_ANALYSIS_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/path)==h,path
    with (DEST/'controller.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while not ((VOUT/'POSTCOMPUTE_REVIEW_READY.json').exists() and (VOUT/'UNGATED_TEST_DIAGNOSTICS_COMPLETE.json').exists()):time.sleep(30)
        canonical=read(VOUT/'FULL_GRID_SCHEDULE.json')['canonical']
        while not all((VOUT/'scan/receipts'/(t['id']+'.json')).exists() for t in canonical) or len(list((SEM/'scan/receipts').glob('*.json')))!=64:time.sleep(30)
        run('vlm_baseline_trajectory_audit.py',['--study','primary'])
        if (SEM/'repair/INFERENCE_COMPLETE.json').exists():run('vlm_baseline_trajectory_audit.py',['--study','semantic'])
        else:assert (SEM/'repair/NO_COMPETITIVE_CANDIDATES.json').exists()
        # Original postcompute has already finished its statistics and original
        # multiplicity pass; these refreshes therefore cannot be superseded by it.
        for script in ['vlm_prior_reference_statistics.py','vlm_oracle_ungated_sources.py','vlm_qda_joint.py','vlm_qda_report.py','vlm_readout_report.py','vlm_rank_bound_audit.py']:
            run(script)
        run('vlm_dimension_report.py',['--require-complete'])
        atomic(VOUT/'FINAL_ANALYSES_REVIEW_READY.json',dict(status='READY_FOR_VISUAL_AND_REPORT_REVIEW',time=stamp(),
            actual_data_analyses_complete=True,figures_need_review=True,report_not_built_by_this_script=True,resources_and_queues_retained=True))
        print('FINAL_ANALYSES_REVIEW_READY',flush=True)

if __name__=='__main__':
    try:main()
    except BaseException as e:
        atomic(VOUT/'failures/finalize_analysis.json',dict(status='FAILED',time=stamp(),error=repr(e),traceback=traceback.format_exc()));raise
