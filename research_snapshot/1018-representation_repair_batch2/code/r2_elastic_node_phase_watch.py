"""Mechanical five-minute post-smoke readiness flags, no resource decisions."""
from r2_common import *


def main():
    initial={'peer_a1','peer_a2','peer_b1'}
    while True:
        cloud=read(ROOT/'resources/CLOUD_LATEST.json')
        for n in cloud['nodes']:
            if n['name'] in initial or n['status']!='Running':continue
            smoke=RUN/'nodes'/n['name']/'GPU_SMOKE_PASS.json';flag=ROOT/'runs/elastic_first_phase'/(n['name']+'.json')
            if not smoke.exists() or flag.exists():continue
            d=read(smoke);age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(d['time'])).total_seconds()
            if age>=300:atomic(flag,dict(status='READY_FOR_AGENT_SCIENTIFIC_PHASE_REVIEW',time=stamp(),node=n['name'],job=n['job'],smoke_time=d['time'],elapsed_seconds=age,no_automatic_acceptance_or_background_launch=True))
        time.sleep(60)


if __name__=='__main__':main()
