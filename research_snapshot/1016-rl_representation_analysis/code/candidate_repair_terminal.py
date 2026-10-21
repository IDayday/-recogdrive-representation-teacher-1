"""Execute a scoped command in the two retained task-owned containers; ephemeral URL never logged."""
from common import *
import argparse
import re
import uuid

def execute(job,command,timeout=90):
    from cloud_api import request
    import websocket
    assert job in read(ROOT/'candidate_repair_v1/CLOUD_READY.json')['jobs']
    config=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
    assert config['DisplayName'].startswith('sjc-expanded-candidate-repair-node') and config['Status']=='Running'
    assert str(config['WorkspaceId'])==os.environ['PAI_WORKSPACE_ID']
    node=read(ROOT/'candidate_repair_v1/CLOUD_READY.json')['jobs'].index(job)
    assert config['UserCommand']==read(ROOT/f'dlc/candidate_repair_request_node{node}.json')['UserCommand']
    pod=next(p for p in config['Pods'] if p['Status']=='Running')
    response=request('pai-dlc','2020-12-03','GetWebTerminal','GET',f'/api/v1/jobs/{job}/pods/{pod["PodId"]}/webterminal',{'IsShared':'true'})
    connection=None;output='';marker='REPAIR_EXIT_'+uuid.uuid4().hex;began=time.monotonic()
    try:
        connection=websocket.create_connection(response['WebTerminalUrl'],timeout=15,http_no_proxy=['*'])
        connection.send(json.dumps(dict(operation='stdin',data=command+f"\nprintf '\\n{marker}:%s\\n' \"$?\"\n")))
        while time.monotonic()-began<timeout:
            connection.settimeout(min(15,max(1,timeout-(time.monotonic()-began))))
            try:message=json.loads(connection.recv())
            except websocket.WebSocketTimeoutException:continue
            if message.get('operation')=='stdout':output+=message.get('data','')
            found=re.search(r'(?:\r?\n)'+marker+r':(\d+)(?:\r?\n)',output)
            if found:
                return dict(status='PASS' if found.group(1)=='0' else 'COMMAND_FAILED',time=stamp(),job=job,
                    pod=pod['PodId'],exit_code=int(found.group(1)),seconds=time.monotonic()-began,
                    output=output,command_sha256=hashlib.sha256(command.encode()).hexdigest(),terminal_url_saved=False)
        raise TimeoutError('Container command deadline exceeded')
    except Exception as error:
        # Transport exception text may contain the ephemeral access URL; do not expose it.
        raise RuntimeError('Container terminal transport failed: '+type(error).__name__) from None
    finally:
        if connection is not None:connection.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--job',required=True);p.add_argument('--command-file',required=True);p.add_argument('--output',required=True)
    p.add_argument('--timeout',type=int,default=90);args=p.parse_args();setup('candidate_repair/terminal')
    command_path=(ROOT/args.command_file).resolve();assert command_path.is_relative_to(ROOT)
    result=execute(args.job,command_path.read_text(),args.timeout);atomic(ROOT/args.output,result)
    print(json.dumps({k:result[k] for k in ['status','job','pod','exit_code','seconds']}));assert result['exit_code']==0
