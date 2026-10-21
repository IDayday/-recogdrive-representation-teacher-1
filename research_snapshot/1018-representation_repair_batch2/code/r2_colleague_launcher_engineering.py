"""Actual CPU-only command/receipt/dedup smoke in an isolated handoff inbox."""
from r2_common import *
import argparse
import subprocess

FOLDER=ROOT/'resources/handoffs/peer_b1_20261019/launcher_engineering'


def child():
    import r2_colleague_inbox_launcher as module
    module.DEST=FOLDER/'inbox'
    module.main()


def main():
    import psutil
    assert socket.gethostname().startswith('dlcqdtslnqnytsc7-')
    assert not (FOLDER/'PASS.json').exists()
    folder=FOLDER/'inbox';folder.mkdir(parents=True,exist_ok=True)
    script=FOLDER/'cpu_smoke.sh';script.write_text('#!/usr/bin/env bash\nset -euo pipefail\nprintf "%s\\n" "$1"\n')
    atomic(FOLDER/'ACCEPTED_EMPTY_FOR_OWNER.json',dict(engineering_fixture_only=True,not_formal_handoff_acceptance=True))
    atomic(folder/'OWNER_ACTIVATION.json',dict(expected_job='dlcqdtslnqnytsc7',task_root=str(FOLDER)))
    pending=folder/'pending/one_cpu_command.json'
    atomic(pending,dict(expected_job='dlcqdtslnqnytsc7',script=str(script),script_sha256=sha(script),cwd=str(FOLDER),
        arguments=['handoff smoke literal value'],env={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1'}))
    log=(FOLDER/'launcher.log').open('a')
    p=subprocess.Popen([sys.executable,'-u','-B',str(Path(__file__).resolve()),'child'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    receipt=folder/'receipts/one_cpu_command.json';state=folder/'states/one_cpu_command.json'
    try:
        end=time.monotonic()+90
        while time.monotonic()<end:
            assert p.poll() is None
            if state.exists() and read(state)['status']=='COMPLETE':break
            time.sleep(1)
        assert state.exists() and read(state)['returncode']==0
        before=sha(receipt);time.sleep(17)
        assert sha(receipt)==before and (folder/'logs/one_cpu_command.log').read_text()=='handoff smoke literal value\n'
        assert not psutil.Process(p.pid).children(recursive=True)
        atomic(FOLDER/'PASS.json',dict(status='PASS_ACTUAL_JOB_INDEPENDENT_INBOX_CHAIN',time=stamp(),
            job='dlcqdtslnqnytsc7',source_sha256=sha(ROOT/'code/r2_colleague_inbox_launcher.py'),
            cpu_script_started_and_finished=True,arguments_and_log_exact=True,duplicate_dispatch_skipped=True,
            no_GPU_or_experiment_queue_used=True,formal_handoff_not_claimed=True))
    finally:
        if p.poll() is None:p.terminate()
        p.wait(timeout=10);log.close()
    print('COLLEAGUE_LAUNCHER_ACTUAL_CPU_ENGINEERING_PASS')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['child','main']);a=p.parse_args();globals()[a.mode]()
