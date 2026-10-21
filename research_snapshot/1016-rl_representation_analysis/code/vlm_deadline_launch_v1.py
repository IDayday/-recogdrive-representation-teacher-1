"""Tool-owned wait, followed by scoped drain near the two old jobs' expiry."""
from common import *
import shlex
from vlm_elastic_registry import DEST
from vlm_resume_terminal import execute
from repair_queue_v2 import atomic_unique as atomic

OUT=DEST/'deadline_launch_20261017'
RESUME=DEST.parent/'resume/20261017T035006'

if __name__=='__main__':
    setup('vlm_repair/deadline_launch');OUT.mkdir(exist_ok=True)
    for p,h in read(DEST/'DEADLINE_LAUNCH_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    target=dt.datetime(2026,10,17,15,42,tzinfo=dt.timezone.utc)
    while dt.datetime.now(dt.timezone.utc)<target:
        time.sleep(min(15,max(.1,(target-dt.datetime.now(dt.timezone.utc)).total_seconds())))
    folders={}
    for node in [0,1]:
        ident=f'legacy_{node}'
        if (DEST/'retirements'/(ident+'.json')).exists():continue
        live=read(DEST/'CLONE_LIVE_LATEST.json');item=next(j for j in live['jobs'] if j['id']==ident)
        deadline=dt.datetime.fromisoformat(item['conservative_deadline'])
        if item['status']!='Running' or (deadline-dt.datetime.now(dt.timezone.utc)).total_seconds()>900:
            print('DEADLINE_DRAIN_SKIPPED_STATE_OR_EXTENSION',ident,item['status'],deadline.isoformat(),flush=True);continue
        relative=f'vlm_repair_v1/elastic_v1/rolling/deadline_{ident}_20261017T1542'
        folders[ident]=ROOT/relative;log=OUT/(ident+'.log')
        command='cd '+shlex.quote(str(ROOT))+'\nnohup '+shlex.quote(sys.executable)+' -u -B code/vlm_deadline_handoff_v1.py drain --legacy-id '+ident+' --folder '+relative+' --wait-seconds 600 > '+shlex.quote(str(log))+' 2>&1 < /dev/null &\nprintf "DEADLINE_DRAIN_PID:%s\\n" "$!"\n'
        atomic(OUT/(ident+'_COMMAND.json'),dict(time=stamp(),command=command,command_sha256=hashlib.sha256(command.encode()).hexdigest(),no_cloud_stop_or_delete=True))
        result=execute(RESUME,node,command,50);atomic(OUT/(ident+'_TERMINAL.json'),result)
        assert result['status']=='PASS'
    end=time.monotonic()+650
    while True:
        finished={}
        for ident,folder in folders.items():
            for name in ['QUIESCED.json','DEFERRED.json']:
                if (folder/name).exists():finished[ident]=dict(path=str((folder/name).relative_to(ROOT)),sha256=sha(folder/name),result=read(folder/name))
        if len(finished)==len(folders):
            atomic(OUT/'DRAIN_RESULT.json',dict(time=stamp(),jobs_retained_until_platform_expiry=True,results=finished))
            print('DEADLINE_DRAIN_REVIEW_REQUIRED',json.dumps(finished),flush=True);break
        assert time.monotonic()<end,'Drain did not report before its bounded wait; inspect exact logs and claims.'
        time.sleep(10)
