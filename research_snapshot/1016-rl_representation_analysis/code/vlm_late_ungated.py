"""Actual ungated late parents on per-seed Base failures; preserve all other outputs."""
from common import *
from vlm_core import VOUT
from vlm_late_qualification import DEST
from vlm_ungated_final import one
from repair_queue_v2 import atomic_unique as atomic


def main():
    setup('vlm_repair/late_ungated')
    base=ROOT/'runs/vlm_global_refine_20261016_v5'
    while True:
        if (DEST/'NO_COMPETITIVE_CANDIDATES.json').exists():
            atomic(DEST/'UNGATED_COMPLETE.json',dict(status='PASS',time=stamp(),no_competitive=True));return
        if (DEST/'FINAL_OPERATOR_ENGINEERING_PASS.json').exists() and (base/'stages/final_test_late/PROTOCOL.json').exists():break
        time.sleep(30)
    one('late',DEST/'TEST_LOCK.json',DEST/'ungated')
    atomic(DEST/'UNGATED_COMPLETE.json',dict(status='PASS',time=stamp(),actually_computed=True))


if __name__=='__main__':
    try:main()
    except BaseException as exc:
        import traceback
        atomic(DEST/'failures/ungated.json',dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()));raise
