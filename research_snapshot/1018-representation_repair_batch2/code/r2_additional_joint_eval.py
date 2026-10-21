"""Score the actual frozen joint policy using a verified location-specific path."""
from r2_common import *


def run(engine,task,pool):
    from r2_library_rollouts import block
    point=read(ROOT/task['point'])
    if all(block(part) in ['interface_pre','interface_post'] for policy in point['policies'] for part in policy['model']['parts']):
        from r2_behavior_router_eval import run as execute
    else:
        assert read(ROOT/'provenance/RAW_MULTISITE_ROUTER_ENGINEERING_PASS.json')['status']=='PASS'
        from r2_behavior_router_raw_eval_v1 import run as execute
    return execute(engine,task,pool)
