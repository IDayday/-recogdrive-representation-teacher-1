"""Compact the execution inbox; immutable protocols, receipts and claims remain.

The original full inbox is compressed before each atomic replacement. Only tasks
with completed receipts leave the live inbox; no active or failed task is removed.
This avoids repeatedly reading and stat-scanning tens of thousands of done jobs.
"""
from r2_common import *
import gzip


def main():
    folder=ROOT/'provenance/cpu_inbox_compaction';folder.mkdir(parents=True,exist_ok=True)
    while True:
        with (RUN/'cpu.lock').open('a+') as guard:
            fcntl.flock(guard,fcntl.LOCK_EX)
            path=RUN/'tasks_cpu.json';tasks=read(path)
            done={p.stem for p in (RUN/'receipts_cpu').glob('*.json')}
            pending=[t for t in tasks if t['id'] not in done]
            removed=len(tasks)-len(pending)
            if removed>=256 or (removed and not pending):
                ident=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+str(path.stat().st_mtime_ns)
                archive=folder/(ident+'.json.gz');before=sha(path)
                content=retry(path.read_bytes)
                with gzip.open(archive,'wb',compresslevel=1) as stream:stream.write(content)
                assert hashlib.sha256(content).hexdigest()==before
                atomic(path,pending)
                record=dict(status='COMPACTED',time=stamp(),before_tasks=len(tasks),removed_completed=removed,
                       pending_inbox_tasks=len(pending),source_sha256=before,live_sha256=sha(path),
                       original_inbox_archive=str(archive.relative_to(ROOT)),receipts_and_claims_unchanged=True,
                       no_active_or_failed_tasks_removed=True,scientific_protocols_unchanged=True)
                atomic(folder/(ident+'.json'),record);atomic(folder/'LATEST.json',record)
                print(json.dumps({k:record[k] for k in ['status','removed_completed','pending_inbox_tasks']}),flush=True)
        time.sleep(300)


if __name__=='__main__':main()
