"""Complete the one already-owned four-scene claim exposed by the boundary audit."""
from r2_common import *
import psutil
import subprocess
from r2_peer_b1_finalize_handoff_v2 import checked

DEST=ROOT/'resources/handoffs/peer_b1_20261019_round2'


def main():
    setup('peer_b1_round2_prehandler')
    assert socket.gethostname().startswith('dlcqdtslnqnytsc7-')
    assert not (DEST/'RESUMED_PREHANDLER_CLAIM.json').exists()
    audit=read(DEST/'CLAIM_AUDIT_AFTER_DRAIN.json')
    pending=[v for v in audit['target_pending'] if not v['resident_admission_wrapper'] and not v['prior_failure_exists']]
    assert len(pending)==1;entry=pending[0]
    assert entry['owner']['pid']==274589 and entry['claim']=='admit_630f71a32b2aace89f0e2725'
    assert entry['stage']=='runs/fair_scientific_admission_v1/g0235'
    drain=read(DEST/'drain/SUSPENDED_SAFE.json')
    item=next(v for v in drain['items'] if v['process']['pid']==entry['owner']['pid'])
    p=checked(item['process']);assert p.status()==psutil.STATUS_STOPPED and item['kind']=='gpu'
    assert (ROOT/item['completed_receipt']).exists()
    actual=read(ROOT/entry['stage']/'claims'/entry['claim']/'OWNER.json')
    assert actual==entry['owner'] and actual['hostname']==socket.gethostname()
    atomic(DEST/'PREHANDLER_RESUME_INTENT.json',dict(time=stamp(),existing_owned_claim=entry,paused_item=item,
        original_chunk='four exploration scenes at canonical offsets464:468',no_new_task_added=True))
    p.resume();deadline=time.monotonic()+30
    while True:
        status=read(ROOT/item['status_file'])
        if status.get('task')==entry['claim'] or (ROOT/entry['stage']/'receipts'/(entry['claim']+'.json')).exists():break
        assert time.monotonic()<deadline,'Existing claim has not reached its status; no force/deletion.'
        time.sleep(.01)
    script=ROOT/'code/r2_peer_b1_boundary_drain_round2_pass2.py'
    log=(DEST/'drain_pass2.log').open('a')
    child=subprocess.Popen([sys.executable,'-u','-B',str(script)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    atomic(DEST/'RESUMED_PREHANDLER_CLAIM.json',dict(time=stamp(),status='ONLY_ONE_ALREADY_CLAIMED_TASK_RESUMED',
        owner=actual,original_paused_item=item,new_boundary_pid=child.pid,new_boundary_source_sha256=sha(script),
        other43_workers_remain_paused=True,no_claim_removed_or_new_scientific_task_added=True))
    print(json.dumps(dict(status='ONE_EXISTING_FOUR_SCENE_CLAIM_FINISHING',pid=p.pid,new_boundary_pid=child.pid)))


if __name__=='__main__':main()
