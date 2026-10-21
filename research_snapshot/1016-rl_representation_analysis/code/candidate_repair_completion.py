"""Foreground continuation after development: locked test, final audit and science-ready marker."""
from common import *
import subprocess
from candidate_repair_fit import OUT
from candidate_repair_monitor import wait

def command(*parts):
    subprocess.run([sys.executable,'-B',str(ROOT/'code'/parts[0]),*parts[1:]],cwd=ROOT,check=True)

def main():
    setup('candidate_repair/completion')
    while not (OUT/'DEVELOPMENT_READY.json').exists():
        failures=list((ROOT/'runs/candidate_repair_20261016_v1/failures').glob('*.json'))
        if failures:raise RuntimeError('Development worker failure: '+str(failures[0]))
        time.sleep(30)
    command('candidate_repair_accept.py','development')
    command('candidate_repair_final.py')
    wait('final_test')
    wait('navtrain_full_locked')
    from candidate_repair_followup import summarized
    summarized('final_test')
    summarized('navtrain_full_locked')
    command('candidate_repair_statistics.py')
    command('repair_rescore_audit.py','--run','candidate_repair_20261016_v1')
    command('candidate_repair_accept.py','final')
    atomic(OUT/'SCIENCE_READY.json',dict(status='PASS',time=stamp(),final_acceptance_sha256=sha(OUT/'FINAL_ACCEPTANCE.json'),
        reports_pending=True,resources_retained=True,no_test_driven_reselection=True))
    print(json.dumps(dict(event='SCIENCE_READY',time=stamp())),flush=True)

if __name__=='__main__':main()
