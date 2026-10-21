"""Verify the prepared rolling-handoff source hashes before any operation."""
from common import *
import argparse,runpy
from vlm_elastic_registry import DEST

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--target',choices=['roll','producers'],default='roll');p.add_argument('arguments',nargs=argparse.REMAINDER);a=p.parse_args()
    for path,h in read(DEST/'ROLL_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/path)==h,path
    for path,h in read(DEST/'EXECUTION.json')['code_sha256'].items():assert sha(ROOT/path)==h,path
    target=ROOT/'code'/('vlm_elastic_roll.py' if a.target=='roll' else 'vlm_elastic_producers.py')
    arguments=a.arguments[1:] if a.arguments[:1]==['--'] else a.arguments;sys.argv=[str(target),*arguments]
    runpy.run_path(str(target),run_name='__main__')
