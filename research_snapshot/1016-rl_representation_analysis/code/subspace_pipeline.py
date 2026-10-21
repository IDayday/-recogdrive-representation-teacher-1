"""Foreground orchestration; every cloud computation remains inside retained containers."""
from common import *
import subprocess
setup('subspace_scan/pipeline')
execution='configs/subspace_scan_execution_v2.json';cfg=read(ROOT/execution)
def call(program,*args):
 print(json.dumps(dict(status='PIPELINE_STEP',program=program,time=stamp())),flush=True)
 subprocess.run([sys.executable,'-B',str(ROOT/'code'/program),*args],check=True,cwd=ROOT)
call('subspace_scan_monitor.py','--execution',execution,'--phase','cv')
assert (ROOT/'runs'/cfg['run']/'CV_DRAINED_RESOURCES_HELD.json').exists()
call('subspace_scan_select.py','--run',cfg['run'])
call('subspace_scan_monitor.py','--execution',execution,'--phase','confirm')
assert (ROOT/'runs'/cfg['run']/'CONFIRM_DRAINED_RESOURCES_HELD.json').exists()
call('subspace_results.py','--execution',execution)
call('subspace_golden_audit.py')
atomic(ROOT/'analysis/subspace_scan_v2/SCIENCE_READY.json',dict(status='PASS',time=stamp(),execution_sha256=sha(ROOT/execution),resources_retained=True))
print(json.dumps(dict(status='SUBSPACE_SCIENCE_READY',time=stamp())),flush=True)
