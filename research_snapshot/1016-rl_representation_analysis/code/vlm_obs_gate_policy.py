"""Freeze deployable gate identities before reading own test observations."""
from common import *
from vlm_obs_qda_gate import OUT
from repair_queue_v2 import atomic_unique as atomic


def test_lock():
    path=OUT/'TEST_LOCK.json';source=read(OUT/'FINAL_LOCK.json')
    policies=list({r['id']:r for r in source['roles'].values()}.values())
    parents=list({r['parent']['id']:r['parent'] for r in policies}.values());virtual=[]
    for p in policies:
        virtual.append(dict(p['parent'],id=p['id'],gate='external_observation_qda_hard',
            observation_gate=p['gate'],underlying_arm_id=p['parent']['id'],
            policy_definition='Use the complete fixed ungated-parent trajectory if the natural-observation risk exceeds the frozen exploration-high quantile; otherwise use the exact frozen Base. No PDMS/GT at runtime.'))
    content=dict(status='FROZEN_BEFORE_OWN_TEST_OBSERVATIONS',time=stamp(),parents=virtual,controls=[],
        underlying_parents=parents,roles={k:r['id'] for k,r in source['roles'].items()},seeds=[0,1,2,3,4],
        source_actual_policy_lock_sha256=sha(OUT/'FINAL_LOCK.json'),policy_parameters_frozen_before_test_features=True)
    if path.exists():
        previous=read(path);assert {k:v for k,v in previous.items() if k!='time'}=={k:v for k,v in content.items() if k!='time'}
        return previous
    atomic(path,content);return content
