"""Retire only this rejoin's drained processes, preserving the DLC keeper and job."""
from r2_common import *
import argparse
import psutil
from r2_peer_b1_finalize_handoff_v2 import identity,terminal,checked,stop

DEST=ROOT/'resources/handoffs/peer_b1_20261019_round2'


def main(args):
    setup('peer_b1_finalize_round2')
    assert socket.gethostname().startswith('dlcqdtslnqnytsc7-')
    assert not (DEST/'COMPUTE_STOPPED_AWAITING_ACCEPTANCE.json').exists()
    node=next(n for n in read(ROOT/'resources/NODES.json')['nodes'] if n['name']=='peer_b1')
    assert node['active_for_batch2'] is False and node['devices']==[]
    drain=read(ROOT/args.drain_proof);audit=read(ROOT/args.audit)
    assert audit['target_job']=='dlcqdtslnqnytsc7' and audit['time']>=drain['time']
    assert not [v for v in audit['target_pending'] if not v['resident_admission_wrapper'] and not v['prior_failure_exists']]
    first=min(dt.datetime.fromisoformat(v['paused_at']).timestamp() for v in drain['items'])
    assert not [v for v in audit['empty_claim_observations'] if v['mtime']>=first-5]
    assert sum(v['kind']=='gpu' for v in drain['items'])==16
    assert sum(v['kind']=='background' for v in drain['items'])==4
    assert sum(v['kind']=='cpu' for v in drain['items'])==24
    roots=[]
    for item in drain['items']:
        p=checked(item['process']);assert p.status()==psutil.STATUS_STOPPED
        if item['completed_receipt']:assert (ROOT/item['completed_receipt']).exists()
        roots.append(identity(p))
    old=read(ROOT/'resources/handoffs/peer_b1_20261019/NODE_EMPTY_HARDWARE_AND_PROCESS_ACCEPTANCE.json')
    keeper=next(p for p in old['observations'][-1]['processes'] if p['pid']==5)
    keep=psutil.Process(5)
    assert keep.create_time()==keeper['create_time'] and keep.cmdline()==keeper['cmdline'] and keep.ppid()==1
    nodeparent=read(RUN/'nodes/peer_b1/LIVE.json')
    bgparent=read(RUN/'background_supervisor/peer_b1/rejoin1_overlap_v1/START.json')
    parent_specs=[(nodeparent['pid'],'r2_node.py'),(bgparent['pid'],'r2_background_supervisor.py')]
    parents=[]
    for pid,script in parent_specs:
        p=psutil.Process(pid);argv=p.cmdline()
        assert str(ROOT/'code'/script) in argv and argv[argv.index('--node')+1]=='peer_b1'
        assert p.uids().real==os.getuid()
        parents.append(identity(p))
    assert {r['ppid'] for r in roots}=={r['pid'] for r in parents}
    assert {c.pid for r in parents for c in checked(r).children(recursive=False)}=={r['pid'] for r in roots}
    targets={}
    for record in roots+parents:
        p=checked(record);targets[p.pid]=record
        for child in p.children(recursive=True):
            try:
                if child.status()==psutil.STATUS_ZOMBIE:continue
                assert child.uids().real==os.getuid();targets[child.pid]=identity(child)
            except psutil.NoSuchProcess:continue
    assert not {1,5,os.getpid()}&set(targets)
    atomic(DEST/'FINAL_COMPUTE_RETIRE_INTENT.json',dict(time=stamp(),roots=roots,parents=parents,
        all_targets=list(targets.values()),kept_DLC_keeper=keeper,audit=args.audit,audit_sha256=sha(ROOT/args.audit),
        drain=args.drain_proof,drain_sha256=sha(ROOT/args.drain_proof),no_claim_deletion=True))
    for record in parents:stop(record)
    for record in targets.values():
        if record['pid'] not in {p['pid'] for p in parents}:stop(record)
    deadline=time.monotonic()+30
    while True:
        pending=[r for r in targets.values() if not terminal(r)]
        if not pending:break
        assert time.monotonic()<deadline,[r['pid'] for r in pending]
        time.sleep(.1)
    keep=psutil.Process(5);assert keep.create_time()==keeper['create_time'] and keep.status()!=psutil.STATUS_ZOMBIE
    atomic(DEST/'COMPUTE_STOPPED_AWAITING_ACCEPTANCE.json',dict(status='OWN_COMPUTE_TERMINAL_DLC_KEEPER_RETAINED',
        time=stamp(),root_workers=len(roots),total_target_processes=len(targets),kept_runtime_pid=5,
        no_scientific_task_interrupted=True,no_claim_deleted=True,no_DLC_stop_or_release_called=True,
        formal_process_GPU_receiver_and_cloud_acceptance_still_required=True))
    print(json.dumps(dict(status='OWN_COMPUTE_STOPPED_KEEPER_RETAINED',workers=len(roots),processes=len(targets))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--audit',required=True)
    p.add_argument('--drain-proof',default='resources/handoffs/peer_b1_20261019_round2/drain/SUSPENDED_SAFE.json')
    try:main(p.parse_args())
    except BaseException as error:
        import traceback
        atomic(DEST/'FINALIZE_FAILED.json',dict(time=stamp(),error=repr(error),traceback=traceback.format_exc(),no_automatic_retry=True))
        raise
