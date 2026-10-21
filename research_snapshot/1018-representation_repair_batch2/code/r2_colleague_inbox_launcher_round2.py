"""Reuse the validated independent launcher with this handoff's new acceptance gate."""
from r2_common import *
import r2_colleague_inbox_launcher as original

original.DEST=ROOT/'resources/handoffs/peer_b1_20261019_round2/colleague_launcher'

if __name__=='__main__':original.main()
