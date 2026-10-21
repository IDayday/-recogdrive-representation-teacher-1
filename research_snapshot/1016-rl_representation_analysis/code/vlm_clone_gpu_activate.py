"""Activate verified cloned cards at the unchanged complete-validation boundary."""
from common import *
import argparse
from vlm_elastic_registry import DEST,BASE,configuration
from vlm_elastic_manage import enable
from repair_queue_v2 import atomic_unique as atomic

def main(a):
    for name in ['EXECUTION.json','CLONE_EXECUTION.json','CLONE_ADMIN_EXECUTION.json']:
        for path,h in read(DEST/name)['code_sha256'].items():assert sha(ROOT/path)==h,path
    pending=set(a.id)
    while pending:
        for ident in sorted(pending):
            c=configuration(ident);folder=ROOT/c['folder']
            if not (DEST.parent/'final/PRIMARY_STAGES_APPENDED.json').exists():continue
            if not (DEST/'DYNAMIC_ACCEPTANCE_READY.json').exists():continue
            if not all((folder/name).exists() for name in ['GPU_SMOKE_PASS.json','ENGINEERING_PASS.json','FIVE_MINUTE_PHASE_CHECK.json']):continue
            assert read(folder/'FIVE_MINUTE_PHASE_CHECK.json')['status']=='PASS'
            live=read(folder/'attestations'/read(folder/'ADOPTED_CLONE.json')['job']/'LIVE.json')
            assert live['status']=='RUNNING' and live['authorized_clone_identity']
            assert (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(live['time'])).total_seconds()<120
            protocol=read(BASE/'stages/validation_main/PROTOCOL.json')
            assert len(list((BASE/'receipts').glob('validation_main_a*.json')))==protocol['tasks']
            enable(c);pending.remove(ident)
            atomic(folder/'CLONE_GPU_BOUNDARY_ACCEPTANCE.json',dict(status='PASS',time=stamp(),node=ident,
                original_validation_tasks_complete=protocol['tasks'],all_cards_smoke_pass=c['cards'],
                five_minute_phase_check_sha256=sha(folder/'FIVE_MINUTE_PHASE_CHECK.json'),
                source_sha256=sha(Path(__file__)),only_future_unclaimed_tasks=True))
        if pending:time.sleep(5)
    print('ALL_REQUESTED_CLONED_GPU_WORKERS_ENABLED',','.join(a.id),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--id',action='append',required=True);main(p.parse_args())
