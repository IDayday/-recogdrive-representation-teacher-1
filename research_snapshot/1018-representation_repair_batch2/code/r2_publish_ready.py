"""Publish the producer's completed ordered prefix while it builds later points.

Only metadata is copied; the immutable producer remains authoritative. Preserving
its exact task order makes worker cursors safe when its final queue is published.
"""
from r2_common import *


def main():
    base=ROOT/'runs/representation_coarse_v1'
    protocol=read(ROOT/'config/REPRESENTATION_LOCATION_PROTOCOL.json')
    last=-1
    while True:
        if read(base/'producer.json').get('complete'):return
        queue=[];points=0
        for original in protocol['tasks']:
            result=ROOT/'analysis/expert_spaces'/(original['id']+'.json')
            point=base/'points'/(original['id']+'.json')
            if not point.exists():
                if result.exists() and read(result)['status']!='PASS':continue
                break
            descriptor=read(point);panel=descriptor['panel']
            for start in range(0,len(panel),4):
                queue.append(dict(id=original['id']+'_%03d'%start,point=str(point.relative_to(ROOT)),
                                  start=start,end=min(start+4,len(panel))))
            points+=1
        if points!=last:
            # A final producer write can race this publication. The prefix order
            # is identical, and the next pass restores any newer final suffix.
            if read(base/'producer.json').get('complete'):return
            existing=read(base/'tasks.json')
            if len(queue)>len(existing):atomic(base/'tasks.json',queue)
            atomic(base/'PUBLISHED_PREFIX.json',dict(time=stamp(),points=points,tasks=len(queue)))
            last=points
        time.sleep(60)


if __name__=='__main__':main()
