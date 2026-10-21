"""Wait for complete original CV arrays and perform independent vectorized acceptance."""
from common import *
import subprocess,traceback
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic
if __name__=='__main__':
    setup('vlm_repair/full_analysis_waiter')
    folder=VOUT/'full_analysis_accept';folder.mkdir(exist_ok=True)
    try:
        for p,h in read(VOUT/'FULL_ANALYSIS_ACCEPT_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
        while len(list((VOUT/'scan/receipts').glob('*.json')))!=2272:time.sleep(60)
        with (folder/'accept.log').open('a') as stream:
            subprocess.run([sys.executable,'-u','-B',str(ROOT/'code/vlm_full_analysis_accept.py')],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=True)
        assert read(VOUT/'FULL_ORIGINAL_ANALYSIS_ACCEPTANCE_LATEST.json')['status']=='PASS'
        print('ALL_ORIGINAL_CV_ARRAYS_ACCEPTED',flush=True)
    except BaseException as exc:
        atomic(VOUT/'late_token_coverage/failures/full_analysis_accept.json',dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()));raise
