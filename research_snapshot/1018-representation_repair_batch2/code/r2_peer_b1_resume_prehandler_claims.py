"""Finish only the two observed pre-handler claims, then pause at receipts again."""
from r2_common import *
import psutil
import subprocess

DEST=ROOT/'resources/handoffs/peer_b1_20261019'


def main():
    assert socket.gethostname().startswith('dlcqdtslnqnytsc7-')
    assert not(DEST/'RESUMED_PREHANDLER_CLAIMS.json').exists()
    expected={31061:'admit_aa1c6def4b70ccd4ca038d9d',31071:'admit_2f699914f07f77c2c0998679'}
    stage=ROOT/'runs/fair_scientific_admission_v1/g0213';drain=read(DEST/'drain/SUSPENDED_SAFE.json')
    items={v['process']['pid']:v for v in drain['items']};proof=[]
    for pid,ident in expected.items():
        item=items[pid];r=item['process'];p=psutil.Process(pid)
        assert p.create_time()==r['created'] and p.cmdline()==r['cmdline'] and p.uids().real==r['uid']==os.getuid()
        assert p.status()==psutil.STATUS_STOPPED and item['kind']=='gpu' and (ROOT/item['completed_receipt']).exists()
        assert not(stage/'claims'/ident/'OWNER.json').exists()
        proof.append(dict(pid=pid,expected_claim=ident,original_paused_item=item));p.resume()
    end=time.monotonic()+30
    while True:
        ready=True
        for pid,ident in expected.items():
            owner=stage/'claims'/ident/'OWNER.json'
            if not owner.exists():ready=False;continue
            o=read(owner);assert o['pid']==pid and o['hostname']==socket.gethostname()
            status=read(RUN/'dispatch_workers'/(socket.gethostname()+'_'+str(pid)+'.json'))
            if status.get('task')!=ident and not(stage/'receipts'/(ident+'.json')).exists():ready=False
        if ready:break
        assert time.monotonic()<end,'Expectedclaimregistrationhasnotmaterialized; do not deleteclaim.';time.sleep(.01)
    for r in proof:r['actual_owner']=read(stage/'claims'/r['expected_claim']/'OWNER.json')
    entry=ROOT/'code/r2_peer_b1_drain_pass2.py';log=(DEST/'drain_pass2_parent.log').open('a')
    child=subprocess.Popen([sys.executable,'-u','-B',str(entry)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    atomic(DEST/'RESUMED_PREHANDLER_CLAIMS.json',dict(time=stamp(),status='ONLY_TWO_EXACT_GPU_WORKERS_RESUMED_TO_FINISH_NEW_CLAIMS',
        workers=proof,new_boundary_watcher_pid=child.pid,new_boundary_watcher_sha256=sha(entry),
        no_claim_removed_or_reassigned=True,no_model_or_result_overwritten=True,other66workers_remain_suspended=True))
    print(json.dumps(dict(status='TWO_EXACT_PREHANDLER_CLAIMS_PROGRESSING',PIDs=list(expected),new_boundary_watcher=child.pid)))


if __name__=='__main__':
    try:main()
    except BaseException as error:
        import traceback
        atomic(DEST/'PREHANDLER_RESUME_FAILED.json',dict(time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        raise
