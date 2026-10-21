"""Read-only owner audit for the current user-authorized B1 drain, not historical PIDs."""
from r2_common import *


def main():
    f=ROOT/'resources/handoffs/peer_b1_20261019_round2'
    while not (f/'drain/SUSPENDED_SAFE.json').exists():
        if any((f/'drain'/n).exists() for n in ['FAILED.json','ATTENTION.json']):return
        time.sleep(10)
    from types import SimpleNamespace
    from r2_handoff_claim_audit_v4 import main as audit
    path=str((f/'CLAIM_AUDIT_AFTER_DRAIN.json').relative_to(ROOT))
    audit(SimpleNamespace(output=path,workers=str((f/'drain/WORKERS_BEFORE.json').relative_to(ROOT)),
        drain_proof=str((f/'drain/SUSPENDED_SAFE.json').relative_to(ROOT))))
    d=read(ROOT/path)
    atomic(f/'FRESH_CLAIM_AUDIT_READY.json',dict(time=stamp(),audit=path,audit_sha256=sha(ROOT/path),
        unresolved_scientific_claims=sum(not v['resident_admission_wrapper'] and not v['prior_failure_exists'] for v in d['target_pending']),
        empty_claim_observations=len(d['empty_claim_observations']),read_only=True))


if __name__=='__main__':main()
