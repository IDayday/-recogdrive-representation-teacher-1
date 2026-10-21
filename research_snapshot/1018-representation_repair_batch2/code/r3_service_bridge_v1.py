"""New compatibility shim only; all third-batch science/output lives next door.

The frozen dispatcher requires handler and claim metadata within batch2. This
adapter changes no old scientific source and reuses the already loaded model.
"""
from r2_common import ROOT,sha
import importlib.util
from pathlib import Path

_MODULES={}


def run(engine,task,pool):
    root=ROOT.parent/'1021-representation_repair_batch3'
    source=(root/task['third_batch_handler']).resolve()
    assert source.is_relative_to(root/'code') and sha(source)==task['third_batch_handler_sha256']
    key=task['third_batch_handler_sha256']
    if key not in _MODULES:
        spec=importlib.util.spec_from_file_location('r3_service_'+key,source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);_MODULES[key]=module
    return _MODULES[key].run(engine,task,pool)
