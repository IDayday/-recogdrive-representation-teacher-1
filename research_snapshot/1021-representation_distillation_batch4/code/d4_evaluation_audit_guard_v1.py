"""Preserve auditor-level exceptions in addition to per-receipt failures."""
from d4_common_v2 import *
import argparse
import traceback


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    try:
        from d4_evaluation_audit_v1 import main
        main(a)
    except BaseException as error:
        atomic(ROOT/'runs/evaluation_audit_workers'/(a.node+'_FAILED.json'),dict(status='FAILED',time=stamp(),node=a.node,
            error=repr(error),traceback=traceback.format_exc()))
        raise
