"""Tool-owned event wait with independent monitor-heartbeat supervision.

No scientific judgment or automatic resource action. Silence is allowed while
healthy monitors work; a dead DLC event monitor or DSW cloud reader wakes us.
"""
from r2_common import *
import argparse


def heartbeat():
    result=[]
    for name,path in [('DLC_event_monitor',ROOT/'runs/attention_monitor/SEEN.json'),('DLC_control_supervisor',RUN/'control_plane/LIVE.json'),('DSW_cloud_monitor',ROOT/'resources/CLOUD_LATEST.json')]:
        value=read(path);age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(value['time'])).total_seconds();result.append(dict(name=name,age_seconds=age,last=value['time']))
    return result


def main(check=False):
    setup('agent_wait_v2');path=RUN/'control_plane/logs/attention_monitor.log';cursor_path=ROOT/'runs/attention_monitor/AGENT_CURSOR.json';offset=read(cursor_path).get('offset',0) if cursor_path.exists() else 0;failures=0
    if check:
        status=heartbeat();assert all(v['age_seconds']<300 for v in status);print(json.dumps(dict(status='HEARTBEAT_PASS',sources=status)),flush=True);return
    while True:
        try:
            events=[]
            if path.exists():
                def take():
                    with path.open() as stream:stream.seek(offset);return stream.readlines(),stream.tell()
                lines,position=retry(take)
                if lines:
                    resolved_path=ROOT/'provenance/RESOLVED_FAILURES.json';resolved=read(resolved_path)['acknowledged'] if resolved_path.exists() else {}
                    for line in lines:
                        if not line.strip():continue
                        record=__import__('json').loads(line)
                        for item in record.get('events',[]):
                            failure=item.get('path');ack=resolved.get(failure,{})
                            if item.get('type')=='ERROR' and ack.get('failure_sha256') and (ROOT/failure).exists() and sha(ROOT/failure)==ack['failure_sha256']:continue
                            events.append(dict(source_time=record.get('time'),**item))
                    offset=position;atomic(cursor_path,dict(time=stamp(),offset=offset,waiter_version=2))
            health=heartbeat();stale=[v for v in health if v['age_seconds']>300]
            if stale:events.append(dict(type='MONITOR_HEARTBEAT_STALE',sources=stale))
            if events:print(__import__('json').dumps(dict(status='ATTENTION',time=stamp(),events=events)),flush=True);return
            failures=0
        except Exception as error:
            failures+=1
            if failures>=3:print(__import__('json').dumps(dict(status='WAIT_MONITOR_READ_ERROR',time=stamp(),consecutive=failures,error=repr(error))),flush=True);return 3
        time.sleep(60)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();raise SystemExit(main(a.check))
