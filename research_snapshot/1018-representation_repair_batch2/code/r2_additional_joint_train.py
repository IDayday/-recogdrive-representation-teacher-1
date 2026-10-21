"""Choose a verified execution path for a frozen heterogeneous bank."""
from r2_common import *


def run(engine,task,pool):
    from r2_library_rollouts import block
    bank=read(ROOT/task['selection'])
    if all(block(p) in ['interface_pre','interface_post'] for p in bank['arms']):
        from r2_behavior_router_v2_nativecache import run as execute
    else:
        assert read(ROOT/'provenance/RAW_MULTISITE_ROUTER_ENGINEERING_PASS.json')['status']=='PASS'
        from r2_behavior_router_raw_locations_v1 import run as execute
    return execute(engine,task,pool)
