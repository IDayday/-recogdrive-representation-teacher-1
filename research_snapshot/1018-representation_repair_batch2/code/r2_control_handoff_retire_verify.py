"""Confirm terminal old metadata processes, then release the prepared standby.

No signal is sent. Addresses the exit-time empty-cmdline observation only.
"""
from r2_common import *
import psutil


def main():
    assert socket.gethostname().startswith('dlcqdtslnqnytsc7-')
    folder = ROOT/'resources/handoffs/peer_b1_20261019/control_migration'
    manifest = read(folder/'RETIRE_INTENT.json'); observations = []
    records = [manifest['old_parent']]+[c['process'] for c in manifest['active']]
    for iteration in range(2):
        checked = []
        for record in records:
            try:
                p = psutil.Process(record['pid']); assert p.create_time() == record['created']
                status = p.status(); assert status == psutil.STATUS_ZOMBIE, (record['pid'], status)
            except psutil.NoSuchProcess: status = 'ABSENT'
            checked.append(dict(pid=record['pid'], created=record['created'], status=status))
        observations.append(dict(time=stamp(), processes=checked))
        if iteration == 0: time.sleep(1)
    guard=(RUN/'control_plane/LEADER.lock').open('a+')
    fcntl.flock(guard, fcntl.LOCK_EX|fcntl.LOCK_NB); fcntl.flock(guard, fcntl.LOCK_UN); guard.close()
    assert not (folder/'RETIRED.json').exists()
    atomic(folder/'RETIRED.json', dict(status='EXACT_METADATA_CONTROLLERS_RETIRED', time=stamp(),
        manifest=manifest, old_parent_dead=True, all_old_metadata_children_dead=True,
        twice_terminal_observations=observations, no_GPU_CPU_scientific_worker_or_DLC_main_stopped=True,
        exit_time_verification_recovered='Original check saw process cmdline empty during termination; no retirement was retried and no additional signals sent.'))
    print(json.dumps(dict(status='PASS_TERMINAL_RETIREMENT_VERIFIED', observations=2, processes=len(records))))


if __name__ == '__main__': main()
