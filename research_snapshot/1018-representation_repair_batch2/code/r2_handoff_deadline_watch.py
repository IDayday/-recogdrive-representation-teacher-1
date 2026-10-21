"""Mechanical handoff reminders only; never stop or release a resource."""
from r2_common import *


def main():
    path = ROOT/'resources/handoffs/peer_b1_20261019/INTENT.json'
    intent = read(path); folder = path.parent
    while True:
        now = dt.datetime.now(dt.timezone.utc)
        for key, value in intent['reminders_UTC'].items():
            if now >= dt.datetime.fromisoformat(value) and not (folder/(key+'.json')).exists():
                atomic(folder/(key+'.json'), dict(time=stamp(), job=intent['job'],
                    status='SCHEDULED_HANDOFF_REQUIRES_AGENT_ATTENTION', reminder=key,
                    deadline=intent['handoff_deadline_UTC'], no_automatic_stop_or_release=True))
        if (folder/'ACCEPTED_EMPTY_FOR_OWNER.json').exists(): return
        time.sleep(60)


if __name__ == '__main__': main()
