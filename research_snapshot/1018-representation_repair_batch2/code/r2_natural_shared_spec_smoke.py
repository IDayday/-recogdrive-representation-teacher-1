"""Real output equality for shared dispatch metadata, on exploration only."""
from r2_common import *


def run(engine,task,pool):
    from r2_natural_shared_spec import expand,run as compact
    from r2_frozen_policy_pack_v2 import run as evaluate
    source=read(ROOT/'runs/frozen_pack_engineering_v1/tasks.json')[0]['evaluation']
    assert source['mode']=='engineering'
    expanded=expand(task['compact_task'])
    reference=dict(source,id=task['id']+'_reference',stage=task['stage'])
    assert {k:v for k,v in expanded.items() if k not in ['id','stage','evaluation_handler','evaluation_handler_sha256']}=={k:v for k,v in reference.items() if k not in ['id','stage']}
    before=evaluate(engine,reference,pool)
    after=compact(engine,task['compact_task'],pool)
    left=read(ROOT/before['path']);right=read(ROOT/after['path'])
    assert left['records']==right['records']
    path=ROOT/'provenance/NATURAL_SHARED_SPEC_ENGINEERING_PASS.json'
    atomic(path,dict(status='PASS',time=stamp(),before=before,after=after,records_per_runtime=len(left['records']),
        all_trajectories_seeds_real_scores_and_decisions_exact=True,only_dispatch_metadata_changed=True,
        evaluation_handler='code/r2_frozen_policy_pack_v2.py',evaluation_handler_sha256=sha(ROOT/'code/r2_frozen_policy_pack_v2.py'),
        actual_exploration_inputs_only=True,validation_accessed=False,test_accessed=False))
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),result=after)
