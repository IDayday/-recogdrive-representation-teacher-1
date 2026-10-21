"""Run the read-only owner audit as soon as the planned B1 drain is ready."""
from r2_common import *


def main():
    folder=ROOT/'resources/handoffs/peer_b1_20261019'
    while not(folder/'drain/SUSPENDED_SAFE.json').exists():
        if any((folder/'drain'/name).exists() for name in ['FAILED.json','ATTENTION.json']):return
        time.sleep(10)
    assert not(folder/'FRESH_CLAIM_AUDIT_READY.json').exists()
    from types import SimpleNamespace
    from r2_handoff_claim_audit_v2 import main as audit
    path='resources/handoffs/peer_b1_20261019/CLAIM_AUDIT_AFTER_DRAIN.json'
    audit(SimpleNamespace(output=path))
    value=read(ROOT/path)
    atomic(folder/'FRESH_CLAIM_AUDIT_READY.json',dict(time=stamp(),audit=path,audit_sha256=sha(ROOT/path),
        unresolved_scientific_claims=sum(not c['resident_admission_wrapper'] and not c['prior_failure_exists'] for c in value['target_pending']),
        empty_claim_observations=len(value['empty_claim_observations']),no_claim_or_process_mutation=True))


if __name__=='__main__':main()
