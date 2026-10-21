"""Append-only final analysis after every upstream batch and full grid is complete."""
from common import *
import fcntl,subprocess,traceback
from vlm_core import VOUT
from vlm_late_qualification import DEST as LATE
from repair_queue_v2 import atomic_unique as atomic

DEST=VOUT/'finalize_all_v1'


def run(script,arguments=()):
    name=script+('_'+'_'.join(arguments) if arguments else '')
    marker=DEST/'steps'/(name+'.json')
    if marker.exists():assert read(marker)['code_sha256']==sha(ROOT/'code'/script);return
    with (DEST/(name+'.log')).open('a') as stream:
        subprocess.run([sys.executable,'-u','-B',str(ROOT/'code'/script),*arguments],cwd=ROOT,
            stdout=stream,stderr=subprocess.STDOUT,check=True)
    atomic(marker,dict(status='PASS',time=stamp(),script=script,arguments=arguments,code_sha256=sha(ROOT/'code'/script)))


def main():
    setup('vlm_repair/finalize_all');DEST.mkdir(exist_ok=True)
    for p,h in read(VOUT/'ALL_FINALIZE_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    with (DEST/'controller.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        stream=(DEST/'ungated.log').open('a')
        ungated=subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code/vlm_late_ungated.py')],
                cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        while True:
            assert ungated.poll() in [None,0],'Late ungated controller failed; retain original log.'
            original=(VOUT/'FINAL_ANALYSES_REVIEW_READY.json').exists()
            late=(LATE/'INFERENCE_COMPLETE.json').exists() or (LATE/'NO_COMPETITIVE_CANDIDATES.json').exists()
            full=len(list((VOUT/'scan/receipts').glob('*.json')))==2272
            complete=original and late and full and (LATE/'UNGATED_COMPLETE.json').exists()
            atomic(DEST/'STATUS.json',dict(time=stamp(),original_analyses_ready=original,late_inference_ready=late,
                full_original_grids=full,late_ungated_ready=(LATE/'UNGATED_COMPLETE.json').exists()))
            if complete:break
            time.sleep(30)
        if (LATE/'INFERENCE_COMPLETE.json').exists():
            run('vlm_late_accept.py');run('vlm_late_trajectory_audit.py',['--study','late'])
        for script in ['vlm_all_statistics.py','vlm_all_prior_statistics.py','vlm_all_oracle.py',
                       'vlm_qda_joint.py','vlm_qda_report.py','vlm_readout_report.py','vlm_rank_bound_audit.py']:
            run(script)
        run('vlm_dimension_report_all.py',['--require-complete'])
        atomic(VOUT/'ALL_BATCHES_ANALYSES_REVIEW_READY.json',dict(status='READY_FOR_VISUAL_AND_REPORT_REVIEW',
            time=stamp(),all_original_full_grids=2272,corrected_semantic_full_grids=64,
            late_inference_complete=(LATE/'INFERENCE_COMPLETE.json').exists(),
            late_no_competitive=(LATE/'NO_COMPETITIVE_CANDIDATES.json').exists(),
            source_code_sha256=sha(Path(__file__)),report_still_requires_build_and_review=True,
            queues_and_jobs_retained=True))
        print('ALL_BATCHES_ANALYSES_REVIEW_READY',flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as exc:
        atomic(LATE/'failures/finalize_all.json',dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()));raise
