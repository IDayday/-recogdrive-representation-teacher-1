"""Reuse the verified checkpoint pool for two original unfinished 4096D tasks."""
from common import *
import argparse,shutil
from vlm_core import VOUT
from vlm_fold_backup_v2 import OUT,BASE,CELLS,prepare_train,aggregate
from repair_queue_v2 import append,atomic_unique as atomic

def prepare():
    assert read(OUT/'ENGINEERING_PASS.json')['status']=='PASS'
    assert not (OUT/'EXTENSION_PROTOCOL.json').exists()
    active=[]
    for path in sorted((VOUT/'scan/workers').glob('rank*.json')):
        state=read(path)
        if state['status']!='COMPUTING' or state['rank']>=32:continue
        cell=state['task'];proof=read(VOUT/'cells'/(cell+'.json'))
        if cell in CELLS or proof['shape'][1]!=4096 or proof['valid_cases']!=103288:continue
        if (VOUT/'scan/receipts'/(cell+'.json')).exists():continue
        active.append(cell)
    chosen=sorted(set(active))[:2];assert len(chosen)==2
    for cell in chosen:
        source=VOUT/'cells'/(cell+'.json');p=read(source);assert sha(ROOT/p['path'])==p['sha256']
        assert not (OUT/'cells'/source.name).exists();shutil.copyfile(source,OUT/'cells'/source.name)
    atomic(OUT/'EXTENSION_PROTOCOL.json',dict(status='FROZEN_BEFORE_EXTENSION',time=stamp(),cells=chosen,
        selection='Lexicographic first two valid original unfinished active 4096D tasks; no CV or outcome used',
        code_sha256=sha(Path(__file__)),original_engineering_sha256=sha(OUT/'ENGINEERING_PASS.json'),
        maximum_additional_cells=2,existing_worker_pool_only=True,no_new_gpu_or_nodes=True,no_old_scan_changed=True,
        adoption='Only after original jobs/pods terminate; committed original results always preferred'))
    append(BASE,[dict(id=cell+'__held'+str(k),kind='held',cell=cell,fold=k) for cell in chosen for k in range(5)])
    print('TWO_ADDITIONAL_ORIGINAL_CELLS_CHECKPOINT_REGISTERED',chosen,flush=True)

def controller():
    setup('vlm_repair/fold_backup/extension');p=read(OUT/'EXTENSION_PROTOCOL.json');assert sha(Path(__file__))==p['code_sha256']
    from threadpoolctl import threadpool_limits
    with threadpool_limits(4):
        while True:
            for cell in p['cells']:
                if not prepare_train(cell):continue
                marker=OUT/'work'/cell/'DIRECTIONS_APPENDED.json'
                if not marker.exists():
                    append(BASE,[dict(id=cell+f'__c{cc}f{k}',kind='direction',cell=cell,centered=cc,fold=k) for cc in [0,1] for k in range(5)])
                    atomic(marker,dict(status='PASS',time=stamp(),tasks=10,extension=True))
                aggregate(cell)
            if all((OUT/'completed'/(cell+'.json')).exists() for cell in p['cells']):
                atomic(OUT/'EXTENSION_COMPLETE.json',dict(status='PASS',time=stamp(),cells=p['cells'],original_results_untouched=True));return
            time.sleep(10)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','controller']);a=parser.parse_args()
    try:globals()[a.mode]()
    except BaseException as exc:
        import traceback
        atomic(ROOT/'provenance/fold_backup_errors'/('extension_'+a.mode+'.json'),dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()));raise
