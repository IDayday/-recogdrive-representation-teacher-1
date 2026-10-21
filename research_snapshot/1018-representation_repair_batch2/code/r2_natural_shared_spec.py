"""Compact dispatch metadata around the unchanged frozen natural evaluator."""
from r2_common import *
from r2_frozen_policy_pack_v2 import manifest


def expand(task):
    specification=manifest(task['specification'],task['specification_sha256'])
    assert specification['evaluation_handler']=='code/r2_frozen_policy_pack_v2.py'
    assert specification['evaluation_handler_sha256']==sha(ROOT/specification['evaluation_handler'])
    assert 0<=task['start']<task['end']<=len(specification['panel'])
    return dict(specification,id=task['evaluation_id'],stage=task['stage'],start=task['start'],end=task['end'])


def run(engine,task,pool):
    from r2_frozen_policy_pack_v2 import run as evaluate
    return evaluate(engine,expand(task),pool)
