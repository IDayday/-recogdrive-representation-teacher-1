"""Foreground observation of the retained, read-only cloud monitor.

Does not manage any experimental process or write experimental state. Each
return hands control back to the agent for the semantic checks that a status
poller cannot perform.
"""
from common import *
import argparse
from vlm_core import VOUT
from vlm_semantic import SEM
from vlm_event_watch_v2 import errors


def main(a):
    start = time.monotonic()
    state = VOUT/'live_watch/9cd0eaa282ce86d3_latest.json'
    initial = read(state)
    previous = (initial['primary_full_completed'], initial['semantic_full_completed'])
    while True:
        bad = errors()
        if bad:
            print('WAKE_AGENT_REVIEW_FAILURE', str(bad[0].relative_to(ROOT)), flush=True)
            return
        value = read(state)
        age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(value['time'])).total_seconds()
        if age > 180:
            print('WAKE_AGENT_CLOUD_MONITOR_STALE', age, flush=True)
            return
        for j in value['jobs']:
            if j['status'] != 'Running' or j['remaining_seconds'] < 1200:
                print('WAKE_AGENT_JOB_LIFETIME', json.dumps(j), flush=True)
                return
        counts = (value['primary_full_completed'], value['semantic_full_completed'])
        print(json.dumps(dict(time=value['time'], hours_left=round(min(j['remaining_seconds'] for j in value['jobs'])/3600, 2),
                              primary_full=counts[0], semantic_full=counts[1], gpu=value['counts'])), flush=True)
        if previous[1] < 64 and counts[1] == 64:
            print('WAKE_AGENT_SEMANTIC_FULL_COMPLETE', flush=True)
            return
        if (VOUT/'global_funnel/PARENT_LOCK.json').exists() or (VOUT/'FINAL_ANALYSES_REVIEW_READY.json').exists():
            print('WAKE_AGENT_PARENT_OR_FINAL_PHASE_READY', flush=True)
            return
        if time.monotonic()-start >= a.minutes*60:
            print('WAKE_AGENT_SCHEDULED_SEMANTIC_REVIEW', flush=True)
            return
        previous = counts
        time.sleep(60)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--minutes', type=float, default=10)
    main(p.parse_args())
