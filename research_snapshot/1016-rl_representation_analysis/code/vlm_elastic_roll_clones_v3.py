"""Legacy rolling with actual clone IDs and exactly resolved command failures."""
from common import *
import argparse
import vlm_elastic_roll as original
import vlm_elastic_roll_clones as clone_roll
import vlm_elastic_roll_clones_v2 as analysis_roll
from vlm_clone_watch_v2 import resolved
from vlm_elastic_registry import DEST

def fresh_clone(c):
    folder=ROOT/c['folder'];lease=read(folder/'ADOPTED_CLONE.json')
    assert lease['confirmed_max_minutes']>=4320 and lease['original_config_sha256']==sha(folder/'CONFIG.json')
    live=read(folder/'attestations'/lease['job']/'LIVE.json');state=read(folder/'STATUS.json')
    assert live['job']==lease['job'] and live['authorized_clone_identity'] and live['core_pid']==state['pid']
    assert live['status']==state['status']=='RUNNING'
    assert all((dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(x['time'])).total_seconds()<120 for x in [live,state])
    for sub in ['failures','clone_wrapper_failures','command_failures']:
        assert not [p for p in (folder/sub).glob('*.json') if not resolved(p)]
    for name in ['PREFLIGHT.json','GPU_SMOKE_PASS.json','ENGINEERING_PASS.json']:assert read(folder/name)['status']=='PASS'
    assert read(folder/'ENGINEERING_PASS.json')['all_record_fields_exact']
    assert read(folder/'GPU_ENABLED.json')['status']=='ENABLED'
    return dict(node=c['id'],job=lease['job'],cards=c['cards'],lease=lease,
        live_sha256=sha(folder/'attestations'/lease['job']/'LIVE.json'),state_time=state['time'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['inspect','quiesce','resume','stop','confirm']);p.add_argument('--legacy-id');p.add_argument('--folder');a=p.parse_args()
    setup('vlm_repair/elastic_roll_clones_v3')
    for name in ['EXECUTION.json','ROLL_EXECUTION.json','CLONE_ADMIN_EXECUTION.json','CLONE_ANALYSIS_MOVE_EXECUTION.json','CLONE_MONITOR_RETRY_EXECUTION.json']:
        for path,h in read(DEST/name)['code_sha256'].items():assert sha(ROOT/path)==h,path
    original.ready=analysis_roll.ready;clone_roll.fresh_clone=fresh_clone
    if a.mode=='inspect':print(json.dumps(dict(status='READ_ONLY',missing=original.ready(),no_stop_requested=True)),flush=True)
    elif a.mode=='resume':original.restore(read(ROOT/a.folder/'QUIESCED.json')['paused_processes']);print('OWNED_PAUSED_PROCESSES_RESUMED')
    elif a.mode=='stop':clone_roll.stop(a)
    else:getattr(original,a.mode)(a)
