"""Verify completed development artifacts while the retained nodes run the next workload."""
from common import *
import subprocess

def main():
    setup('repair/dev_accept_wait')
    parent=ROOT/'runs/repair_20261016_v2'
    while not (parent/'COMPUTE_DRAINED_RESOURCES_HELD.json').exists() or not (ROOT/'repair_v1/DEVELOPMENT_ANALYSES_COMPLETE.json').exists():time.sleep(60)
    subprocess.run([sys.executable,'-B',str(ROOT/'code/repair_audit.py'),'--execution','configs/repair_execution_v2.json','--retain'],check=True,cwd=ROOT)

if __name__=='__main__':main()
