"""Read-only cloud/status poller. No job creation, restarts, or repair actions."""
from common import *
import argparse
from cloud_api import request


def once():
    execution=read(ROOT/'configs/execution.json')
    run=execution['run_id'];base=ROOT/'runs'/run
    jobs=[];nodes=[];failures=[]
    for node in range(2):
        job_id=read(ROOT/f'dlc/submission_node{node}.json')['JobId']
        try:
            job=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job_id)
            job={k:job[k] for k in ['JobId','DisplayName','Status','ReasonCode','ReasonMessage','GmtStartTime','GmtEndTime'] if k in job}
            atomic(ROOT/f'dlc/latest_node{node}.json',job)
        except Exception as error:
            job=dict(JobId=job_id,Status='QUERY_ERROR',error=str(error))
        jobs.append(job)
        path=base/f'node{node}/STATUS.json'
        if path.exists():
            try:
                value=read(path)
                nodes.append({k:v for k,v in value.items() if k!='worker_statuses'})
            except OSError:nodes.append(dict(node_id=node,status='STATUS_READ_RETRY_NEXT_POLL'))
        failure=base/f'node{node}/FAILED.json'
        if failure.exists():failures.append(str(failure))
    complete=base/'BASELINE_READY.json'
    failed=bool(failures) or any(j['Status'] in {'Failed','Stopped','Deleted'} for j in jobs)
    status='FAILED' if failed else 'COMPLETE' if complete.exists() else 'RUNNING'
    result=dict(status=status,time=stamp(),run_id=run,jobs=jobs,nodes=nodes,failures=failures,
                completed=sum(n.get('completed',0) for n in nodes if n.get('status')=='FORMAL'),expected=103288,
                smoke_gate=(base/'BOTH_NODE_SMOKE_PASS.json').exists())
    if complete.exists():
        ready=read(complete);result.update(summary=str(base/'delivery/summary.json'),report=ready['report'],completed=ready['samples'])
    atomic(ROOT/'STATUS.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    if failed:return 1
    if all(j['Status']=='Succeeded' for j in jobs):
        return 0 if complete.exists() else 2
    return None


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    while True:
        code=once()
        if code is not None:raise SystemExit(code)
        if args.once:return
        time.sleep(60)


if __name__=='__main__':main()
