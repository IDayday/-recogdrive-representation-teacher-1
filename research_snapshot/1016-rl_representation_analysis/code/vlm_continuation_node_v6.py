"""Cold-resume only unfinished phases; all launch logs belong to the new run."""
from common import *
import argparse,subprocess,traceback
from repair_queue_v2 import atomic_unique as atomic
from vlm_core import VOUT
from vlm_semantic import SEM

def pending(base):
    return not (base/'tasks.json').exists() or len(read(base/'tasks.json'))!=len(list((base/'receipts').glob('*.json')))

def commands(node):
    original=ROOT/'runs/vlm_repair_20261016_v2';semantic=ROOT/'runs/vlm_semantic_20261016_v2'
    names={}
    if pending(original) or not (VOUT/'global_funnel/PARENT_LOCK.json').exists():
        names['repair_original']=['vlm_repair_queue_v6.py','node','--node',str(node),'--workers','16','--run','vlm_repair_20261016_v2']
    # This verified launcher waits for the original queue and stays open for all
    # future stages, including final ungated and corrected-semantic stages.
    names['repair_next_waiter']=['vlm_wait_launch_v6.py','--node',str(node)]
    if pending(VOUT/'scan'):
        names['scan']=['vlm_scan_queue.py','node','--node',str(node),'--workers','16','--threads','4']
    if any(not (VOUT/'scan/receipts'/(t['id']+'.json')).exists() for t in read(VOUT/'FULL_GRID_SCHEDULE.json')['canonical']):
        names['canonical_scan']=['vlm_core_scan.py','node','--node',str(node)]
    # Launch controllers separately into NEW append-only logs, avoiding the old
    # host's LAUNCHED.json and preserving all original process identities.
    if node==0 and len(list((VOUT/'development').glob('*.json')))<62:
        names['funnel']=['vlm_funnel.py']
    if node==1:
        if not (VOUT/'global_funnel/PARENT_LOCK.json').exists():
            names['replay']=['vlm_replay.py'];names['residual']=['vlm_residual_candidates.py']
        if not (VOUT/'global_funnel/FINAL_CANDIDATE_LOCK.json').exists():names['global']=['vlm_global_funnel_v6.py']
        if pending(VOUT/'scan'):names['schedule']=['vlm_scan_schedule.py','follow']
        if not (VOUT/'final/PRIMARY_INFERENCE_COMPLETE.json').exists():names['final_driver']=['vlm_final_driver.py']
        if not any((SEM/'repair'/m).exists() for m in ['INFERENCE_COMPLETE.json','NO_COMPETITIVE_CANDIDATES.json']):
            names['semantic_repair']=['vlm_semantic_repair_v3.py']
        if not (VOUT/'UNGATED_TEST_DIAGNOSTICS_COMPLETE.json').exists():names['ungated_final']=['vlm_ungated_final.py']
    if len(list((semantic/'receipts').glob('*.json')))!=6456:
        names['semantic_gap']=['vlm_semantic_collect.py','node','--node',str(node)]
    if node==0:
        if not (SEM/'ANALYSIS_EXECUTION.json').exists():names['semantic_analysis']=['vlm_semantic_analysis.py']
        if not (VOUT/'POSTCOMPUTE_REVIEW_READY.json').exists():names['postcompute']=['vlm_postcompute.py']
    for kind in ['rapid','scan']:
        if len(list((SEM/kind/'receipts').glob('*.json')))!=64:
            names['semantic_'+kind]=['vlm_semantic_cpu.py','node','--node',str(node),'--kind',kind,'--workers','8']
    if pending(VOUT/'scan'):
        names['scan_spare']=['vlm_scan_spare.py','node','--node',str(node)]
    if node==0 and not (VOUT/'FINAL_ANALYSES_REVIEW_READY.json').exists():
        names['analysis_finalize']=['vlm_analysis_finalize.py']
    # Same disjoint ranks and frozen mathematical kernels. Start extra only if
    # corrected full grids remain; actual new-device numeric smokes are reset.
    if len(list((SEM/'scan/receipts').glob('*.json')))!=64:
        names['semantic_scan_extra']=['vlm_semantic_cpu_extra.py','--node',str(node)]
        names['semantic_scan_wave']=['vlm_semantic_cpu_wave.py','--node',str(node)]
    return names

def main(a):
    names=commands(a.node)
    late=VOUT/'late_token_coverage';qda=VOUT/'qda_neighbor_repair'
    if not any((late/name).exists() for name in ['INFERENCE_COMPLETE.json','NO_COMPETITIVE_CANDIDATES.json']):
        names['late_qualifiers']=['vlm_late_selection.py','node','--node',str(a.node),'--workers','16','--threads','2',
            '--launch',str(Path(a.resume)/'late_qualifiers'/f'node{a.node}')]
        if a.node==1:
            if not (late/'SELECTION_LOCK.json').exists():names['late_selector']=['vlm_late_selection.py','controller']
            names['late_repair']=['vlm_late_repair.py']
    if a.node==1 and not any((qda/name).exists() for name in ['INFERENCE_COMPLETE.json','NO_COMPETITIVE_CANDIDATES.json']):names['qneighbor_repair']=['vlm_qneighbor_repair_v2.py']
    if a.node==0:
        if not (VOUT/'ALL_BATCHES_ANALYSES_REVIEW_READY.json').exists():names['all_finalize']=['vlm_all_finalize.py']
        if not (VOUT/'ALL_FOUR_BATCHES_ANALYSES_REVIEW_READY.json').exists():names['four_finalize']=['vlm_four_finalize.py']
        if not (VOUT/'FULL_ORIGINAL_ANALYSIS_ACCEPTANCE_LATEST.json').exists():names['full_analysis_accept']=['vlm_full_analysis_waiter.py']
    # Fifth-batch model features remain on the existing DSW one-card collector.
    # Only CPU selection/test production/finalization resume here, in new logs.
    if a.node==0:
        obs=VOUT/'observation_qda_gate'
        if not any((obs/name).exists() for name in ['FINAL_LOCK.json','NO_COMPETITIVE_CANDIDATES.json']):
            names['obs_gate_prepare']=['vlm_obs_qda_gate.py']
        if not any((obs/name).exists() for name in ['INFERENCE_COMPLETE.json','NO_COMPETITIVE_CANDIDATES.json']):
            names['obs_gate_test']=['vlm_obs_gate_test.py']
        if not (VOUT/'ALL_FIVE_BATCHES_ANALYSES_REVIEW_READY.json').exists():
            names['five_finalize']=['vlm_five_finalize.py']
    wrapped={'global','final_driver','semantic_repair','postcompute','analysis_finalize','all_finalize','four_finalize','late_repair','qneighbor_repair','obs_gate_test','five_finalize'}
    for name in wrapped&names.keys():
        command=names[name];assert len(command)==1
        names[name]=['vlm_resume_frozen_controller_v2.py','--script',Path(command[0]).stem]

    if a.dry_plan:print(json.dumps(dict(node=a.node,commands=names)),flush=True);return
    setup(f'vlm_repair/resume_v6/node{a.node}');folder=ROOT/a.resume/f'node{a.node}';folder.mkdir(exist_ok=True)
    assert read(ROOT/a.resume/'PREPARED.json')['status']=='PREPARED_NOT_SUBMITTED'
    assert read(ROOT/a.resume/'PREPARED.json')['continuation_version']==6
    p=read(VOUT/'CONTINUATION_EXECUTION_v6.json')
    for path,h in p['code_sha256'].items():assert sha(ROOT/path)==h,path
    from natural_coordinate import preflight
    class Args:pass
    args=Args();args.node=a.node;args.run='vlm_resume_'+Path(a.resume).name
    preflight(args,dict(p,identity='Same frozen RL/VLM model, data, seeds and committed outputs; cold continuation'))
    processes={};streams={};env=dict(os.environ)
    for k in ['RANK','LOCAL_RANK','WORLD_SIZE','LOCAL_WORLD_SIZE','GROUP_RANK','ROLE_RANK','ROLE_WORLD_SIZE']:env.pop(k,None)
    for name,command in names.items():
        stream=(folder/(name+'.log')).open('a');streams[name]=stream
        processes[name]=subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code'/command[0])]+command[1:],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
    atomic(folder/'LAUNCHED.json',dict(status='PASS',time=stamp(),node=a.node,commands=names,processes={n:p.pid for n,p in processes.items()}))
    while True:
        state={name:dict(pid=p.pid,returncode=p.poll(),status='RUNNING' if p.poll() is None else 'COMPLETE' if p.returncode==0 else 'FAILED') for name,p in processes.items()}
        for name,s in state.items():
            if s['status']=='FAILED':atomic(folder/'failures'/(name+'.json'),dict(time=stamp(),original_log=str((folder/(name+'.log')).relative_to(ROOT)),**s))
        atomic(folder/'STATUS.json',dict(time=stamp(),node=a.node,processes=state,main_process_retained=True));time.sleep(30)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',type=int,choices=[0,1],required=True);p.add_argument('--resume');p.add_argument('--dry-plan',action='store_true');a=p.parse_args()
    try:main(a)
    except BaseException as e:
        if a.dry_plan:raise
        atomic(ROOT/a.resume/f'node{a.node}/FAILED.json',dict(status='FAILED',time=stamp(),error=repr(e),traceback=traceback.format_exc()))
        while True:time.sleep(30)
