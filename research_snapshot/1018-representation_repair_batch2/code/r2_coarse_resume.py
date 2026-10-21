"""Recover the original interrupted wide sweep producer on a DLC controller.

Preserve all existing points, ordering and results. Panel caching only avoids
rehashing the same success bank at each location; the sampling rule is identical.
"""
from r2_common import *
from r2_coarse_producer import balanced,arms_from_fits
from r2_resume_support import enqueue


def main():
    setup('coarse_producer_resume')
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality'])
    explore=np.array([r['subset']=='exploration' for r in rows]);high=np.flatnonzero(explore&(q>.9));middle=np.flatnonzero(explore&(q>=.7)&(q<=.9))
    original=read(ROOT/'config/REPRESENTATION_LOCATION_PROTOCOL.json')['tasks'];base=ROOT/'runs/representation_coarse_v1'
    queue=read(base/'tasks.json');known={t['id'] for t in queue};groups={};panels={};handled=set();skipped=[];points=0
    def publish(complete=False):
        atomic(base/'tasks.json',queue)
        atomic(base/'producer.json',dict(status='PRODUCER_COMPLETE' if complete else 'PRODUCING_RESUMED',complete=complete,
               tasks=len(queue),points=points,handled=len(handled),expected=len(original),ineligible=skipped,time=stamp(),
               resumed_from_interruption=True,producer_version='code/r2_coarse_resume.py'))
    while len(handled)<len(original):
        changed=False
        for task in original:
            ident=task['id']
            if ident in handled:continue
            path=ROOT/'analysis/expert_spaces'/(ident+'.json')
            if not path.exists():continue
            result=read(path);handled.add(ident);changed=True
            if result['status']!='PASS':skipped.append(dict(id=ident,status=result['status']));continue
            point=base/'points'/(ident+'.json')
            if point.exists():descriptor=read(point)
            else:
                name=task['responsibility_meta'];expert=task['expert'];key=(name,expert)
                if key not in panels:
                    if name not in groups:
                        meta=read(ROOT/name)
                        with np.load(ROOT/meta['path']) as z:groups[name]=(np.array(z['global_indices']),np.array(z['responsibility']))
                    indices,responsibility=groups[name];dominant=responsibility.argmax(1)==expert
                    salt=dict(system=name,expert=expert,panel=20261018)
                    own=balanced(indices[dominant],rows,16,salt)
                    if len(own)<16:own += [int(indices[i]) for i in np.argsort(-responsibility[:,expert]) if int(indices[i]) not in own][:16-len(own)]
                    other=balanced([i for i in indices[~dominant] if i not in own],rows,8,salt)
                    success=balanced(high,rows,4,salt);mid=balanced(middle,rows,4,salt)
                    panel=own+other+success+mid;assert len(panel)==len(set(panel))
                    panels[key]=(panel,dict(own=own,other=other,success=success,intermediate=mid))
                panel,partitions=panels[key]
                descriptor=dict(id=ident,task=task,fit_metadata=result['fits'],arms=arms_from_fits(result['fits']),
                                panel=panel,seeds=[0],panel_partitions=partitions,training_only=True,actual_outcome_cv=False)
                atomic(point,descriptor)
            for start in range(0,len(descriptor['panel']),4):
                enqueue(queue,known,dict(id=ident+'_%03d'%start,point=str(point.relative_to(ROOT)),start=start,end=min(start+4,len(descriptor['panel']))))
            points+=1
            if points%32==0:publish()
        if changed:publish()
        if len(handled)<len(original):time.sleep(30)
    publish(True)
    assert len(queue)==len({t['id'] for t in queue})
    print(json.dumps(dict(status='PRODUCER_COMPLETE',points=points,tasks=len(queue))),flush=True)


if __name__=='__main__':main()
