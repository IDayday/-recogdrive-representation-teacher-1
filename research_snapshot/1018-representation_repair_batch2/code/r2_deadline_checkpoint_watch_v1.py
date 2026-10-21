"""Notify near-expiry boundaries; no drain, stop, claim or cloud mutation."""
from r2_common import *


def main():
    while True:
        snapshot=read(ROOT/'resources/CLOUD_LATEST.json')
        now=dt.datetime.now(dt.timezone.utc)
        for node in snapshot['nodes']:
            if node['status']!='Running' or not node.get('deadline_from_running_time'):continue
            remaining=(dt.datetime.fromisoformat(node['deadline_from_running_time'])-now).total_seconds()
            for label,threshold in [('two_hours',7200),('thirty_minutes',1800)]:
                p=ROOT/'resources/deadline_checkpoints'/node['name']/(label+'.json')
                if remaining<=threshold and not p.exists():
                    atomic(p,dict(time=stamp(),status='DEADLINE_AGENT_REVIEW',node=node,
                        remaining_seconds=remaining,threshold=threshold,
                        no_automatic_resource_or_process_action=True))
        time.sleep(60)


if __name__=='__main__':
    main()
