"""Fix direct acceptor dispatch; reuse every original numerical function."""
from common import *
import argparse,runpy,subprocess
from vlm_elastic_registry import DEST
from vlm_elastic_entry import SCRIPTS

def main(a):
    assert a.script in SCRIPTS
    setup('vlm_repair/elastic_adapter_v2/'+Path(a.script).stem)
    for name in ['EXECUTION.json','ACCEPTOR_RECOVERY_EXECUTION.json']:
        for p,h in read(DEST/name)['code_sha256'].items():assert sha(ROOT/p)==h,p
    import vlm_final_accept
    from vlm_elastic_accept import audit_participating_ranks
    vlm_final_accept.audit32=audit_participating_ranks
    if os.environ.get('VLM_ELASTIC_CONTROLLER_FOLDER'):
        from repair_queue_v2 import atomic_unique as atomic
        folder=Path(os.environ['VLM_ELASTIC_CONTROLLER_FOLDER']).resolve();assert folder.is_relative_to(DEST)
        atomic(folder/'adapter_ready'/a.script,dict(status='ADAPTER_INSTALLED',time=stamp(),pid=os.getpid(),script=a.script,
            original_source_sha256=sha(ROOT/'code'/a.script),dynamic_rank_acceptance=True,direct_acceptor_dispatch_fixed=True))
    original=subprocess.Popen
    def popen(command,*args,**kwargs):
        if isinstance(command,(list,tuple)):
            position=next((i for i,p in enumerate(command) if str(p).endswith('.py')),None)
            if position is not None:
                target=Path(command[position]).resolve()
                if target.parent==ROOT/'code' and target.name in SCRIPTS:
                    command=[*command[:position],str(Path(__file__).resolve()),'--script',target.name,'--',*command[position+1:]]
        return original(command,*args,**kwargs)
    subprocess.Popen=popen
    arguments=a.arguments[1:] if a.arguments[:1]==['--'] else a.arguments
    sys.argv=[str(ROOT/'code'/a.script),*arguments]
    if a.script=='vlm_final_accept.py':
        # run_path would define audit32 again in a different __main__ namespace.
        # Invoke the unchanged imported main with its original CLI contract.
        parser=argparse.ArgumentParser();parser.add_argument('--study',choices=['primary','semantic'],required=True)
        assert vlm_final_accept.main.__globals__['audit32'] is audit_participating_ranks
        return vlm_final_accept.main(parser.parse_args(arguments))
    return runpy.run_path(str(ROOT/'code'/a.script),run_name='__main__')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--script',required=True);p.add_argument('arguments',nargs=argparse.REMAINDER);main(p.parse_args())
