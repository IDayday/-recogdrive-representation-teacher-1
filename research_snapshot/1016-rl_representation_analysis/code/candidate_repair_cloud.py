"""Freeze validated runtime, submit exactly two new task-owned 16-card jobs, preserve receipts."""
from common import *
from cloud_api import request
from candidate_repair_fit import OUT
import copy

def main():
    setup('candidate_repair/cloud')
    assert read(OUT/'ENGINEERING_PASS_v2.json')['status']=='PASS'
    for p,h in read(OUT/'ENGINEERING_PASS_v2.json')['code_sha256'].items():assert sha(ROOT/p)==h
    dsw='runs/candidate_repair_dsw_v4/smoke/rank000.json';assert read(ROOT/dsw)['status']=='PASS'
    protocol=read(OUT/'PROTOCOL.json');run=protocol['run'];config=ROOT/'configs/candidate_repair_execution_v1.json';assert not config.exists()
    before=request('pai-dlc','2020-12-03','ListJobs','GET','/api/v1/jobs',{'WorkspaceId':os.environ['PAI_WORKSPACE_ID'],'PageSize':100})
    active=[{k:j.get(k) for k in ['JobId','Status','DisplayName','ResourceId']} for j in before.get('Jobs',[]) if j['Status'] not in ['Stopped','Failed','Succeeded']]
    atomic(ROOT/'dlc/candidate_repair_resources_before_submit.json',dict(time=stamp(),active_jobs=active))
    paths=set(read(ROOT/'configs/repair_execution_v2.json')['code_sha256'])
    paths.update(['code/candidate_repair_engine.py','code/candidate_repair_queue.py','code/candidate_repair_fit.py','code/candidate_repair_launch.sh',
        'code/subspace_scan_math.py','code/subspace_scan_cv.py','code/subspace_scan_prepare.py','code/repair_test_features.py','configs/repair_final_baseline.json'])
    fit_paths=[p for p in (OUT/'fits').iterdir() if p.suffix in ['.npz','.json']]
    execution=dict(time=stamp(),run=run,code_sha256={p:sha(ROOT/p) for p in sorted(paths)},fit_sha256={str(p.relative_to(ROOT)):sha(p) for p in fit_paths},
        dsw_reference=dsw,submissions=[f'dlc/candidate_repair_submission_node{i}.json' for i in range(2)],resources=dict(nodes=2,gpus_per_node=16),
        initial_tasks_sha256=sha(ROOT/'runs'/run/'tasks.json'),protocol_sha256=sha(OUT/'PROTOCOL.json'),engineering_sha256=sha(OUT/'ENGINEERING_PASS_v2.json'),
        queue_open_until_all_heavy_work_completed=True)
    execution['identity']=digest(execution);atomic(config,execution)
    for node in range(2):
        body=copy.deepcopy(read(ROOT/f'dlc/repair_v2_request_node{node}.json'))
        assert str(body['WorkspaceId'])==os.environ['PAI_WORKSPACE_ID']
        body['DisplayName']=f'sjc-expanded-candidate-repair-node{node}-20261016-v1'
        body['UserCommand']=f'bash {ROOT}/code/candidate_repair_launch.sh {node} {run} configs/candidate_repair_execution_v1.json'
        body['JobMaxRunningTimeMinutes']=720;body['Settings']={'JobReservedMinutes':0}
        assert len(body['JobSpecs'])==1 and int(body['JobSpecs'][0]['PodCount'])==1 and int(body['JobSpecs'][0]['ResourceConfig']['GPU'])==16
        mounts={m['MountPath']:m for m in body['DataSources']}
        assert set(mounts)=={'/mnt/workspace','/mnt/data','/mnt/yehr_workspace'}
        assert mounts['/mnt/workspace']['MountAccess']=='RW' and all(mounts[p]['MountAccess']=='RO' for p in ['/mnt/data','/mnt/yehr_workspace'])
        atomic(ROOT/f'dlc/candidate_repair_request_node{node}.json',body)
        result=request('pai-dlc','2020-12-03','CreateJob','POST','/api/v1/jobs',payload=body)
        receipt={k:result[k] for k in ['JobId','RequestId']};atomic(ROOT/execution['submissions'][node],receipt)
        print(json.dumps(dict(event='CREATED',node=node,**receipt)),flush=True)
    atomic(OUT/'CLOUD_READY.json',dict(status='SUBMITTED',time=stamp(),execution_sha256=sha(config),jobs=[read(ROOT/p)['JobId'] for p in execution['submissions']]))

if __name__=='__main__':main()
