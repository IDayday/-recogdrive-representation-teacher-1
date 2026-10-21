"""Scoped terminal access for a recorded continuation; ephemeral URL is never logged."""
from common import *
import argparse,re,uuid
from repair_queue_v2 import atomic_unique as atomic

def execute(folder,node,command,timeout):
    import websocket
    from cloud_api import request
    ready=read(folder/'CLOUD_READY.json');job=ready['jobs'][node]
    d=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
    assert d['DisplayName'].startswith(f'sjc-vlm-continuation-node{node}-') and d['Status']=='Running'
    assert str(d['WorkspaceId'])==os.environ['PAI_WORKSPACE_ID']
    assert d['UserCommand']==read(ROOT/ready['requests'][node])['UserCommand']
    pod=next(p for p in d['Pods'] if p['Status']=='Running')
    response=request('pai-dlc','2020-12-03','GetWebTerminal','GET',f'/api/v1/jobs/{job}/pods/{pod["PodId"]}/webterminal',{'IsShared':'true'})
    connection=None;output='';marker='VLM_RESUME_EXIT_'+uuid.uuid4().hex;start=time.monotonic()
    try:
        connection=websocket.create_connection(response['WebTerminalUrl'],timeout=15,http_no_proxy=['*'])
        connection.send(json.dumps(dict(operation='stdin',data=command+f"\nprintf '\\n{marker}:%s\\n' \"$?\"\n")))
        while time.monotonic()-start<timeout:
            connection.settimeout(min(15,max(1,timeout-(time.monotonic()-start))))
            try:m=json.loads(connection.recv())
            except websocket.WebSocketTimeoutException:continue
            if m.get('operation')=='stdout':output+=m.get('data','')
            found=re.search(r'(?:\r?\n)'+marker+r':(\d+)(?:\r?\n)',output)
            if found:return dict(status='PASS' if found.group(1)=='0' else 'COMMAND_FAILED',time=stamp(),job=job,pod=pod['PodId'],exit_code=int(found.group(1)),seconds=time.monotonic()-start,output=output,terminal_url_saved=False,command_sha256=hashlib.sha256(command.encode()).hexdigest())
        raise TimeoutError('Scoped continuation command timed out')
    except Exception as e:raise RuntimeError('Continuation terminal transport: '+type(e).__name__) from None
    finally:
        if connection is not None:connection.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--resume',required=True);p.add_argument('--node',type=int,choices=[0,1],required=True);p.add_argument('--command-file',required=True);p.add_argument('--output',required=True);p.add_argument('--timeout',type=int,default=50);a=p.parse_args();setup('vlm_repair/resume_terminal')
    folder=(ROOT/a.resume).resolve();command=(ROOT/a.command_file).resolve();assert folder.is_relative_to(ROOT) and command.is_relative_to(ROOT)
    r=execute(folder,a.node,command.read_text(),a.timeout);atomic(ROOT/a.output,r)
    print(json.dumps({k:r[k] for k in ['status','job','pod','exit_code','seconds']}));assert r['exit_code']==0
