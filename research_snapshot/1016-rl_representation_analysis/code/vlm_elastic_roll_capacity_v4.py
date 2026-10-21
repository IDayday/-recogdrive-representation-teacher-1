"""Legacy rotation additionally requires the user's new 32-free-card policy."""
from common import *
import argparse,subprocess
import vlm_elastic_roll as original
import vlm_elastic_roll_clones as clone_roll
import vlm_elastic_roll_clones_v2 as analysis_roll
import vlm_elastic_roll_clones_v3 as verified_roll
from vlm_elastic_registry import DEST
from repair_queue_v2 import atomic_unique as atomic

WAIT_SCRIPT=Path('/mnt/workspace/dlc-pool-monitor/wait_for_capacity.py')

def capacity_proof():
    pointer=DEST/'capacity_wait/CAPACITY_AVAILABLE_LATEST.json'
    if not pointer.exists():return None
    ref=read(pointer);path=ROOT/ref['path'];assert path.resolve().is_relative_to(DEST)
    assert sha(path)==ref['sha256'];proof=read(path)
    assert proof['exit_code']==0 and proof['wait_script_sha256']==sha(WAIT_SCRIPT)
    r=proof['result'];assert r['event']=='capacity_available' and r['ready']
    assert r['minimum_free_cards']>=32 and r['required_stable_seconds']>=120
    assert r['stable_for_seconds']>=120 and r['minimum_observed_free_cards']>=32
    assert r['last_sample']['free_cards']>=32
    age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(r['checked_at_utc'].replace('Z','+00:00'))).total_seconds()
    return ref if 0<=age<180 else None

def ready():
    missing=analysis_roll.ready()
    if capacity_proof() is None:missing.append('fresh 32-card continuous-120s capacity proof not available; retain legacy nodes')
    return missing

def stop(a):
    assert not ready()
    proof=capacity_proof();assert proof is not None
    # Aggregate availability is only a condition, never a scheduling guarantee.
    result=subprocess.run([sys.executable,'-B',str(WAIT_SCRIPT),'--check','--min-free-cards','32'],
        cwd=ROOT,capture_output=True,text=True,timeout=45)
    assert result.returncode==0,'Live pool query failed; no StopJob requested.'
    snapshot=json.loads(result.stdout);assert snapshot['event']=='snapshot'
    assert snapshot['last_sample']['free_cards']>=32,'Capacity fell below 32; no StopJob requested.'
    atomic(ROOT/a.folder/'CAPACITY_AT_STOP.json',dict(status='PASS',time=stamp(),continuous_proof=proof,
        current_snapshot=snapshot,whole_node_availability_or_reallocation_not_guaranteed=True))
    clone_roll.stop(a)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['inspect','quiesce','resume','stop','confirm'])
    p.add_argument('--legacy-id');p.add_argument('--folder');a=p.parse_args();setup('vlm_repair/capacity_guarded_roll')
    for name in ['EXECUTION.json','ROLL_EXECUTION.json','CLONE_ADMIN_EXECUTION.json',
                 'CLONE_ANALYSIS_MOVE_EXECUTION.json','CLONE_MONITOR_RETRY_EXECUTION.json','CAPACITY_POLICY_EXECUTION.json']:
        for path,h in read(DEST/name)['code_sha256'].items():assert sha(ROOT/path)==h,path
    original.ready=ready;clone_roll.fresh_clone=verified_roll.fresh_clone
    if a.mode=='inspect':print(json.dumps(dict(status='READ_ONLY',missing=ready(),no_stop_requested=True)),flush=True)
    elif a.mode=='resume':original.restore(read(ROOT/a.folder/'QUIESCED.json')['paused_processes']);print('OWNED_PAUSED_PROCESSES_RESUMED')
    elif a.mode=='stop':stop(a)
    else:getattr(original,a.mode)(a)
