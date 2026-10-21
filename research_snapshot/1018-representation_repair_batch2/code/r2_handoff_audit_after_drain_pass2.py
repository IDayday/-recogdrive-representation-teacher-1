"""One read-only owner audit after the second B1 receipt-boundary pass."""
from r2_common import *


def main():
    f=ROOT/'resources/handoffs/peer_b1_20261019'
    while not(f/'drain_pass2/SUSPENDED_SAFE.json').exists():
        if any((f/'drain_pass2'/n).exists() for n in ['FAILED.json','ATTENTION.json']):return
        time.sleep(10)
    from types import SimpleNamespace
    from r2_handoff_claim_audit_v3 import main as audit
    path='resources/handoffs/peer_b1_20261019/CLAIM_AUDIT_AFTER_DRAIN_PASS2.json';audit(SimpleNamespace(output=path));data=read(ROOT/path)
    atomic(f/'FRESH_CLAIM_AUDIT_PASS2_READY.json',dict(time=stamp(),audit=path,audit_sha256=sha(ROOT/path),
        unresolved_scientific_claims=sum(not v['resident_admission_wrapper'] and not v['prior_failure_exists'] for v in data['target_pending']),
        empty_claim_observations=len(data['empty_claim_observations']),read_only=True))


if __name__=='__main__':main()
