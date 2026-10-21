"""Mechanical priority ordering, retaining every task and all in-flight claims."""
from r2_common import *
import gzip


def priority(task,completed):
    if task['id'] in completed:return 100
    if task['id'].startswith(('space_learned_','outcome_','engineering_')):return 0
    if task['id'].startswith('family_proposal_'):return 5
    if task['id'].startswith('space_cv_'):return 10
    return 8


def main():
    folder=ROOT/'provenance/cpu_queue_order';folder.mkdir(parents=True,exist_ok=True)
    while True:
        with (RUN/'cpu.lock').open('a+') as guard:
            fcntl.flock(guard,fcntl.LOCK_EX)
            path=RUN/'tasks_cpu.json';tasks=read(path)
            completed={p.stem for p in (RUN/'receipts_cpu').glob('*.json')}
            ordered=sorted(tasks,key=lambda t:priority(t,completed))
            if [t['id'] for t in ordered]!=[t['id'] for t in tasks]:
                ident=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')
                snapshot=folder/(ident+'.json.gz')
                with gzip.open(snapshot,'wt') as f:json.dump([t['id'] for t in tasks],f)
                before=sha(path);atomic(path,ordered)
                atomic(folder/(ident+'.json'),dict(time=stamp(),tasks=len(tasks),completed=len(completed),
                       before_sha256=before,after_sha256=sha(path),original_order=str(snapshot.relative_to(ROOT)),
                       task_configs_unchanged=True,claims_unchanged=True))
        time.sleep(300)


if __name__=='__main__':main()
