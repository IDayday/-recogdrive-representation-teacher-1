"""Mechanical phase/estimated-use reminders for B1; never stop or release work."""
from r2_common import *

DEST=ROOT/'resources/rejoins/peer_b1_20261019T0540'


def main():
    setup('peer_b1_rejoin_watch_v1')
    began=dt.datetime.fromisoformat(read(DEST/'LEASE_AND_WRAPPERS_ENABLED.json')['time'])
    estimate=dt.datetime.fromisoformat(read(DEST/'INTENT.json')['time'])+dt.timedelta(hours=5)
    tasks=read(DEST/'NEW_RESIDENT_DISPATCH_WRAPPERS.json')['tasks']
    ready_since=None
    while True:
        lease=next(n for n in read(ROOT/'resources/NODES.json')['nodes'] if n['name']=='peer_b1')
        if not lease.get('active_for_batch2',True):return
        now=dt.datetime.now(dt.timezone.utc);owners=[]
        for task in tasks:
            path=RUN/'claims_gpu'/task['id']/'OWNER.json'
            if path.exists():
                owner=read(path);assert owner['hostname'].startswith('dlcqdtslnqnytsc7-')
                owners.append(owner)
        if len(owners)==16 and ready_since is None:ready_since=now
        if ready_since and (now-ready_since).total_seconds()>=300 and not (DEST/'FIRST_PHASE_READY.json').exists():
            atomic(DEST/'FIRST_PHASE_READY.json',dict(time=stamp(),status='READY_FOR_AGENT_ACTUAL_COMPUTE_ACCEPTANCE',
                sixteen_new_models_loaded=True,resident_owners=owners,ready_since=ready_since.isoformat(),
                no_automatic_scientific_acceptance_or_resource_action=True))
        if len(owners)<16 and (now-began).total_seconds()>900 and not (DEST/'ATTENTION.json').exists():
            atomic(DEST/'ATTENTION.json',dict(time=stamp(),status='REJOIN_LOADING_DELAY',loaded=len(owners),
                expected=16,no_automatic_restart_or_stop=True))
        atomic(DEST/'WATCH_LIVE.json',dict(time=stamp(),loaded=len(owners),ready_since=ready_since.isoformat() if ready_since else None,
            estimated_use_until=estimate.isoformat(),estimate_not_automatic_handoff=True))
        if now>=estimate:
            atomic(DEST/'FIVE_HOUR_ESTIMATE_ELAPSED.json',dict(time=stamp(),status='REMIND_USER_ESTIMATE_ONLY',
                reason='User expects about fivehours, actualhandoff follows latermessage.',
                no_automatic_process_stop_node_release_or_handoff=True))
            return
        time.sleep(60)


if __name__=='__main__':main()
