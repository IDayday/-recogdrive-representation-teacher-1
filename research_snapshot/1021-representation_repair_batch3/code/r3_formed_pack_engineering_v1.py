"""DSW-only engineering coverage of every formed schedule pack, never screening.

Uses two fixed training examples and all five noises. Weak gains do not remove
any candidate. One retained model and two scoring processes serve all packs.
"""
from r3_common import *
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import socket
import traceback


def main():
    setup('formed_pack_engineering_v1');compatibility()
    import psutil
    import torch
    from vlm_intervene_v4 import Engine
    from r3_runtime import init_scorer
    from r3_formed_rollout_v1 import run as evaluate
    from r3_formed_audit_v1 import audit
    stage=ROOT/'runs/formed_pack_engineering_v1';stage.mkdir(parents=True,exist_ok=True)
    assert not (stage/'MASTER_PASS.json').exists()
    assert socket.gethostname()==read(ROOT/'resources/DSW_PREFLIGHT_V1.json')['hostname']
    assert torch.cuda.device_count()==1 and psutil.virtual_memory().available>32*(1<<30)
    free,total=torch.cuda.mem_get_info();assert free>70*(1<<30)
    atomic(stage/'PREFLIGHT.json',dict(time=stamp(),hostname=socket.gethostname(),cpu_affinity=len(os.sched_getaffinity(0)),memory_available=psutil.virtual_memory().available,
                                    device=torch.cuda.get_device_properties(0).name,free_gpu_bytes=free,total_gpu_bytes=total,no_existing_process_signals=True))
    schedule_path=ROOT/'manifests/FORMED_SCHEDULE_DRAFT_V1.json';schedule=read(schedule_path)
    catalog_path=ROOT/schedule['catalog'];assert sha(catalog_path)==schedule['catalog_sha256'];catalog=read(catalog_path);by_id={e['id']:e for e in catalog['entries']}
    admission_path=ROOT/'provenance/FORMED_RUNTIME_MULTI_DEVICE_ADMISSION.json';admission=read(admission_path)
    assert admission['status']=='PASS_FORMED_RUNTIME_MULTI_DEVICE'
    for name,hashed in admission['code_hashes'].items():assert sha(ROOT/'code'/name)==hashed
    checkpoint=read(ROOT/'manifests/first42_v1.json')['checkpoint_sha256'];packs=[]
    for part in schedule['packs']:
        path=ROOT/'configs/formed_packs_v1'/(part['id']+'.json')
        definition=dict(candidate_scope='formed',checkpoint_sha256=checkpoint,entries=[by_id[i] for i in part['entries']],
                        runtime_admission=str(admission_path),runtime_admission_sha256=sha(admission_path),catalog_sha256=schedule['catalog_sha256'],
                        schedule_sha256=sha(schedule_path),id=part['id'],full_evaluation_required_without_unresolved_prescreen=True)
        if path.exists():assert read(path)==definition
        else:atomic(path,definition)
        packs.append(dict(id=part['id'],path=str(path),sha256=sha(path),entries=len(part['entries'])))
    atomic(stage/'CONFIG.json',dict(time=stamp(),schedule_sha256=sha(schedule_path),packs=packs,indices=[60,1],seeds=[0,1,2,3,4],
            engineering_only=True,no_outcome_based_candidate_filtering=True,source_sha256=sha(Path(__file__)),admitted_code_hashes=admission['code_hashes']))
    engine=Engine();rows=BATCH1/'manifests/natural_s0.json';prior=ROOT/'analysis/first42_engineering_v2/SUMMARY.json';completed=[];began=time.monotonic()
    with ProcessPoolExecutor(max_workers=2,mp_context=mp.get_context('spawn'),initializer=init_scorer) as pool:
        for pack in packs:
            folder=stage/pack['id'];proof_path=folder/'AUDIT.json'
            if proof_path.exists():
                proof=read(proof_path);assert proof['status']=='PASS_GENERIC_CPU_AUDIT';completed.append(dict(id=pack['id'],audit_sha256=sha(proof_path),resumed=True));continue
            atomic(stage/'LIVE.json',dict(status='COMPUTING_ENGINEERING_ONLY',time=stamp(),pid=os.getpid(),pack=pack['id'],completed=len(completed),total=len(packs)))
            task=dict(id=pack['id'],stage=str(folder.relative_to(ROOT)),pack=pack['path'],pack_sha256=pack['sha256'],rows=str(rows),rows_sha256=sha(rows),
                      indices=[60,1],seeds=[0,1,2,3,4],cohort='navtrain',engineering=True,first42_summary=str(prior),first42_summary_sha256=sha(prior))
            result_path=folder/'results'/(pack['id']+'.json')
            result=evaluate(engine,task,pool) if not result_path.exists() else dict(path=str(result_path.relative_to(ROOT)),sha256=sha(result_path),resumed=True)
            proof=audit(ROOT/result['path']);atomic(proof_path,proof);engine.verify_engine()
            completed.append(dict(id=pack['id'],entries=pack['entries'],audit_sha256=sha(proof_path),result=result))
    atomic(stage/'MASTER_PASS.json',dict(status='PASS_ALL_FORMED_PACKS_ENGINEERING_NOT_FULL_EVALUATION',time=stamp(),packs=len(completed),candidate_identities=len(by_id),
        covered_training_examples=2,seeds=[0,1,2,3,4],completed=completed,seconds=time.monotonic()-began,no_outcome_based_candidate_filtering=True,
        formal_expansion_not_started=True,teacher_snapshot_created=False))
    print(json.dumps(dict(event='ALL_FORMED_PACKS_ENGINEERING_COMPLETE',packs=len(completed),candidate_identities=len(by_id))),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        atomic(ROOT/'runs/formed_pack_engineering_v1'/'FAILED.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        raise
