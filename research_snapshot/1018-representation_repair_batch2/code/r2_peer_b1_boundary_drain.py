"""Pause exact task-owned workers only after their current receipt is durable.

No scientific task is cancelled, no claim is removed, and no DLC process is
released. A separate agent acceptance is required before terminating workers.
"""
from r2_common import *
import psutil

DEST = ROOT/'resources/handoffs/peer_b1_20261019/drain'


def record(p):
    return dict(pid=p.pid, created=p.create_time(), cmdline=p.cmdline(), uid=p.uids().real)


def process(r):
    p=psutil.Process(r['pid'])
    assert p.create_time()==r['created'] and p.cmdline()==r['cmdline']
    assert p.uids().real==r['uid']==os.getuid()
    return p


def finished(item):
    d=read(ROOT/item['status_file'])
    if d['status']=='QUEUE_WAIT': return True,d,None
    if d['status']!='COMPUTING': return False,d,None
    receipt=(RUN/'receipts_cpu'/(d['task']+'.json') if item['kind']=='cpu'
        else ROOT/d['stage']/'receipts'/(d['task']+'.json'))
    return receipt.exists(),d,str(receipt.relative_to(ROOT))


def main():
    setup('peer_b1_boundary_drain')
    assert socket.gethostname().startswith('dlcqdtslnqnytsc7-')
    assert read(DEST.parent/'INTENT.json')['job']=='dlcqdtslnqnytsc7'
    guard=(DEST/'drain.lock');guard.parent.mkdir(parents=True,exist_ok=True)
    stream=guard.open('a+');fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not (DEST/'SUSPENDED_SAFE.json').exists()
    items=[]
    for p in psutil.process_iter(['cmdline']):
        try:
            args=p.info['cmdline'] or [];scripts={Path(a).name for a in args if a.startswith(str(ROOT)+'/code/')}
            if scripts & {'r2_gpu.py','r2_gpu_background.py'}:
                if '--node' not in args or args[args.index('--node')+1]!='peer_b1': continue
                if 'r2_gpu.py' in scripts:
                    status=RUN/'dispatch_workers'/(socket.gethostname()+'_'+str(p.pid)+'.json');kind='gpu'
                else:
                    device=int(args[args.index('--device')+1]);tag=args[args.index('--tag')+1]
                    status=RUN/'background_gpu/peer_b1'/f'device{device:02d}'/tag/'LIVE.json';kind='background'
            elif scripts & {'r2_cpu.py','r2_cpu_extra.py'}:
                name=args[args.index('--worker')+1]
                if not name.startswith('peer_b1_'): continue
                status=RUN/'workers_cpu'/(name+'.json');kind='cpu'
            else: continue
            assert p.pid>10 and p.uids().real==os.getuid() and status.exists()
            items.append(dict(process=record(p),kind=kind,status_file=str(status.relative_to(ROOT))))
        except psutil.NoSuchProcess: continue
    assert sum(i['kind']=='gpu' for i in items)==16
    assert sum(i['kind']=='background' for i in items)==4
    assert sum(i['kind']=='cpu' for i in items)>=24
    atomic(DEST/'WORKERS_BEFORE.json',dict(time=stamp(),items=items))
    start=dt.datetime.fromisoformat(read(DEST.parent/'INTENT.json')['reminders_UTC']['drain_start'])
    while dt.datetime.now(dt.timezone.utc)<start: time.sleep(30)
    pending={i['process']['pid']:i for i in items};paused=[];began=time.monotonic()
    while pending:
        for pid,item in list(pending.items()):
            p=process(item['process']);done,before,receipt=finished(item)
            if not done: continue
            p.suspend()
            until=time.monotonic()+1
            while time.monotonic()<until and p.status()!=psutil.STATUS_STOPPED: time.sleep(.001)
            assert p.status()==psutil.STATUS_STOPPED
            done,after,receipt=finished(item)
            if not done:
                p.resume();continue
            # A new queue claim could precede the next status write. The
            # handler runs after that write, so such claims are not executed;
            # retain them for the explicit post-stop owner audit.
            paused.append(dict(**item,paused_at=stamp(),last_status=after,
                completed_receipt=receipt,possible_prehandler_claim_requires_audit=True))
            pending.pop(pid)
        atomic(DEST/'LIVE.json',dict(time=stamp(),status='DRAINING_AT_DURABLE_RECEIPT_BOUNDARIES',
            suspended=len(paused),remaining=len(pending),remaining_processes=list(pending),
            seconds=time.monotonic()-began,no_termination_or_claim_deletion=True))
        if time.monotonic()-began>1800:
            atomic(DEST/'ATTENTION.json',dict(time=stamp(),reason='Somecurrenttasksnotfinishedwithin30min',remaining=list(pending),suspended=paused,no_forced_termination=True));return
        time.sleep(.02)
    atomic(DEST/'SUSPENDED_SAFE.json',dict(time=stamp(),status='ALL_EXACT_WORKERS_SUSPENDED_AFTER_DURABLE_RECEIPTS',
        items=paused,require_claim_owner_audit_before_termination=True,original_DLC_keepalive_not_stopped=True))


if __name__=='__main__':
    try: main()
    except BaseException as error:
        import traceback
        atomic(DEST/'FAILED.json',dict(time=stamp(),error=repr(error),traceback=traceback.format_exc(),no_automatic_recovery=True))
        raise
