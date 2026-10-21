"""Read-only final retention audit of the two current jobs and original coordinators."""
from common import *
from cloud_api import request
from candidate_repair_terminal import execute
from candidate_repair_fit import OUT

def main():
    setup('candidate_repair/resource_audit');base=ROOT/'runs/candidate_repair_20261016_v1'
    assert not read(base/'queue.json')['closed']
    assert all(read(base/'workers'/f'rank{r:03d}.json')['status']=='QUEUE_WAIT' for r in range(32))
    command=f'''cd {ROOT}
PYTHONDONTWRITEBYTECODE=1 /usr/local/bin/python -B - <<'PYCODE'
import os,json
from pathlib import Path
import torch
assert torch.cuda.is_available() and torch.cuda.device_count()==16
coordinators=[];workers=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:parts=(p/'cmdline').read_bytes().split(b'\\0')
 except (OSError,PermissionError):continue
 if not any(x.endswith(b'/candidate_repair_queue.py') or x==b'code/candidate_repair_queue.py' for x in parts):continue
 if b'candidate_repair_20261016_v1' not in parts:continue
 if b'node' in parts:coordinators.append(int(p.name))
 if b'worker' in parts:workers.append(int(p.name))
assert len(coordinators)==1 and len(workers)==16
print(json.dumps(dict(status='PASS',hostname=os.uname().nodename,devices=16,coordinator_pids=coordinators,worker_pids=workers,original_program_alive=True)),flush=True)
PYCODE'''
    jobs=[]
    for node,job in enumerate(read(OUT/'CLOUD_READY.json')['jobs']):
        j=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job)
        assert j['Status']=='Running' and j['JobMaxRunningTimeMinutes']==720 and j['Settings']['JobReservedMinutes']==0
        created=dt.datetime.fromisoformat(j['GmtCreateTime'].replace('Z','+00:00'));deadline=created+dt.timedelta(minutes=720)
        result=execute(job,command,timeout=60);assert result['exit_code']==0
        atomic(OUT/f'RETAINED_TERMINAL_NODE{node}.json',result)
        jobs.append(dict(job=job,status=j['Status'],cards=16,max_minutes=720,reserved_minutes=0,conservative_deadline=deadline.isoformat(),
            remaining_seconds=(deadline-dt.datetime.now(dt.timezone.utc)).total_seconds(),terminal_proof_sha256=sha(OUT/f'RETAINED_TERMINAL_NODE{node}.json')))
    record=dict(status='PASS',time=stamp(),jobs=jobs,queue_open=True,all_32_workers_waiting=True,original_coordinators_preserved=True,
        resources_intentionally_retained=True,no_stop_or_release_called=True,uninterrupted_extension_verified=False)
    atomic(OUT/'RESOURCE_RETENTION_FINAL.json',record);print(json.dumps(record),flush=True)

if __name__=='__main__':main()
