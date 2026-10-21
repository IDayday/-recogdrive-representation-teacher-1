"""Release the original deferred scope after canonical coverage, before cold start."""
from common import *
from vlm_core import VOUT
from vlm_quiescence import assert_quiescent
from vlm_scan_schedule import release, SCHED
from repair_queue_v2 import atomic_unique as atomic


def main():
    setup('vlm_repair/release_remaining_grids')
    assert not list((VOUT/'resume').glob('*/CLOUD_READY.json')), 'Run only before the first continuation is submitted.'
    quiescence = assert_quiescent()
    schedule = read(VOUT/'FULL_GRID_SCHEDULE.json')
    assert all((VOUT/'scan/receipts'/(t['id']+'.json')).exists() for t in schedule['canonical'])
    tasks = {t['id']: t for t in read(VOUT/'scan/tasks.json')}
    released = []
    for key in schedule['held']:
        claim = VOUT/'scan/claims'/key
        if not claim.exists():
            continue
        owner = read(claim/'OWNER.json')
        if owner.get('status') != 'SCHEDULER_RESERVED':
            continue
        assert owner['scheduler'] == SCHED
        if (VOUT/'scan/receipts'/(key+'.json')).exists():
            continue
        history = VOUT/'schedule_history'/(key+'.json')
        if history.exists():
            prior = read(history)
            assert prior['prior_owner']['scheduler'] == SCHED
            assert prior['prior_owner']['task']['id'] == key
            # Preserve the original history if expiry interrupted the unlink.
            (claim/'OWNER.json').unlink()
            claim.rmdir()
        else:
            release(tasks[key])
        released.append(key)
    marker = VOUT/'FULL_GRID_ALL_RELEASED.json'
    assert not marker.exists()
    atomic(marker, dict(status='ORIGINAL_DEFERRED_SCOPE_RELEASED_AFTER_CANONICAL_COVERAGE', time=stamp(),
                        canonical_completed=62, released=released, quiescence=quiescence,
                        no_new_scientific_hypotheses=True, frozen_mathematics_unchanged=True,
                        code_sha256=sha(Path(__file__))))
    print('ORIGINAL_REMAINING_GRIDS_RELEASED', len(released), flush=True)


if __name__ == '__main__':
    main()
