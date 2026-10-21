"""Recover terminated legacy ranks through replay tasks on existing live workers.

Never stops jobs, resets global claims, restarts live GPU workers, or changes
model computation. Replay stages use exact original slices and frozen inputs.
"""
from common import *
import argparse,fcntl,shutil,subprocess,traceback
import numpy as np
from vlm_elastic_registry import DEST,BASE,configuration
from vlm_elastic_roll import legacy,get_old,TERMINAL
from vlm_elastic_producers import MARKERS,finished
from repair_queue_v2 import atomic_unique as atomic,append

REC=DEST/'natural_expiry_recovery_v2'
ACTIVE_LEGACY=None

def ensure_append(plan):
    current={t['id']:t for t in read(BASE/'tasks.json')};missing=[]
    for task in plan['replay_tasks']:
        if task['id'] in current:assert current[task['id']]==task
        else:missing.append(task)
    if missing:append(BASE,missing)
    atomic(REC/'APPENDED.json',dict(status='PASS',time=stamp(),tasks=len(plan['replay_tasks'])))

def confirm():
    end=time.monotonic()+1200
    for ident in [ACTIVE_LEGACY]:
        n=legacy(ident);checks=[]
        existing=DEST/'retirements'/(ident+'.json')
        if existing.exists():
            proof=read(existing);assert proof['status']=='PASS' and proof['job']==n['job']
            print('EXISTING_ACTUAL_TERMINAL_PROOF_RETAINED',ident,flush=True);continue
        while len(checks)<2:
            _,d=get_old(n);pods=[dict(id=p['PodId'],status=p['Status']) for p in d.get('Pods',[])]
            terminal=d['Status'] in TERMINAL and all(p['status'] in TERMINAL for p in pods)
            if terminal:checks.append(dict(time=stamp(),job=n['job'],status=d['Status'],pods=pods,
                cloud_created=d.get('GmtCreateTime'),cloud_running=d.get('GmtRunningTime'),cloud_finished=d.get('GmtFinishedTime')))
            else:checks=[]
            assert time.monotonic()<end,'Platform has not terminated the legacy job; retain it and review actual cloud state.'
            if len(checks)<2:time.sleep(10)
        folder=DEST/'rolling'/f'deadline_{ident}_20261017T1542'
        deferred=read(folder/'DEFERRED.json');assert deferred['status']=='DEFERRED_ALL_PAUSES_REVERSED'
        proof=dict(status='PASS',time=stamp(),legacy_id=ident,job=n['job'],double_terminal_checks=checks,
            no_StopJob_or_DeleteJob_requested=True,quiesce_deferred_and_all_pauses_reversed=True,
            defer_proof_sha256=sha(folder/'DEFERRED.json'),end_reason='Actual platform terminal after original time limit; no active release.',
            interrupted_GPU_chunks_require_scoped_replay=True)
        atomic(folder/'TERMINAL_CONFIRMED.json',proof);atomic(DEST/'retirements'/(ident+'.json'),proof)
        print('ACTUAL_LEGACY_DOUBLE_TERMINAL',ident,flush=True)

def validate(doc,task):
    assert doc['status']=='COMPLETE' and doc['task']==task
    folder=BASE/'stages'/task['stage'];rows=read(folder/'panel.json')[task['start']:task['end']]
    arms=read(folder/'arms.json')[task['arm_start']:task['arm_end']];lookup={x['id']:x for x in arms}
    expected={(r['token'],j,a) for r in rows for j in task['seeds'] for a in ['baseline',*lookup]}
    keys=[(r['token'],r['seed_index'],r['arm']) for r in doc['records']]
    assert len(keys)==len(set(keys)) and set(keys)==expected
    for r in doc['records']:
        assert r['seed']==seed(r['token'],r['seed_index']) and r['quality']==quality(r['score']['score'])
        assert set(r['score'])=={'score',*COMPONENTS}
        assert np.asarray(r['trajectory']).shape==(8,3) and np.isfinite(r['trajectory']).all()
        assert all(np.isfinite(v) and 0<=v<=1+1e-8 for v in r['score'].values())
        assert r['edit']['relative_edit_max']<=lookup.get(r['arm'],{}).get('cap',0)+1e-6

def prepare():
    REC.mkdir(exist_ok=True)
    for ident in [ACTIVE_LEGACY]:
        proof=read(DEST/'retirements'/(ident+'.json'));assert proof['status']=='PASS' and len(proof['double_terminal_checks'])==2
        _,d=get_old(legacy(ident));assert d['Status'] in TERMINAL
    if (REC/'PLAN.json').exists():
        plan=read(REC/'PLAN.json');ensure_append(plan);return plan
    tasks=read(BASE/'tasks.json');index={t['id']:t for t in tasks};pending=[];orphans=[]
    complete={p.stem for p in (BASE/'receipts').glob('*.json')}
    for folder in (BASE/'claims').iterdir():
        if folder.name in complete:continue
        owner_path=folder/'OWNER.json'
        if not owner_path.exists():continue  # Never infer ownership of another live node's incomplete mkdir.
        owner=read(owner_path)
        if owner['rank'] not in set(legacy(ACTIVE_LEGACY)['gpu_ranks']):continue
        task=index[folder.name];assert owner['task']==task
        n=legacy('legacy_'+str(owner['rank']//16));assert owner['rank'] in n['gpu_ranks']
        saved=REC/'previous_owners'/(folder.name+'.json');atomic(saved,dict(owner=owner,owner_sha256=sha(owner_path),job=n['job'],task=task))
        result=BASE/'results'/(folder.name+'.json')
        if result.exists():
            doc=read(result);validate(doc,task);assert doc['rank']==owner['rank']
            atomic(BASE/'receipts'/result.name,dict(status='COMPLETE',time=stamp(),rank=doc['rank'],task=task,
                records=len(doc['records']),seconds=0.,result_sha256=sha(result),recovered_already_complete_atomic_result=True))
            orphans.append(dict(task=task['id'],sha256=sha(result)));continue
        pending.append(dict(task=task,owner=owner,owner_sha256=sha(owner_path)))
    groups={}
    for row in pending:groups.setdefault(row['task']['stage'],[]).append(row)
    replay=[];mapping=[]
    for original_stage,items in groups.items():
        source=BASE/'stages'/original_stage;name='expiry_replay_'+ACTIVE_LEGACY+'_'+original_stage+'_20261017';folder=BASE/'stages'/name
        folder.mkdir(parents=True,exist_ok=True)
        for filename in ['panel.json','arms.json']:
            if not (folder/filename).exists():shutil.copyfile(source/filename,folder/filename)
            assert sha(source/filename)==sha(folder/filename)
        protocol=read(source/'PROTOCOL.json')
        assert sum(t['stage']==original_stage for t in tasks)==protocol['tasks'],'Original stage manifest must be complete before replay.'
        aliases=[]
        for i,item in enumerate(sorted(items,key=lambda x:x['task']['id'])):
            t=item['task'];alias=dict(t,id=f'{name}_a{i:05d}_{t["start"]:06d}',stage=name,recovery_original_task=t['id'])
            assert {k:v for k,v in alias.items() if k not in ['id','stage','recovery_original_task']}=={k:v for k,v in t.items() if k not in ['id','stage']}
            aliases.append(alias);mapping.append(dict(item,alias=alias))
        if (folder/'PROTOCOL.json').exists():
            previous=read(folder/'PROTOCOL.json');assert previous['tasks']==len(aliases) and previous['original_protocol_sha256']==sha(source/'PROTOCOL.json')
        else:
            atomic(folder/'PROTOCOL.json',dict(protocol,time=stamp(),tasks=len(aliases),
                original_stage=original_stage,original_protocol_sha256=sha(source/'PROTOCOL.json'),
                computational_replay_of_interrupted_slices_only=True,no_new_scientific_samples_or_candidates=True))
        replay.extend(aliases)
    plan=dict(status='PREPARED',time=stamp(),mapping=mapping,replay_tasks=replay,orphan_results_committed=orphans,
        preserved_all_completed_results=True,no_live_claim_removed=True,no_global_cursor_reset=True,
        uses_existing_verified_GPU_program=True)
    atomic(REC/'PLAN.json',plan)
    ensure_append(plan)
    print('SCOPED_EXPIRY_REPLAY_APPENDED',len(replay),'orphan_results_preserved',len(orphans),flush=True)
    return plan

def commit(item):
    task=item['task'];alias=item['alias'];receipt=BASE/'receipts'/(alias['id']+'.json')
    if not receipt.exists():return False
    r=read(receipt);source=BASE/'results'/receipt.name;assert sha(source)==r['result_sha256'];doc=read(source);validate(doc,alias)
    canonical=BASE/'receipts'/(task['id']+'.json')
    if canonical.exists():return True
    owner=BASE/'claims'/task['id']/'OWNER.json';assert sha(owner)==item['owner_sha256']
    result=BASE/'results'/(task['id']+'.json');assert not result.exists()
    transferred=dict(doc,task=task,expiry_replay_source=str(source.relative_to(ROOT)),expiry_replay_sha256=sha(source))
    validate(transferred,task);atomic(result,transferred)
    actual_owner=read(BASE/'claims'/alias['id']/'OWNER.json')
    atomic(owner,dict(actual_owner,task=task,previous_terminated_owner_sha256=item['owner_sha256'],replayed_alias=alias['id']))
    atomic(canonical,dict(r,task=task,result_sha256=sha(result),expiry_replay_alias=alias['id']))
    return True

def replay():
    plan=prepare()
    # The original manifests are append-only. Existing workers pick appended
    # replay slices without restarting or rewinding their private cursors.
    while True:
        completed=sum(commit(x) for x in plan['mapping'])
        atomic(REC/'STATUS.json',dict(status='RUNNING',time=stamp(),pid=os.getpid(),completed=completed,total=len(plan['mapping'])))
        if completed==len(plan['mapping']):break
        time.sleep(30)
    atomic(REC/'REPLAY_COMPLETE.json',dict(status='PASS',time=stamp(),replayed=len(plan['mapping']),
        completed_atomic_orphans=len(plan['orphan_results_committed']),all_original_expected_tasks_restored=True,
        original_records_inputs_seeds_arms_and_scoring_preserved=True,no_live_GPU_process_restarted=True))
    print('LEGACY_SCOPED_REPLAY_COMPLETE',len(plan['mapping']),flush=True)

def producers(a):
    c=configuration(a.id);assert read(ROOT/c['folder']/'PREFLIGHT.json')['status']=='PASS'
    for ident in ['legacy_0','legacy_1']:assert read(DEST/'retirements'/(ident+'.json'))['status']=='PASS'
    folder=REC/'producers';folder.mkdir(exist_ok=False);children={};streams=[]
    for name in MARKERS:
        if finished(name):continue
        stream=(folder/(name+'.log')).open('a');streams.append(stream)
        children[name]=subprocess.Popen([sys.executable,'-u','-B',str(ROOT/'code/vlm_elastic_producers.py'),'execute','--script',name],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    atomic(folder/'LAUNCHED.json',dict(status='PASS',time=stamp(),host=a.id,processes={n:p.pid for n,p in children.items()},completed_producers_not_restarted=True))
    while True:
        for name,p in children.items():assert p.poll() in [None,0],(name,p.poll())
        atomic(folder/'STATUS.json',dict(status='RUNNING',time=stamp(),pid=os.getpid(),host=a.id,
            processes={n:dict(pid=p.pid,returncode=p.poll()) for n,p in children.items()},resources_retained=True))
        time.sleep(15)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['confirm','replay','producers']);p.add_argument('--id');p.add_argument('--legacy-id',choices=['legacy_0','legacy_1'],required=True);a=p.parse_args();ACTIVE_LEGACY=a.legacy_id;REC=REC/ACTIVE_LEGACY;setup('vlm_repair/natural_expiry_recovery_v2')
    for path,h in read(DEST/'NATURAL_EXPIRY_RECOVERY_EXECUTION_v2.json')['code_sha256'].items():assert sha(ROOT/path)==h,path
    try:producers(a) if a.mode=='producers' else globals()[a.mode]()
    except BaseException as exc:
        atomic(REC/'failures'/(a.mode+'.json'),dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()));raise
