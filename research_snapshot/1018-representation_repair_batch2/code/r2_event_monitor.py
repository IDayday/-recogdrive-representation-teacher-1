"""Mechanical event wait for agent attention; no experimental decisions.

Reports first new error, cloud allocation change, deadline warning, or configured
stage milestone. A persistent seen set prevents repeated wake-ups for old events.
"""
from r2_common import *


def main():
    folder=ROOT/'runs/attention_monitor';state_path=folder/'SEEN.json'
    state=read(state_path) if state_path.exists() else dict(events=[],cloud={})
    seen=set(state['events']);cloud_state=state['cloud']
    while True:
        events=[]
        for name in ['failures','failures_cpu','failures_gpu']:
            for path in (RUN/name).glob('*.json'):
                ident='error:'+str(path.relative_to(ROOT))
                if ident not in seen:events.append(dict(id=ident,type='ERROR',path=str(path.relative_to(ROOT))))
        cloud=read(ROOT/'resources/CLOUD_LATEST.json')
        for node in cloud['nodes']:
            previous=cloud_state.get(node['name'])
            if previous and previous!=node['status']:
                ident='cloud:'+node['name']+':'+node['status']+':'+str(node.get('running_since'))
                if ident not in seen:events.append(dict(id=ident,type='CLOUD_STATE_CHANGED',node=node['name'],job=node['job'],before=previous,after=node['status']))
            cloud_state[node['name']]=node['status']
            if node.get('remaining_seconds',1e12)<12*3600:
                key='deadline:'+node['name']+':12h'
                if key not in seen:events.append(dict(id=key,type='DEADLINE',node=node['name'],remaining_seconds=node['remaining_seconds']))
        live=read(RUN/'control_plane/LIVE.json')
        if (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(live['time'])).total_seconds()>300:
            key='control_stale:'+live['time']
            if key not in seen:events.append(dict(id=key,type='CONTROL_HEARTBEAT_STALE',last=live['time']))
        milestones=read(ROOT/'config/ATTENTION_MILESTONES.json')['milestones']
        for milestone in milestones:
            ident=milestone['id']
            if ident in seen:continue
            count=len(list((ROOT/milestone['folder']).glob(milestone['pattern'])))
            if count>=milestone['minimum']:events.append(dict(id=ident,type='MILESTONE',count=count,description=milestone['description']))
        if events:
            seen.update(e['id'] for e in events);atomic(state_path,dict(time=stamp(),events=sorted(seen),cloud=cloud_state))
            print(json.dumps(dict(status='ATTENTION',time=stamp(),events=events),ensure_ascii=False),flush=True)
        atomic(state_path,dict(time=stamp(),events=sorted(seen),cloud=cloud_state))
        time.sleep(60)


if __name__=='__main__':main()
