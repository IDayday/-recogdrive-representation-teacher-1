from common import *
import subprocess
setup('subspace_scan/post_wait')
while not (ROOT/'analysis/subspace_scan_v2/SCIENCE_READY.json').exists():time.sleep(30)
for script in ['subspace_distributions.py','subspace_control_comparisons.py']:
 print(json.dumps(dict(status='POST_STEP',script=script,time=stamp())),flush=True)
 subprocess.run([sys.executable,'-B',str(ROOT/'code'/script)],check=True,cwd=ROOT)
atomic(ROOT/'analysis/subspace_scan_v2/REPORT_DATA_READY.json',dict(status='PASS',time=stamp()))
print(json.dumps(dict(status='REPORT_DATA_READY',time=stamp())),flush=True)
