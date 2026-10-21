"""Mechanical per-node parent/worker health, no automatic recovery or stopping."""
from r2_common import *
import argparse


def inspect():
    now=dt.datetime.now(dt.timezone.utc);nodes=[];alerts=[]
    for n in read(ROOT/'resources/CLOUD_LATEST.json')['nodes']:
        if n['status']!='Running':continue
        parent=RUN/'nodes'/n['name']/'LIVE.json';launch=ROOT/'provenance'/('launch_'+n['name']+'.json')
        if not parent.exists():
            # Cloud allocation can precede remote startup. Allow ten minutes.
            began=dt.datetime.fromisoformat(n['running_since'].replace('Z','+00:00'))
            if (now-began).total_seconds()>600:alerts.append(dict(type='NODE_PARENT_MISSING',node=n['name'],job=n['job']))
            continue
        d=read(parent);age=(now-dt.datetime.fromisoformat(d['time'])).total_seconds();failed={k:v for k,v in d['children'].items() if v.get('returncode') not in [None,0]}
        nodes.append(dict(node=n['name'],job=n['job'],parent_time=d['time'],age_seconds=age,children=len(d['children']),failures=failed,cpu_percent=d.get('cpu_busy')))
        if age>300:alerts.append(dict(type='NODE_PARENT_STALE',node=n['name'],job=n['job'],last=d['time']))
        if failed:alerts.append(dict(type='NODE_CHILD_NONZERO',node=n['name'],job=n['job'],children=failed))
    return dict(time=stamp(),status='ATTENTION' if alerts else 'HEALTHY',nodes=nodes,alerts=alerts,no_process_or_resource_mutation=True)


def main(once=False):
    failures=0
    while True:
        try:
            d=inspect();atomic(ROOT/'runs/node_health_watch/LIVE.json',d);failures=0
            for a in d['alerts']:
                ident='node_health_'+digest(a)[:24];p=RUN/'failures'/(ident+'.json')
                if not p.exists():atomic(p,dict(status='NODE_HEALTH_ATTENTION',time=stamp(),observation=a,no_automatic_recovery=True))
            if once:print(json.dumps(d,ensure_ascii=False),flush=True);return
        except Exception as error:
            failures+=1
            if failures>=3:
                atomic(RUN/'failures/node_health_watch_reader.json',dict(status='MONITOR_READ_ERROR',time=stamp(),consecutive=failures,error=repr(error)));raise
        time.sleep(60)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--once',action='store_true');a=p.parse_args();main(a.once)
