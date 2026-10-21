"""Exact adapter-failure resolution and fresh clone execution evidence."""
from common import *
from vlm_elastic_registry import DEST

def age(value):
    return (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(value['time'])).total_seconds()

def adapter_failure_resolved(path):
    ledger=DEST/'RESOLVED_ADAPTER_FAILURES.json'
    if not ledger.exists():return False
    for record in read(ledger)['records']:
        if (ROOT/record['marker']).resolve()!=path.resolve():continue
        if sha(path)!=record['failure_sha256']:return False
        proof=ROOT/record['proof'];service=ROOT/record['service_status']
        if not proof.exists() or sha(proof)!=record['proof_sha256'] or read(proof)['status']!='PASS':return False
        if not service.exists():return False
        state=read(service)
        return state['status']=='RUNNING' and state['pid']==record['service_pid'] and age(state)<120
    return False

def fresh_clone(config):
    folder=ROOT/config['folder'];lease=read(folder/'ADOPTED_CLONE.json')
    assert lease['confirmed_max_minutes']>=4320 and lease['original_config_sha256']==sha(folder/'CONFIG.json')
    live=read(folder/'attestations'/lease['job']/'LIVE.json');state=read(folder/'STATUS.json')
    assert live['job']==lease['job'] and live['authorized_clone_identity'] and live['core_pid']==state['pid']
    assert live['status']=='RUNNING' and state['status']=='RUNNING' and max(age(live),age(state))<120
    for sub in ['failures','clone_wrapper_failures','command_failures']:assert not list((folder/sub).glob('*.json'))
    assert read(folder/'PREFLIGHT.json')['status']=='PASS'
    assert read(folder/'GPU_SMOKE_PASS.json')['status']=='PASS'
    assert read(folder/'ENGINEERING_PASS.json')['all_record_fields_exact']
    assert read(folder/'GPU_ENABLED.json')['status']=='ENABLED'
    return dict(node=config['id'],job=lease['job'],cards=config['cards'],lease=lease,
        live_sha256=sha(folder/'attestations'/lease['job']/'LIVE.json'),state_time=state['time'])
