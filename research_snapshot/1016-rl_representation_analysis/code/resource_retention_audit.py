"""Verify retained task-owned nodes, four waiting programs, open queues and live lifetime."""
from common import *
from cloud_api import request
from repair_terminal import execute

setup('resource_retention/final');runs=['repair_20261016_v2','repair_null_validation_20261016_v1','repair_final_test_20261016_v1','subspace_scan_20261016_v2']
for run in runs:
 base=ROOT/'runs'/run;assert not read(base/'queue.json')['closed']
 assert all(read(base/'workers'/f'rank{r:03d}.json')['status']=='QUEUE_WAIT' for r in range(32)),run
command=f'''cd {ROOT} && PYTHONDONTWRITEBYTECODE=1 /usr/local/bin/python -B - <<'PYCODE'
import sys
sys.path.insert(0,'code')
from common import *
setup('resource_retention/container_proof')
import torch
known={{'repair_queue_v2.py':'repair_20261016_v2','repair_validation_null_queue.py':'repair_null_validation_20261016_v1','repair_final_queue.py':'repair_final_test_20261016_v1','subspace_scan_queue.py':'subspace_scan_20261016_v2'}}
found=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:parts=(p/'cmdline').read_bytes().split(b'\\0')
 except (OSError,PermissionError):continue
 if b'node' not in parts:continue
 for program,run in known.items():
  if any(v.endswith(('/'+program).encode()) or v==('code/'+program).encode() for v in parts) and run.encode() in parts:found.append(dict(pid=int(p.name),program=program,run=run))
assert len(found)==4 and {{r['program'] for r in found}}==set(known)
assert torch.cuda.is_available() and torch.cuda.device_count()==16
print(json.dumps(dict(status='PASS',hostname=os.uname().nodename,devices=16,coordinators=found,original_preserved=True)),flush=True)
PYCODE'''
proofs=[]
for i,job in enumerate(['dlc1whaxhnd8c2zs','dlc1whaxhnnaj1nn']):
 j=request('pai-dlc','2020-12-03','GetJob','GET','/api/v1/jobs/'+job);assert j['Status']=='Running'
 max_minutes=j.get('JobMaxRunningTimeMinutes');assert max_minutes==720,max_minutes
 reserved=j.get('Settings',{}).get('JobReservedMinutes');assert reserved==0,reserved
 starts={k:dt.datetime.fromisoformat(j[k].replace('Z','+00:00')) for k in ['GmtCreateTime','GmtRunningTime'] if j.get(k)}
 deadlines={k:(v+dt.timedelta(minutes=max_minutes)).isoformat() for k,v in starts.items()};remaining=min((v+dt.timedelta(minutes=max_minutes)-dt.datetime.now(dt.timezone.utc)).total_seconds() for v in starts.values())
 terminal=execute(job,command);assert terminal['exit_code']==0;atomic(ROOT/f'provenance/retained_final_terminal_node{i}.json',terminal)
 proofs.append(dict(job=job,status=j['Status'],max_running_minutes=max_minutes,reserved_minutes=reserved,deadlines_utc=deadlines,conservative_remaining_seconds=remaining,
  extension_without_interruption_verified=False,terminal_proof_sha256=sha(ROOT/f'provenance/retained_final_terminal_node{i}.json')))
result=dict(status='PASS',time=stamp(),jobs=proofs,all_four_queues_open=True,all_four_program_workers_waiting=True,original_primary_processes_preserved=True,
 active_computation=False,resources_intentionally_retained=True,no_stop_or_release_called=True,extension_without_interruption='NOT_VERIFIED')
atomic(ROOT/'provenance/RESOURCE_RETENTION_FINAL.json',result);print(json.dumps(result),flush=True)
