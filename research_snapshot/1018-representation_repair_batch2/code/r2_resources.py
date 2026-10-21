"""Quiet cloud supervision and automatic joining of the six authorized jobs."""
from r2_common import *
import shlex
from dlc_cloud import request
from r2_remote import execute


def main():
    previous={};failures=0
    profile={'region':'cn-wulanchabu','workspace_id':'245760','auth':{'kind':'instance_role'}}
    while True:
        result=[]
        try:
            for node in read(ROOT/'resources/NODES.json')['nodes']:
                job=node['job']
                d=request(profile,'pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
                assert d['JobMaxRunningTimeMinutes']==4320
                state=dict(name=node['name'],job=job,status=d['Status'],created=d['GmtCreateTime'],
                           running_since=d.get('GmtRunningTime'),maximum_minutes=d['JobMaxRunningTimeMinutes'])
                if d.get('GmtRunningTime'):
                    begin=dt.datetime.fromisoformat(d['GmtRunningTime'].replace('Z','+00:00'))
                    deadline=begin+dt.timedelta(minutes=d['JobMaxRunningTimeMinutes'])
                    state.update(deadline_from_running_time=deadline.isoformat(),
                                 remaining_seconds=(deadline-dt.datetime.now(dt.timezone.utc)).total_seconds())
                result.append(state)
                if previous.get(job)!=d['Status']:
                    print(json.dumps(dict(event='CLOUD_STATE',time=stamp(),**state)),flush=True)
                    previous[job]=d['Status']
                directory=RUN/'nodes'/node['name'];live=directory/'LIVE.json'
                launch=ROOT/'provenance'/('launch_'+node['name']+'.json')
                if d['Status']=='Running' and not live.exists() and not launch.exists():
                    directory.mkdir(parents=True,exist_ok=True)
                    command='nohup python3 -u -B '+shlex.quote(str(ROOT/'code/r2_node.py'))+' --node '+shlex.quote(node['name'])+' > '+shlex.quote(str(directory/'parent.log'))+' 2>&1 < /dev/null &\nprintf "R2_NODE_LAUNCHED:%s\\n" "$!"'
                    proof=execute(job,command);atomic(launch,proof)
                    assert proof['exit_code']==0
                    print(json.dumps(dict(event='NODE_JOIN_LAUNCHED',time=stamp(),node=node['name'],job=job)),flush=True)
                if d['Status'] in ['Failed','Stopped','Succeeded']:
                    atomic(ROOT/'resources/TERMINAL_ALERT.json',dict(status='ATTENTION',time=stamp(),node=node,cloud=state))
            atomic(ROOT/'resources/CLOUD_LATEST.json',dict(time=stamp(),nodes=result,automatic_release=False))
            failures=0
        except Exception as error:
            failures+=1
            atomic(ROOT/'resources/MONITOR_LAST_ERROR.json',dict(time=stamp(),consecutive=failures,error=repr(error)))
            if failures>=3:
                print(json.dumps(dict(event='CLOUD_MONITOR_ERROR',consecutive=failures,error=repr(error))),flush=True)
                return 3
        time.sleep(60)


if __name__=='__main__':raise SystemExit(main())
