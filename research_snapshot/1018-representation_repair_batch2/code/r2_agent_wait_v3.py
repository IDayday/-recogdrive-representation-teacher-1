"""Tool-owned wait following the actual event log across controller migrations.

Keep an independent cursor for every log, preserve all backlog, and verify
resident monitor heartbeats. No cloud, experiment, or resource action.
"""
from r2_common import *
from r2_agent_wait_v2 import heartbeat
import argparse


def log_paths():
    result=[RUN/'control_plane/logs/attention_monitor.log']
    control=read(RUN/'control_plane/LIVE.json')
    if control.get('migration_proof'):
        proof=(ROOT/control['migration_proof']).resolve();assert proof.is_relative_to(ROOT)
        result.append(proof.parent/'logs/attention_monitor.log')
    return list(dict.fromkeys(result))


def main(check=False):
    setup('agent_wait_v3');cursor=ROOT/'runs/attention_monitor/AGENT_CURSOR_V3.json'
    if cursor.exists():offsets=read(cursor)['offsets']
    else:
        previous=ROOT/'runs/attention_monitor/AGENT_CURSOR.json'
        offsets={str((RUN/'control_plane/logs/attention_monitor.log').relative_to(ROOT)):
            read(previous).get('offset',0) if previous.exists() else 0}
    if check:
        health=heartbeat();assert all(v['age_seconds']<300 for v in health)
        paths=log_paths();assert paths[-1].exists()
        print(json.dumps(dict(status='PASS_ACTUAL_LOG_ROUTE_AND_HEARTBEATS',
            logs=[str(p.relative_to(ROOT)) for p in paths],health=health)),flush=True);return
    failures=0
    while True:
        try:
            events=[];resolved_path=ROOT/'provenance/RESOLVED_FAILURES.json'
            resolved=read(resolved_path)['acknowledged'] if resolved_path.exists() else {}
            paths=list(dict.fromkeys([ROOT/k for k in offsets]+log_paths()))
            for path in paths:
                if not path.exists():continue
                key=str(path.relative_to(ROOT));offset=offsets.get(key,0)
                def take():
                    with path.open('rb') as stream:
                        if stream.seek(0,2)<offset:raise RuntimeError('Previously consumed log shrank: '+key)
                        stream.seek(offset);lines=[]
                        while True:
                            line=stream.readline()
                            if not line or not line.endswith(b'\n'):break
                            lines.append(line)
                        return lines
                lines=retry(take)
                for line in lines:
                    if line.strip():
                        record=json.loads(line)
                        for item in record.get('events',[]):
                            failure=item.get('path');ack=resolved.get(failure,{})
                            if item.get('type')=='ERROR' and ack.get('failure_sha256') and (ROOT/failure).exists() and sha(ROOT/failure)==ack['failure_sha256']:continue
                            events.append(dict(source_log=key,source_time=record.get('time'),**item))
                    offset+=len(line)
                offsets[key]=offset
            atomic(cursor,dict(time=stamp(),offsets=offsets,waiter_version=3))
            stale=[v for v in heartbeat() if v['age_seconds']>300]
            if stale:events.append(dict(type='MONITOR_HEARTBEAT_STALE',sources=stale))
            if events:
                print(json.dumps(dict(status='ATTENTION',time=stamp(),events=events),ensure_ascii=False),flush=True);return
            failures=0
        except Exception as error:
            failures+=1
            if failures>=3:
                print(json.dumps(dict(status='WAIT_MONITOR_READ_ERROR',time=stamp(),consecutive=failures,error=repr(error))),flush=True);return 3
        time.sleep(60)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();raise SystemExit(main(a.check))
