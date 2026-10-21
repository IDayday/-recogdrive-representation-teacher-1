"""Verify the existing fixed teacher file iteration order across active nodes."""
from r2_common import *
import argparse


def main(args):
    node=next(n for n in read(ROOT/'resources/NODES.json')['nodes'] if n['name']==args.node);assert node['job'] in socket.gethostname()
    names=[p.name for p in (ROOT/'analysis/case_corrections').glob('correction_interface_*.json')];assert len(names)==11100
    result=dict(time=stamp(),node=args.node,count=len(names),ordered_names_sha256=digest(names),
        scope='Actual immutable teacher directory order, used by the existing max-score tie behavior. No training target changed.')
    atomic(ROOT/'provenance/target_order'/args.node/'AUDIT.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);main(p.parse_args())
