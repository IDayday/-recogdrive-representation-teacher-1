"""Retire exactly the two old metadata-only node health readers for handoff."""
from r2_common import *
import psutil


def main():
    assert socket.gethostname().startswith('dlcrnshl7t4hcmoy-')
    targets={'per_node_parent_and_child_mechanical_health':'code/r2_node_health_watch.py',
        'resource_liveness_watchdog':'code/r2_resource_watchdog.py'}
    live=read(RUN/'control_plane/LIVE.json');assert live['node']=='self_0'
    folder=ROOT/'resources/handoffs/peer_b1_20261019'
    assert not (folder/'HEALTH_METADATA_RETIRED.json').exists()
    records=[]
    for name,script in targets.items():
        state=live['children'][name];assert state['returncode'] is None
        p=psutil.Process(state['pid']);assert p.ppid()==live['pid'] and not p.children(recursive=True)
        assert p.uids().real==os.getuid() and str(ROOT/script) in p.cmdline()
        records.append(dict(name=name,pid=p.pid,created=p.create_time(),cmdline=p.cmdline(),uid=p.uids().real,source=script))
    atomic(folder/'HEALTH_METADATA_RETIRE_INTENT.json',dict(time=stamp(),records=records,no_scientific_children=True))
    for r in records:
        p=psutil.Process(r['pid']);assert p.create_time()==r['created'] and p.cmdline()==r['cmdline'];p.terminate()
    end=time.monotonic()+20
    while True:
        remaining=[]
        for r in records:
            try:
                p=psutil.Process(r['pid']);assert p.create_time()==r['created']
                if p.status()!=psutil.STATUS_ZOMBIE:remaining.append(r['pid'])
            except psutil.NoSuchProcess:pass
        if not remaining:break
        assert time.monotonic()<end,remaining;time.sleep(.1)
    atomic(folder/'HEALTH_METADATA_RETIRED.json',dict(status='PLANNED_METADATA_READER_RETIREMENT',time=stamp(),records=records,
        replacement='Ownership-filtered wrappers of same frozen health functions. No computation or node stopped.'))
    print('EXACT_HEALTH_METADATA_PAIR_RETIRED')


if __name__=='__main__':main()
