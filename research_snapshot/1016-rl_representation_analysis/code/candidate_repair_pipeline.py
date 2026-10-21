"""Foreground-wait orchestration; all new stages are probed and frozen before appending."""
from common import *
import subprocess
from candidate_repair_monitor import wait
from candidate_repair_fit import OUT

def run_phase(name,output_stage):
    base=ROOT/'runs/candidate_repair_20261016_v1'
    if (base/'stages'/output_stage/'PROTOCOL.json').exists():return
    print(json.dumps(dict(event='FOLLOWUP_START',phase=name,time=stamp())),flush=True)
    subprocess.run([sys.executable,'-B',str(ROOT/'code/candidate_repair_followup.py'),name],cwd=ROOT,check=True)

def main():
    setup('candidate_repair/pipeline')
    phases=[('coarse','replay','replay'),('replay','validation','validation'),
        ('combination_screen','combinations','validation_combinations'),('validation_combinations','finalists','validation_controls')]
    for until,phase,out in phases:
        wait(until)
        if phase=='finalists':wait('validation')
        run_phase(phase,out)
    wait('validation_controls')
    atomic(OUT/'DEVELOPMENT_READY.json',dict(status='PASS',time=stamp(),selection_lock_sha256=sha(OUT/'BEHAVIOR_SELECTION_LOCK.json'),
        all_development_computation_complete=True,final_test_not_yet_appended=True))
    print(json.dumps(dict(event='DEVELOPMENT_READY',time=stamp())),flush=True)

if __name__=='__main__':main()
