"""Compact metadata adapter for the exact shared-scene policy executor."""
from r2_common import *


def run(engine,task,pool):
    assert sha(ROOT/task['definition'])==task['definition_sha256']
    definition=read(ROOT/task['definition']);assert definition['id']==task['id'] and definition['stage']==task['stage']
    assert sha(ROOT/'code/r2_policy_cohort.py')==task['executor_sha256']
    from r2_policy_cohort import run as execute
    return execute(engine,definition,pool)
