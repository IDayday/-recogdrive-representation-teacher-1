"""One bounded scheduling window for a demonstrably starved frozen sweep.

No model/science/runtime changes or process interruption. Only the ordered list
read at natural task boundaries by existing supplementary model lanes changes.
Restore only our exact metadata version, and wake the agent after the window.
"""
from r2_common import *


def counts():
    names=['representation_coarse_v1','fold_and_outcome_probes_v1','behavior_experts_v1','candidate_selector_cv_v1','warm_hard_cv_v1']
    return {n:len(list((ROOT/'runs'/n/'receipts').glob('*.json'))) for n in names}


def main():
    protocol=read(ROOT/'config/BOUNDED_BROAD_BACKGROUND_WINDOW_V1.json');config_path=ROOT/'config/BACKGROUND_GPU_STAGES.json';folder=ROOT/'runs/broad_background_window_v1';assert not (folder/'START.json').exists()
    before=read(config_path);assert digest(before)==protocol['original_config_digest'];assert before['enabled'];assert before['stages']==['runs/fold_and_outcome_probes_v1','runs/representation_coarse_v1']
    changed=dict(before);changed.update(time=stamp(),stages=list(reversed(before['stages'])),bounded_schedule_window='broad_background_window_v1');start=dt.datetime.now(dt.timezone.utc);end=start+dt.timedelta(seconds=protocol['duration_seconds']);old_counts=counts();atomic(config_path,changed)
    atomic(folder/'START.json',dict(time=stamp(),before=before,temporary=changed,before_counts=old_counts,scheduled_end=end.isoformat(),no_inflight_preemption=True))
    while dt.datetime.now(dt.timezone.utc)<end:
        if digest(read(config_path))!=digest(changed):
            atomic(folder/'COMPLETE.json',dict(status='ATTENTION_CONFIG_CHANGED_NOT_OVERWRITTEN',time=stamp(),before_counts=old_counts,after_counts=counts()));return
        atomic(folder/'LIVE.json',dict(time=stamp(),scheduled_end=end.isoformat(),counts=counts(),all_nodes_and_primary_workers_retained=True));time.sleep(60)
    assert digest(read(config_path))==digest(changed);restored=dict(before);restored['time']=stamp();restored['bounded_window_restored_after']='broad_background_window_v1';atomic(config_path,restored)
    atomic(folder/'COMPLETE.json',dict(status='BOUNDED_SCHEDULING_WINDOW_COMPLETE',time=stamp(),duration_seconds=protocol['duration_seconds'],before_counts=old_counts,after_counts=counts(),restored_stages=restored['stages'],no_process_stopped=True,no_scientific_parameters_changed=True))


if __name__=='__main__':main()
