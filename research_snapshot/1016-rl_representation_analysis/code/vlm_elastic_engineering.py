"""Replay one already completed real validation task without claiming new work."""
from common import *
import argparse,multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from vlm_elastic_registry import BASE,configuration
from repair_queue_v2 import atomic_unique as atomic,init_score_unique

def main(a):
    c=configuration(a.id);folder=ROOT/c['folder'];setup('vlm_repair/elastic_engineering/'+a.id);compatibility()
    import vlm_repair_queue_v6 as module
    paths=sorted((BASE/'receipts').glob('validation_main_a*.json'));assert paths
    receipt=read(paths[0]);path=BASE/'results'/paths[0].name;assert sha(path)==receipt['result_sha256'];original=read(path)
    e=module.Engine();fits=module.Fits()
    with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_score_unique) as pool:
        actual,timing=module.run_task(e,fits,original['task'],BASE,pool)
    assert actual==original['records'],'Expansion worker changed a real trajectory, seed, edit, geometry or score.'
    atomic(folder/'ENGINEERING_PASS.json',dict(status='PASS',time=stamp(),id=a.id,
        source_result=str(path.relative_to(ROOT)),source_result_sha256=sha(path),
        source_receipt=str(paths[0].relative_to(ROOT)),source_receipt_sha256=sha(paths[0]),
        task=original['task'],records=len(actual),all_record_fields_exact=True,
        trajectory_seed_geometry_edits_quality_and_seven_scores_exact=True,
        no_scientific_queue_claimed_or_result_replaced=True,timing=timing,
        frozen_run_task_sha256=sha(ROOT/'code/vlm_repair_queue_v6.py')))
    print('ELASTIC_REAL_VALIDATION_TASK_EXACT_PASS',a.id,len(actual),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--id',required=True);main(p.parse_args())
