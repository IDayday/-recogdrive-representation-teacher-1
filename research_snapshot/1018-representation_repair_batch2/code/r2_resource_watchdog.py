"""Mechanical liveness checks only; never stops, releases or restarts a node."""
from r2_common import *


def main():
    while True:
        now=dt.datetime.now(dt.timezone.utc);issues=[];cloud=read(ROOT/'resources/CLOUD_LATEST.json')
        age=(now-dt.datetime.fromisoformat(cloud['time'])).total_seconds()
        if age>300:issues.append(dict(id='cloud_heartbeat',age_seconds=age,last=cloud['time']))
        for node in cloud['nodes']:
            if node['status']!='Running':continue
            path=RUN/'nodes'/node['name']/'LIVE.json'
            if not path.exists():continue # preflight/autojoin may still be in progress
            d=read(path);age=(now-dt.datetime.fromisoformat(d['time'])).total_seconds()
            if age>300:issues.append(dict(id='node_heartbeat_'+node['name'],age_seconds=age,last=d['time']))
            if d.get('failures'):issues.append(dict(id='node_children_'+node['name'],children=d['failures']))
        for issue in issues:
            path=RUN/'failures'/('watchdog_'+issue['id']+'.json')
            if not path.exists():atomic(path,dict(status='ATTENTION',time=stamp(),issue=issue,automatic_recovery=False,automatic_release=False))
        atomic(RUN/'watchdog/LIVE.json',dict(time=stamp(),issues=issues,mechanical_only=True))
        time.sleep(60)


if __name__=='__main__':main()
