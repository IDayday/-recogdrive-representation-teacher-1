"""New user-authorized B1 handoff, reusing the verified durable-boundary algorithm."""
from r2_common import *
import r2_peer_b1_boundary_drain as original
original.DEST=ROOT/'resources/handoffs/peer_b1_20261019_round2/drain_pass2'
if __name__=='__main__':
    try:original.main()
    except BaseException as error:
        import traceback
        atomic(original.DEST/'FAILED.json',dict(time=stamp(),error=repr(error),traceback=traceback.format_exc(),no_automatic_recovery=True))
        raise
