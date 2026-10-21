"""Mechanical readiness flags five minutes after new supplementary launches."""
from r2_common import *


def main():
    while True:
        for name in ['peer_b2','self_0','self_1']:
            start=RUN/'background_supervisor'/name/'retained_overlap_v1/START.json';flag=ROOT/'runs/elastic_background_first_phase'/(name+'.json')
            if not start.exists() or flag.exists():continue
            d=read(start);age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(d['time'])).total_seconds()
            if age>=300:atomic(flag,dict(status='READY_FOR_AGENT_BACKGROUND_PHASE_REVIEW',time=stamp(),node=name,elapsed_seconds=age,devices=d['devices'],no_automatic_scientific_acceptance=True))
        time.sleep(60)


if __name__=='__main__':main()
