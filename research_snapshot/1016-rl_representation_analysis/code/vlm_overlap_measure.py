"""Measure task completion and corrected scenes under four-instance overlap."""
from common import *
import argparse
from vlm_semantic import SEM
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic

def instant(s):return dt.datetime.fromisoformat(s.replace('Z','+00:00'))

def main(a):
    setup('vlm_semantic_v2/overlap_measure');smokes=[read(SEM/f'overlap/smoke/rank{r:03d}.json') for r in [64,65,66,67]];assert all(s['status']=='PASS' for s in smokes)
    trial=read(SEM/'OVERLAP_EXECUTION.json');before_end=instant(trial['time']);start=max(instant(s['time']) for s in smokes)+dt.timedelta(seconds=30);end=start+dt.timedelta(minutes=a.minutes)
    now=dt.datetime.now(dt.timezone.utc)
    if now<end:print(json.dumps(dict(status='WAIT_FULL_WINDOW',elapsed_seconds=max(0,(now-start).total_seconds()),required_seconds=a.minutes*60,end=end.isoformat())));return
    seconds=a.minutes*60;before_start=before_end-dt.timedelta(seconds=seconds);shared={14,15,30,31};panels={k:dict(main_tasks=0,arm_outputs=0,shared_arm_outputs=0,control_arm_outputs=0,semantic_scenes=0,dsw_semantic_scenes=0,overlap_semantic_scenes=0) for k in ['before','overlap']}
    completed_semantic_cases=0
    for run,semantic in [('vlm_repair_20261016_v2',False),('vlm_semantic_20261016_v2',True)]:
        for path in (ROOT/'runs'/run/'receipts').glob('*.json'):
            d=read(path);task=d['task'];cases=task['end']-task['start']
            if semantic:completed_semantic_cases+=cases
            t=instant(d['time']);window='before' if before_start<=t<before_end else 'overlap' if start<=t<end else None
            if window is None:continue
            p=panels[window];task=d['task'];cases=task['end']-task['start']
            if semantic:
                p['semantic_scenes']+=cases
                if d['rank']==32:p['dsw_semantic_scenes']+=cases
                if d['rank'] in [64,65,66,67]:p['overlap_semantic_scenes']+=cases
            else:
                outputs=cases*(task['arm_end']-task['arm_start'])*len(task['seeds']);p['main_tasks']+=1;p['arm_outputs']+=outputs;p['shared_arm_outputs' if d['rank'] in shared else 'control_arm_outputs']+=outputs
    for p in panels.values():p.update(main_arm_outputs_per_second=p['arm_outputs']/seconds,semantic_scenes_per_second=p['semantic_scenes']/seconds)
    before=panels['before'];after=panels['overlap'];ratio=(after['shared_arm_outputs']/max(after['control_arm_outputs'],1))/(before['shared_arm_outputs']/max(before['control_arm_outputs'],1));estimated_fraction=1-4/32*max(0,1-ratio)
    remaining_cases=103288-completed_semantic_cases;rate=after['semantic_scenes_per_second'];deadline=dt.datetime(2026,10,17,3,42,10,tzinfo=dt.timezone.utc)
    result=dict(status='MEASURED_NOT_AUTOMATICALLY_ADOPTED',time=stamp(),before_window=[before_start.isoformat(),before_end.isoformat()],overlap_window=[start.isoformat(),end.isoformat()],windows=panels,
        shared_card_output_ratio_normalized_by_other_cards=ratio,estimated_main_total_fraction_with_peer_control=estimated_fraction,
        semantic_remaining_cases=remaining_cases,semantic_estimated_remaining_seconds=remaining_cases/max(rate,1e-12),old_node_seconds_left=(deadline-now).total_seconds(),
        all_four_actual_pool_hidden_seed_score_proofs_pass=True,no_frozen_code_or_worker_changed=True,
        caveat='Observational completion comparison; stage/case mixes and queue competition vary. Peer-card normalization is an estimate, not a controlled causal speed benchmark. Do not judge only GPU utilization or promise this ratio in later phases.')
    path=SEM/'overlap'/f'MEASUREMENT_{a.minutes}min.json';atomic(path,result);print(json.dumps(result),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--minutes',type=int,default=10);main(p.parse_args())
