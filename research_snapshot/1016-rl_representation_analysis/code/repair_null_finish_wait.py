from common import *
import subprocess
setup('repair/null_finish_wait')
base=ROOT/'runs/repair_null_validation_20261016_v1'
while not (base/'COMPUTE_DRAINED_RESOURCES_HELD.json').exists():time.sleep(60)
subprocess.run([sys.executable,'-B',str(ROOT/'code/repair_null_accept.py')],check=True,cwd=ROOT)
