from common import *
import subprocess
from repair_analysis import summarize,safety
from repair_result_details import details
from repair_final_statistics import analyze
setup('repair/final_finish_wait');compatibility()
while not (ROOT/'repair_v1/FINAL_TEST_READY.json').exists():time.sleep(30)
base=ROOT/'runs'/read(ROOT/'repair_v1/FINAL_TEST_READY.json')['run']
while not (base/'COMPUTE_DRAINED_RESOURCES_HELD.json').exists():time.sleep(60)
summarize(base,'final_test');safety('final_test');details('final_test');analyze()
subprocess.run([sys.executable,'-B',str(ROOT/'code/repair_rescore_audit.py'),'--run',base.name],check=True,cwd=ROOT)
subprocess.run([sys.executable,'-B',str(ROOT/'code/repair_audit.py'),'--execution','configs/repair_final_execution_v1.json','--retain'],check=True,cwd=ROOT)
atomic(ROOT/'repair_v1/FINAL_SCIENCE_READY.json',dict(status='PASS',time=stamp(),run=base.name))
