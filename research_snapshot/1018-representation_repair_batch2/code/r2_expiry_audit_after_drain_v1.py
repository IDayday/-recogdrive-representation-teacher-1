"""Mechanical read-only owner audit after an agent-authorized expiry drain."""
from r2_common import *
import argparse
from types import SimpleNamespace


def main(args):
    setup('expiry_audit/'+args.node)
    folder=(ROOT/args.folder).resolve()
    assert folder.is_relative_to(ROOT/'resources/expiry')
    intent=read(folder/'INTENT.json')
    assert intent['node']==args.node
    while not (folder/'drain/SUSPENDED_SAFE.json').exists():
        time.sleep(30)
    import r2_expiry_claim_audit_v1 as audit
    output=str((folder/'CLAIM_AUDIT.json').relative_to(ROOT))
    audit.main(SimpleNamespace(job=intent['job'],
        workers=str((folder/'drain/WORKERS_BEFORE.json').relative_to(ROOT)),
        drain_proof=str((folder/'drain/SUSPENDED_SAFE.json').relative_to(ROOT)),output=output))
    atomic(folder/'FRESH_CLAIM_AUDIT_READY.json',dict(time=stamp(),
        status='READY_FOR_AGENT_OWNER_AUDIT_REVIEW',audit=output,audit_sha256=sha(ROOT/output),
        no_process_or_resource_action=True))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--node',required=True)
    p.add_argument('--folder',required=True)
    main(p.parse_args())
