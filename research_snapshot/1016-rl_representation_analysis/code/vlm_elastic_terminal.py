"""Container terminal for one registered node and its explicit account profile."""
from common import *
import argparse,re,uuid
from vlm_elastic_registry import configuration
from vlm_elastic_manage import profile
from vlm_elastic_cloud import request
from repair_queue_v2 import atomic_unique as atomic

def execute(c,command,timeout):
    import websocket
    folder=ROOT/c['folder'];p=profile(c);job=read(folder/'SUBMITTED.json')['job'];body=read(folder/'REQUEST.json')
    d=request(p,'pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
    assert d['Status']=='Running' and d['UserCommand']==body['UserCommand'] and d['DisplayName']==body['DisplayName']
    assert str(d['WorkspaceId'])==str(p['workspace_id']) and d['ResourceId']==p['quota_id']
    pod=next(x for x in d['Pods'] if x['Status']=='Running')
    response=request(p,'pai-dlc','2020-12-03','GetWebTerminal','GET',f'/api/v1/jobs/{job}/pods/{pod["PodId"]}/webterminal',query={'IsShared':'true'})
    connection=None;output='';marker='VLM_ELASTIC_EXIT_'+uuid.uuid4().hex;began=time.monotonic()
    try:
        connection=websocket.create_connection(response['WebTerminalUrl'],timeout=15,http_no_proxy=['*'])
        connection.send(json.dumps(dict(operation='stdin',data=command+f"\nprintf '\\n{marker}:%s\\n' \"$?\"\n")))
        while time.monotonic()-began<timeout:
            connection.settimeout(min(15,max(1,timeout-(time.monotonic()-began))))
            try:value=json.loads(connection.recv())
            except websocket.WebSocketTimeoutException:continue
            if value.get('operation')=='stdout':output+=value.get('data','')
            found=re.search(r'(?:\r?\n)'+marker+r':(\d+)(?:\r?\n)',output)
            if found:return dict(status='PASS' if found.group(1)=='0' else 'COMMAND_FAILED',time=stamp(),job=job,pod=pod['PodId'],exit_code=int(found.group(1)),seconds=time.monotonic()-began,output=output,terminal_url_saved=False,command_sha256=hashlib.sha256(command.encode()).hexdigest())
        raise TimeoutError('Scoped elastic command timed out')
    except Exception as error:raise RuntimeError('Elastic terminal transport: '+type(error).__name__) from None
    finally:
        if connection is not None:connection.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--id',required=True);p.add_argument('--command-file',required=True);p.add_argument('--output',required=True);p.add_argument('--timeout',type=int,default=50);a=p.parse_args();setup('vlm_repair/elastic_terminal')
    source=(ROOT/a.command_file).resolve();output=(ROOT/a.output).resolve();assert source.is_relative_to(ROOT) and output.is_relative_to(ROOT)
    r=execute(configuration(a.id),source.read_text(),a.timeout);atomic(output,r)
    print(json.dumps({k:r[k] for k in ['status','job','pod','exit_code','seconds']}));assert r['exit_code']==0
