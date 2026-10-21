"""Use an accepted equivalent backup only after original jobs/pods terminate.

Availability, never the observed metric, determines which implementation wins.
Existing original results always take precedence, including an interrupted
receipt commit. No original result/array/claim is removed or overwritten here.
"""
from common import *
import shutil
from vlm_core import VOUT
from vlm_quiescence import assert_quiescent
from repair_queue_v2 import atomic_unique as atomic
from vlm_resume import scan_result

def main():
    setup('vlm_repair/fold_backup_adopt');states=assert_quiescent()
    source=VOUT/'fold_backup';protocol=read(source/'PROTOCOL.json');engineering=read(source/'ENGINEERING_PASS.json')
    assert engineering['status']=='PASS'
    for path,h in protocol['original_math_sha256'].items():assert sha(ROOT/path)==h
    base=VOUT/'scan';tasks={t['id']:t for t in read(base/'tasks.json')};out=[]
    for cell in protocol['cells']:
        if cell==protocol['control']:continue
        result=base/'results'/(cell+'.json');receipt=base/'receipts'/(cell+'.json')
        if result.exists():
            scan_result(base,tasks[cell],result)
            out.append(dict(cell=cell,decision='ORIGINAL_ALWAYS_PREFERRED',original_receipt_exists=receipt.exists()));continue
        assert not receipt.exists(),cell
        proof_path=source/'completed'/(cell+'.json')
        if not proof_path.exists():out.append(dict(cell=cell,decision='BACKUP_NOT_COMMITTED_REQUEUE_ORIGINAL'));continue
        proof=read(proof_path);assert proof['status']=='PASS' and proof['directions_checkpointed']==10
        other=ROOT/proof['result_path'];assert sha(other)==proof['result_sha256'];scan_result(base,tasks[cell],other)
        # Quiescence and the before-restart ordering rule exclude old writers.
        assert not result.exists()
        atomic(result,read(other));assert sha(result)==sha(other)
        atomic(receipt,dict(status='COMPLETE',time=stamp(),rank=-1,task=tasks[cell],result_sha256=sha(result),
            implementation='Exact frozen scan, independently checkpointed by CV fold',backup_proof=str(proof_path.relative_to(ROOT)),
            control_engineering_sha256=sha(source/'ENGINEERING_PASS.json'),adopted_only_after_original_platform_termination=True,seconds=None))
        out.append(dict(cell=cell,decision='ACCEPTED_BACKUP_ADOPTED',result_sha256=sha(result)))
    dest=source/'adoption'/('adoption_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
    atomic(dest,dict(status='PASS',time=stamp(),quiescence=states,decisions=out,original_results_preferred=True,no_score_based_choice=True))
    print(json.dumps(dict(status='PASS',decisions=out,path=str(dest.relative_to(ROOT)))),flush=True)

if __name__=='__main__':main()
