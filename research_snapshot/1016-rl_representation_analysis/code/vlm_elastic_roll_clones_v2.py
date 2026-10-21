"""Permit legacy rotation once heavy work ends and analysis has moved safely."""
from common import *
import argparse
import vlm_elastic_roll as original
import vlm_elastic_roll_clones as clone_roll
from vlm_elastic_registry import DEST

previous_ready=original.ready

def ready():
    missing=previous_ready();target=str((DEST.parent/'FINAL_ANALYSES_REVIEW_READY.json').relative_to(ROOT))
    marker=DEST/'analysis_move/SERVICE_READY.json'
    if target in missing and marker.exists():
        r=read(marker);s=read(ROOT/r['state_path']);status=read(DEST/'analysis_move/STATUS.json')
        age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(s['time'])).total_seconds()
        assert r['status']=='PASS' and s['pid']==r['pid']
        if s['status'] in ['RUNNING','COMPLETE'] and age<120 and status['old_supervisor_record_resolved']:
            missing.remove(target)
    return missing

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['inspect','quiesce','resume','stop','confirm']);p.add_argument('--legacy-id');p.add_argument('--folder');a=p.parse_args()
    setup('vlm_repair/elastic_roll_clones_v2')
    for name in ['EXECUTION.json','ROLL_EXECUTION.json','CLONE_ADMIN_EXECUTION.json','CLONE_ANALYSIS_MOVE_EXECUTION.json']:
        for path,h in read(DEST/name)['code_sha256'].items():assert sha(ROOT/path)==h,path
    original.ready=ready
    if a.mode=='inspect':print(json.dumps(dict(status='READ_ONLY',missing=ready(),no_stop_requested=True)),flush=True)
    elif a.mode=='resume':original.restore(read(ROOT/a.folder/'QUIESCED.json')['paused_processes']);print('OWNED_PAUSED_PROCESSES_RESUMED')
    elif a.mode=='stop':clone_roll.stop(a)
    else:getattr(original,a.mode)(a)
