"""One configurable rejoin phase reminder after all new model workers actually load."""
from r2_common import *
import argparse


def main(args):
    setup('rejoin_first_phase_watch_v2')
    folder=(ROOT/args.folder).resolve();assert folder.is_relative_to(ROOT/'resources/rejoins')
    job=read(folder/'INTENT.json')['job']
    tasks=read(folder/'NEW_RESIDENT_DISPATCH_WRAPPERS.json')['tasks'];assert tasks
    began=dt.datetime.fromisoformat(read(folder/'LEASE_AND_WRAPPERS_ENABLED.json')['time'])
    ready_since=None
    while True:
        owners=[]
        for task in tasks:
            p=RUN/'claims_gpu'/task['id']/'OWNER.json'
            if p.exists():
                owner=read(p);assert owner['hostname'].startswith(job+'-');owners.append(owner)
        now=dt.datetime.now(dt.timezone.utc)
        if len(owners)==len(tasks) and ready_since is None:ready_since=now
        atomic(folder/'PHASE_WATCH_LIVE.json',dict(time=stamp(),loaded=len(owners),expected=len(tasks),
            ready_since=ready_since.isoformat() if ready_since else None,no_handoff_timer=True))
        if ready_since and (now-ready_since).total_seconds()>=300:
            atomic(folder/'FIRST_PHASE_READY.json',dict(time=stamp(),status='READY_FOR_AGENT_ACTUAL_COMPUTE_ACCEPTANCE',
                resident_owners=owners,ready_since=ready_since.isoformat(),expected_workers=len(tasks),
                no_automatic_scientific_acceptance_stop_release_or_handoff=True));return
        if (now-began).total_seconds()>900 and not (folder/'ATTENTION.json').exists():
            atomic(folder/'ATTENTION.json',dict(time=stamp(),status='MODEL_LOADING_DELAY',loaded=len(owners),
                expected=len(tasks),no_automatic_recovery_or_resource_action=True))
        time.sleep(60)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True);main(p.parse_args())
