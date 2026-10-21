"""Restart-safe metadata helpers; scientific handlers and artifacts stay fixed."""
from r2_common import *


def enqueue(queue,known,task):
    if task['id'] not in known:queue.append(task);known.add(task['id'])


def append_once(kind,tasks):
    with (RUN/(kind+'.lock')).open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX)
        path=RUN/('tasks_'+kind+'.json');old=read(path) if path.exists() else [];existing={t['id']:t for t in old}
        new=[]
        for task in tasks:
            ident=task['id']
            if ident in existing:
                assert digest(existing[ident])==digest(task);continue
            if (RUN/('receipts_'+kind)/(ident+'.json')).exists() or (RUN/('claims_'+kind)/ident).exists():continue
            new.append(task);existing[ident]=task
        if new:atomic(path,old+new)


def register_once(stage):
    with (ROOT/'config/gpu_stages.lock').open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX);path=ROOT/'config/GPU_STAGES.json';config=read(path)
        old=next((s for s in config['stages'] if s['name']==stage['name']),None)
        if old:
            for key in ['path','handler','handler_sha256','kind']:assert old[key]==stage[key]
        else:config['stages'].append(stage);config['time']=stamp();atomic(path,config)
