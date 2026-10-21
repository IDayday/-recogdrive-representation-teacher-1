"""Verified renewal entry: persist cloud lifetime before identity activation."""
from common import *
import argparse
import vlm_self_renewal as previous
from vlm_elastic_registry import DEST,configuration
from vlm_elastic_manage import status
from vlm_clone_manage import command

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','submit','activate']);p.add_argument('--legacy-id');p.add_argument('--id')
    p.add_argument('--devices',default=','.join(map(str,range(16))));p.add_argument('--cpu-workers',type=int,default=80);a=p.parse_args();setup('vlm_repair/self_renewal_v2')
    for name in ['EXECUTION.json','CLONE_EXECUTION.json','SELF_RENEWAL_EXECUTION.json','SELF_RENEWAL_ENTRY_EXECUTION.json']:
        for path,h in read(DEST/name)['code_sha256'].items():assert sha(ROOT/path)==h,path
    if a.mode=='prepare':previous.prepare(a)
    elif a.mode=='submit':c=configuration(a.id);previous.retirement(c);previous.submit(c)
    else:
        c=configuration(a.id);previous.retirement(c);status(c);previous.activate(c)
        command(argparse.Namespace(id=a.id,script='code/vlm_clone_pending_bootstrap.py',arguments_json=json.dumps(['--id',a.id])))
