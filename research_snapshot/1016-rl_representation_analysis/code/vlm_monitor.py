"""Minute foreground monitoring; never closes queues or releases the retained nodes."""
from common import *
from collections import Counter
from cloud_api import request
from vlm_core import VOUT

def snapshot():
    base=ROOT/'runs/vlm_all_layers_20261016_v1';failures=list(base.glob('failures/*.json'))+list(base.glob('node*/FAILED.json'))
    failures += list((VOUT/'failures').glob('*.json'))
    if failures:raise RuntimeError('Original failure retained: '+str(failures[0]))
    jobs=[]
    for job in read(ROOT/'candidate_repair_v1/CLOUD_READY.json')['jobs']:
        data=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
        created=dt.datetime.fromisoformat(data['GmtCreateTime'].replace('Z','+00:00'))
        remaining=(created+dt.timedelta(minutes=data['JobMaxRunningTimeMinutes'])-dt.datetime.now(dt.timezone.utc)).total_seconds()
        jobs.append(dict(job=job,status=data['Status'],remaining_seconds=remaining,max_minutes=data['JobMaxRunningTimeMinutes'],reserved_minutes=data.get('Settings',{}).get('JobReservedMinutes')))
        assert data['Status']=='Running',jobs[-1]
        if remaining<3600:atomic(VOUT/'LIFETIME_NOTICE.json',dict(time=stamp(),jobs=jobs,checkpoint_handoff_required=True))
        if remaining<1200:raise RuntimeError('Under twenty minutes lifetime: finish checkpoint/unfinished-task manifest; do not release nodes')
    states=[read(p)['status'] for p in (base/'workers').glob('rank[0-9][0-9][0-9].json')]
    value=dict(time=stamp(),jobs=jobs,collection=dict(done=len(list((base/'receipts').glob('*.json'))),total=read(base/'PROTOCOL.json')['tasks']),
        collection_workers=dict(Counter(states)),cells_ready=len(list((VOUT/'cells').glob('*.json'))),cells_total=read(VOUT/'PIVOT_PLAN.json')['expected_cells'],
        pivot_nodes={str(n):read(VOUT/f'pivot/node{n}_status.json') for n in [0,1] if (VOUT/f'pivot/node{n}_status.json').exists()},
        nodes_retained=True,all_heavy_complete=(VOUT/'HEAVY_COMPLETE.json').exists())
    atomic(VOUT/'MONITOR.json',value)
    brief={k:value[k] for k in ['time','collection','collection_workers','cells_ready','cells_total','all_heavy_complete']}
    brief['node_hours_left']=round(min(j['remaining_seconds'] for j in jobs)/3600,2)
    print(json.dumps(brief,ensure_ascii=False),flush=True);return value

if __name__=='__main__':
    setup('vlm_repair/monitor')
    while True:
        try:value=snapshot()
        except (OSError,TimeoutError) as error:print(json.dumps(dict(time=stamp(),transient=type(error).__name__)),flush=True);time.sleep(10);continue
        if value['all_heavy_complete']:break
        time.sleep(60)
