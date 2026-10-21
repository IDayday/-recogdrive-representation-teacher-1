"""Finish an accepted receipt-boundary drain; preserve the actual DLC keeper.

Run only after the agent reviews a fresh pending-owner audit. Never calls a
cloud API, deletes a claim, changes a scientific output, or targets another node.
"""
from r2_common import *
import argparse
import psutil

DEST=ROOT/'resources/handoffs/peer_b1_20261019'


def identity(p):
    return dict(pid=p.pid,created=p.create_time(),uid=p.uids().real,cmdline=p.cmdline(),ppid=p.ppid())


def terminal(r):
    try:
        p=psutil.Process(r['pid']);assert p.create_time()==r['created']
        return p.status()==psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:return True


def checked(r):
    p=psutil.Process(r['pid']);assert p.create_time()==r['created'] and p.uids().real==r['uid']==os.getuid()
    assert p.cmdline()==r['cmdline'];return p


def stop(r):
    if terminal(r):return
    # Each target's argv and ancestry were captured before any signal. During
    # shutdown argv may become empty before the kernel marks it a zombie;
    # PID, creation time and UID still identify that exact recorded process.
    p=psutil.Process(r['pid'])
    assert p.create_time()==r['created'] and p.uids().real==r['uid']==os.getuid()
    p.terminate()
    try:
        if p.status()==psutil.STATUS_STOPPED:p.resume()
    except psutil.NoSuchProcess:pass


def main(a):
    assert socket.gethostname().startswith('dlcqdtslnqnytsc7-')
    assert dt.datetime.now(dt.timezone.utc)>=dt.datetime(2026,10,19,5,tzinfo=dt.timezone.utc)
    assert not (DEST/'COMPUTE_STOPPED_AWAITING_ACCEPTANCE.json').exists()
    node=next(n for n in read(ROOT/'resources/NODES.json')['nodes'] if n['name']=='peer_b1')
    assert node['job']=='dlcqdtslnqnytsc7' and node['active_for_batch2'] is False and node['devices']==[]
    drain=read(ROOT/a.drain_proof);audit=read(ROOT/a.audit)
    assert audit['target_job']=='dlcqdtslnqnytsc7' and audit['time']>=drain['time']
    unresolved=[v for v in audit['target_pending'] if not v['resident_admission_wrapper'] and not v['prior_failure_exists']]
    assert not unresolved,unresolved
    first=min(dt.datetime.fromisoformat(v['paused_at']).timestamp() for v in drain['items'])
    assert not [v for v in audit['empty_claim_observations'] if v['mtime']>=first-5], 'Recentunownedclaimsrequireagentreview/resume, notdeletion.'
    roots=[]
    for item in drain['items']:
        r=item['process'];p=checked(r);assert p.status()==psutil.STATUS_STOPPED
        if item['completed_receipt']:assert (ROOT/item['completed_receipt']).exists()
        roots.append(identity(p))
    inventory=read(DEST/'peer_b1_INVENTORY_WITH_KEEPALIVE.json')['processes']
    keeper=next(v for v in inventory if v['pid']==5);core=next(v for v in inventory if v['pid']==6)
    keep=psutil.Process(5);assert keep.create_time()==keeper['create_time'] and keep.cmdline()==keeper['cmdline']
    assert keep.ppid()==1 and 'code/vlm_clone_runtime.py' in keep.cmdline()
    legacy=psutil.Process(6);assert legacy.create_time()==core['create_time'] and legacy.ppid()==5
    assert str(OLD/'code/vlm_elastic_node.py') in legacy.cmdline()
    cfgpath=OLD/'vlm_repair_v1/elastic_v1/nodes/elastic_004';cfg=read(cfgpath/'CONFIG.json')
    oldstates=[]
    for rank in cfg['gpu_ranks']:
        p=cfgpath/'gpu_workers'/f'rank{rank:03d}.json';d=read(p)
        assert d['status'] in ['QUEUE_WAIT','WAITING_ACTIVATION'];oldstates.append(dict(path=str(p),state=d))
    for rank in range(cfg['cpu_rank_base'],cfg['cpu_rank_base']+cfg['cpu_workers']):
        p=OLD/'vlm_repair_v1/scan/workers'/f'rank{rank:03d}.json';d=read(p)
        assert d['status']=='QUEUE_WAIT';oldstates.append(dict(path=str(p),state=d))
    oldworkers=legacy.children(recursive=False)
    assert len(oldworkers)==len(cfg['gpu_ranks'])+cfg['cpu_workers']==96
    for p in oldworkers:
        args=p.cmdline();assert str(OLD/'code/vlm_elastic_node.py') in args and '--id' in args
        assert args[args.index('--id')+1]=='elastic_004' and p.uids().real==os.getuid()
        r=identity(p);p.suspend();roots.append(r)
    parents=[]
    for p in psutil.process_iter(['cmdline']):
        try:
            args=p.info['cmdline'] or []
            if not any(str(ROOT/'code'/s) in args for s in ['r2_node.py','r2_cpu_boost.py','r2_background_supervisor.py']):continue
            if '--node' not in args or args[args.index('--node')+1]!='peer_b1':continue
            assert p.uids().real==os.getuid();parents.append(identity(p))
        except psutil.NoSuchProcess:continue
    assert len(parents)==3
    parents.append(identity(legacy));targets={}
    for r in roots+parents:
        p=checked(r);targets[p.pid]=r
        for child in p.children(recursive=True):
            if child.status()==psutil.STATUS_ZOMBIE:continue
            assert child.uids().real==os.getuid();targets[child.pid]=identity(child)
    assert 1 not in targets and 5 not in targets and os.getpid() not in targets
    intent=dict(time=stamp(),status='EXACT_OWNED_COMPUTE_RETIREMENT_AFTER_RECEIPT_AND_OWNER_AUDIT',
        roots=roots,parents=parents,all_targets=list(targets.values()),legacy_idle_states=oldstates,
        kept_DLC_runtime=keeper,audit=a.audit,audit_sha256=sha(ROOT/a.audit),no_claim_deletion_or_output_overwrite=True)
    atomic(DEST/'FINAL_COMPUTE_RETIRE_INTENT.json',intent)
    for r in parents:stop(r)
    for r in targets.values():
        if r['pid'] not in {v['pid'] for v in parents}:stop(r)
    end=time.monotonic()+30
    while True:
        pending=[r for r in targets.values() if not terminal(r)]
        if not pending:break
        assert time.monotonic()<end,[v['pid'] for v in pending];time.sleep(.1)
    keep=psutil.Process(5);assert keep.create_time()==keeper['create_time'] and keep.status()!=psutil.STATUS_ZOMBIE
    atomic(DEST/'COMPUTE_STOPPED_AWAITING_ACCEPTANCE.json',dict(status='EXACT_OWN_COMPUTE_TERMINAL_DLC_KEEPER_RETAINED',
        time=stamp(),root_workers=len(roots),total_target_processes=len(targets),kept_runtime_pid=5,
        kept_runtime_created=keeper['create_time'],no_scientific_task_interrupted=True,no_claim_deleted=True,
        no_DLC_stop_or_release_called=True,formal_cloud_GPU_and_receiver_acceptance_still_required=True))
    print(json.dumps(dict(status='OWN_COMPUTE_STOPPED_KEEPER_RETAINED',workers=len(roots),processes=len(targets))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--audit',required=True);p.add_argument('--drain-proof',default='resources/handoffs/peer_b1_20261019/drain/SUSPENDED_SAFE.json');a=p.parse_args()
    try:main(a)
    except BaseException as error:
        import traceback
        atomic(DEST/'FINALIZE_FAILED.json',dict(time=stamp(),error=repr(error),traceback=traceback.format_exc(),
            no_automatic_retry_or_cloud_stop=True))
        raise
