"""Unadopted CPU prototype proof against saved exact original direction outputs."""
from common import *
import argparse,traceback
import numpy as np
from vlm_fold_backup_v2 import OUT as BACKUP,BASE,unpack
from vlm_core import VOUT
from vlm_space import metrics
from repair_queue_v2 import atomic_unique as atomic
DEST=VOUT/'fast_space_probe_v1'

def main(a):
    setup('vlm_repair/fast_space_probe');os.nice(10)
    import vlm_space_fast_prototype as fast
    from threadpoolctl import threadpool_limits
    protocol=read(DEST/'EXECUTION.json')
    for p,h in protocol['code_sha256'].items():assert sha(ROOT/p)==h,p
    cell=a.cell;proof=read(BASE/'receipts'/(cell+f'__c{a.centered}f{a.fold}.json'));reference=ROOT/proof['path'];assert sha(reference)==proof['sha256']
    input_path=BACKUP/'work'/cell/f'train{a.fold}.npz'
    with np.load(input_path) as z:mom=unpack(z)
    construction=int(digest(dict(cell=cell,vlm_space_root=20261016))[:16],16)
    with threadpool_limits(a.threads):
        start=time.monotonic();result=fast.directions(mom,bool(a.centered),construction);seconds=time.monotonic()-start
        w,c,status,ranks,degen=result
        with np.load(reference) as ref:
            assert np.array_equal(status,ref['status']),'status'
            assert np.array_equal(ranks,ref['ranks']),'ranks'
            assert np.array_equal(degen,ref['degenerate']),'degenerate'
            assert np.array_equal(c,ref['center']),'center'
            use=(status==0)&~degen;rw=np.array(ref['w'][:,use]);nw=w[:,use]
            relative=np.linalg.norm(nw-rw,axis=0)/np.maximum(np.linalg.norm(rw,axis=0),1e-20)
            max_relative=float(relative.max());max_abs=float(np.max(np.abs(nw-rw)))
            assert max_relative<1e-6,(max_relative,max_abs)
            # Same actual held-out feature rows, independent of quality/readout.
            source=read(BACKUP/'cells'/(cell+'.json'));x=np.load(ROOT/source['path'],mmap_mode='r')[:128].astype(np.float64)
            old=(x-c)@rw;new=(x-c)@nw
            assert np.allclose(old,new,rtol=1e-6,atol=1e-6)
    p=DEST/(cell+f'__c{a.centered}f{a.fold}.json')
    atomic(p,dict(status='PASS_NUMERIC_PROTOTYPE_NOT_ADOPTED',time=stamp(),cell=cell,centered=a.centered,fold=a.fold,threads=a.threads,
        seconds=seconds,original_saved_seconds=proof['seconds'],ratio_to_saved_original=seconds/proof['seconds'],
        maximum_nondegenerate_direction_relative_difference=max_relative,maximum_nondegenerate_direction_absolute_difference=max_abs,
        original_status_ranks_centers_degeneracy_exact=True,actual_feature_projections_agree=True,statistics=fast.LAST_STATS,
        input_sha256=sha(input_path),reference_sha256=proof['sha256'],no_current_frozen_program_changed=True))
    print('FAST_SPACE_PROTOTYPE_PROBE_PASS_NOT_ADOPTED',str(p.relative_to(ROOT)),seconds,seconds/proof['seconds'],fast.LAST_STATS,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cell',required=True);p.add_argument('--centered',type=int,choices=[0,1],default=0);p.add_argument('--fold',type=int,default=0);p.add_argument('--threads',type=int,default=4);a=p.parse_args()
    try:main(a)
    except BaseException as exc:
        atomic(ROOT/'provenance/fast_space_probe_errors'/(a.cell+f'__c{a.centered}f{a.fold}.json'),dict(status='OPTIONAL_PROTOTYPE_FAILED_NOT_ADOPTED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()));raise
