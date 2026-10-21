"""Final mechanical acceptance: task coverage, hashes, model identity, all ranks and cloud exit."""
from common import *
import argparse
import numpy as np

def main(args):
    setup('repair/audit');compatibility()
    from cloud_api import request
    execution=read(ROOT/args.execution);base=ROOT/'runs'/execution['run']
    for p,h in execution['code_sha256'].items():assert sha(ROOT/p)==h,p
    tasks=read(base/'tasks.json');ids={t['id'] for t in tasks};assert len(ids)==len(tasks)
    assert read(base/'queue.json')['closed']==(not args.retain)
    assert {p.stem for p in (base/'receipts').glob('*.json')}==ids
    assert {p.stem for p in (base/'results').glob('*.json')}==ids
    failures=list((base/'failures').glob('*.json')) if (base/'failures').exists() else []
    assert not failures,failures
    total=0;by_stage={}
    for task in tasks:
        name=task['id']+'.json';receipt=read(base/'receipts'/name);path=base/'results'/name
        assert receipt['task']==task and sha(path)==receipt['result_sha256']
        data=read(path);assert data['status']=='COMPLETE' and data['task']==task
        assert receipt['records']==len(data['records']);total+=len(data['records'])
        by_stage[task['stage']]=by_stage.get(task['stage'],0)+1
        if task['stage']!='queue_smoke':
            for row in data['records']:
                trajectory=np.asarray(row['trajectory']);assert trajectory.shape==(8,3) and np.isfinite(trajectory).all()
                assert row['seed']==seed(row['token'],row['seed_index'])
                assert row['quality']==quality(row['score']['score'])
    summaries={}
    for name in by_stage:
        folder=base/'stages'/name;protocol=read(folder/'PROTOCOL.json')
        assert sha(folder/'panel.json')==protocol['panel_sha256']
        assert sha(folder/'arms.json')==protocol['arms_sha256']
        assert by_stage[name]==protocol['tasks']
        if name!='queue_smoke':
            p=ROOT/'repair_v1/analysis'/name/'SUMMARY.json';doc=read(p)
            assert doc['coverage_exact'];summaries[name]=sha(p)
    workers=[]
    for rank in range(32):
        state=read(base/'workers'/f'rank{rank:03d}.json')
        if args.retain:assert state['status'] in ['QUEUE_WAIT','COMPLETE']
        else:assert state['status']=='COMPLETE' and state['base_unchanged']
        runtime=read(base/'workers'/f'rank{rank:03d}_runtime.json')
        assert runtime['checkpoint_sha256']==read(ROOT/'configs/baseline.json')['checkpoint_sha256']
        assert runtime['strict_loaded_tensors']==347
        workers.append(state)
    jobs=[]
    for node in range(2):
        if not args.retain:
            c=read(base/f'node{node}/COMPLETE.json');assert c['exit_codes']==[0]*16
        smoke=read(base/f'node{node}/SMOKE_PASS.json');assert smoke['status']=='PASS' and smoke['ranks']==16
        submission=read(ROOT/execution['submissions'][node]);job=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+submission['JobId'])
        assert job['Status']==('Running' if args.retain else 'Succeeded'),(job['JobId'],job['Status'])
        jobs.append({k:job[k] for k in ['JobId','DisplayName','Status','Pods','EndTime'] if k in job})
    result=dict(status='PASS',time=stamp(),run=execution['run'],execution_sha256=sha(ROOT/args.execution),
        tasks=len(tasks),records=total,stages=by_stage,summaries_sha256=summaries,worker_exit_codes=None if args.retain else [0]*32,
        resources_retained=args.retain,worker_states=[v['status'] for v in workers],
        all_completed_tasks_passed_parameter_version_checks=True,jobs=jobs,all_result_and_receipt_hashes_verified=True)
    out=base/'FINAL_ACCEPTANCE.json';assert not out.exists();atomic(out,result)
    print(json.dumps(dict(status='PASS',run=base.name,tasks=len(tasks),records=total)),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',required=True);p.add_argument('--retain',action='store_true');main(p.parse_args())
