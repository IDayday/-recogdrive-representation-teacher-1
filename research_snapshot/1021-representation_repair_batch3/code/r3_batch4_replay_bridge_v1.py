"""Authorized fourth-batch bridge; old scientific implementations stay frozen."""
from r3_common import *


def run(engine,task,pool):
    import importlib.util
    root=ROOT.parent/'1021-representation_distillation_batch4'
    for name,hashed in task['batch4_code_hashes'].items():assert sha(root/'code'/name)==hashed
    if str(root/'code') not in sys.path:sys.path.insert(0,str(root/'code'))
    source=root/'code/d4_replay_service_v1.py'
    spec=importlib.util.spec_from_file_location('d4_replay_service_frozen_v1',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.run(engine,task,pool)
