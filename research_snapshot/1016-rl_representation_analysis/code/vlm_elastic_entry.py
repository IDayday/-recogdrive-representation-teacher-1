"""Scoped launch adapter for CPU acceptors; frozen numerical sources stay intact."""
from common import *
import argparse,runpy,subprocess
from vlm_elastic_registry import DEST

SCRIPTS={'vlm_postcompute.py','vlm_analysis_finalize.py','vlm_all_finalize.py','vlm_four_finalize.py','vlm_five_finalize.py',
         'vlm_final_accept.py','vlm_late_accept.py','vlm_qneighbor_accept.py','vlm_obs_gate_accept.py'}

def main(a):
    assert a.script in SCRIPTS
    setup('vlm_repair/elastic_adapter/'+Path(a.script).stem)
    execution=read(DEST/'EXECUTION.json')
    for p,h in execution['code_sha256'].items():assert sha(ROOT/p)==h,p
    import vlm_final_accept
    from vlm_elastic_accept import audit_participating_ranks
    vlm_final_accept.audit32=audit_participating_ranks
    if os.environ.get('VLM_ELASTIC_CONTROLLER_FOLDER'):
        from repair_queue_v2 import atomic_unique as atomic
        folder=Path(os.environ['VLM_ELASTIC_CONTROLLER_FOLDER']).resolve();assert folder.is_relative_to(DEST)
        atomic(folder/'adapter_ready'/a.script,dict(status='ADAPTER_INSTALLED',time=stamp(),pid=os.getpid(),script=a.script,
            original_source_sha256=sha(ROOT/'code'/a.script),dynamic_rank_acceptance=True))
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
    runpy.run_path(str(ROOT/'code'/a.script),run_name='__main__')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--script',required=True);p.add_argument('arguments',nargs=argparse.REMAINDER);main(p.parse_args())
