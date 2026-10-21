"""Finalize the lightweight observation gate after the four frozen repair batches."""
from common import *
import fcntl,subprocess,traceback
from vlm_core import VOUT
from vlm_obs_qda_gate import OUT
from repair_queue_v2 import atomic_unique as atomic

DEST=VOUT/'finalize_five_v1'


def run(script):
    marker=DEST/'steps'/(script+'.json')
    if marker.exists():assert read(marker)['code_sha256']==sha(ROOT/'code'/script);return
    with (DEST/(script+'.log')).open('a') as stream:
        subprocess.run([sys.executable,'-u','-B',str(ROOT/'code'/script)],cwd=ROOT,
            stdout=stream,stderr=subprocess.STDOUT,check=True)
    atomic(marker,dict(status='PASS',time=stamp(),script=script,code_sha256=sha(ROOT/'code'/script)))


def main():
    setup('vlm_repair/finalize_five');DEST.mkdir(exist_ok=True)
    for p,h in read(VOUT/'FIVE_FINALIZE_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    with (DEST/'controller.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            original=(VOUT/'ALL_FOUR_BATCHES_ANALYSES_REVIEW_READY.json').exists()
            own=(OUT/'INFERENCE_COMPLETE.json').exists() or (OUT/'NO_COMPETITIVE_CANDIDATES.json').exists()
            atomic(DEST/'STATUS.json',dict(time=stamp(),all_four_prior_batches_ready=original,observation_gate_ready=own))
            if original and own:break
            time.sleep(30)
        if (OUT/'INFERENCE_COMPLETE.json').exists():run('vlm_obs_gate_accept.py')
        for script in ['vlm_five_statistics.py','vlm_five_prior_statistics.py','vlm_five_oracle.py']:run(script)
        atomic(VOUT/'ALL_FIVE_BATCHES_ANALYSES_REVIEW_READY.json',dict(status='READY_FOR_VISUAL_AND_REPORT_REVIEW',
            time=stamp(),observation_gate_accepted=(OUT/'SCIENTIFIC_ACCEPTANCE.json').exists(),
            observation_gate_no_competitive=(OUT/'NO_COMPETITIVE_CANDIDATES.json').exists(),
            all_four_original_batches_preserved=True,all_five_joint_statistics=True,resources_and_queues_retained=True,
            source_code_sha256=sha(Path(__file__)),report_requires_build_and_visual_review=True))
        print('ALL_FIVE_BATCHES_ANALYSES_REVIEW_READY',flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as exc:
        atomic(OUT/'failures/finalize_five.json',dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()));raise
