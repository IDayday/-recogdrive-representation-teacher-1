"""Use otherwise empty global-queue gaps for already frozen later coarse stages.

Same queue, model, panel, fits, operators, seeds and stage names as the original
late/semantic producers. One stage at a time; stop before primary validation.
"""
from common import *
import fcntl,traceback
from vlm_core import VOUT
from vlm_semantic import SEM
from vlm_funnel import arms
from vlm_repair_queue_v6 import stage
from repair_queue_v2 import atomic_unique as atomic

BASE=ROOT/'runs/vlm_global_refine_20261016_v5'
DEST=VOUT/'ready_coarse_prefill'


def manifest():
    path=DEST/'MANIFEST.json'
    if path.exists():return read(path)
    q=read(VOUT/'late_token_coverage/QDA_SELECTION_LOCK.json');fits=[]
    for spec in q['selected']:
        fit=read(VOUT/'late_token_coverage/fits'/(digest(spec)[:20]+'.json'))['fit']
        assert fit['spec']==spec;fits.append(dict(stage='late_coarse_'+fit['id'],fit=fit,source='frozen_qda_neighbors'))
    assert (SEM/'repair/FITS_READY.json').exists()
    for p in sorted((SEM/'repair/fits').glob('*.json')):
        fit=read(p)['fit'];fits.append(dict(stage='sem_coarse_'+fit['id'],fit=fit,source='frozen_corrected_semantic'))
    assert len(fits)==259 and len({r['stage'] for r in fits})==259
    result=dict(status='FROZEN_COMPATIBLE_STAGE_MANIFEST',time=stamp(),stages=fits,
        no_validation_or_test_results_used=True,no_additional_fit_or_candidate=True)
    atomic(path,result);return result


def main():
    setup('vlm_repair/ready_coarse_prefill');DEST.mkdir(exist_ok=True)
    for p,h in read(VOUT/'READY_COARSE_PREFILL_EXECUTION.json')['code_sha256'].items():assert sha(ROOT/p)==h,p
    with (DEST/'controller.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        choices=manifest()['stages'];rows=read(VOUT/'development/COARSE_PANEL.json');assert len(rows)==32
        while True:
            if ((BASE/'stages/validation_main/PROTOCOL.json').exists()
                or (VOUT/'global_funnel/FINAL_CANDIDATE_LOCK.json').exists()):
                atomic(DEST/'DONE.json',dict(status='STOPPED_NEW_PREFILL_AT_PRIMARY_VALIDATION',time=stamp(),queues_still_open=True));return
            ready=all((BASE/f'node{n}/SMOKE_PASS.json').exists() for n in [0,1])
            tasks=len(read(BASE/'tasks.json')) if (BASE/'tasks.json').exists() else 0
            receipts=len(list((BASE/'receipts').glob('*.json')))
            if ready and tasks==receipts:
                item=next((r for r in choices if not (BASE/'stages'/r['stage']/'PROTOCOL.json').exists()),None)
                if item is None:
                    atomic(DEST/'DONE.json',dict(status='ALL_COMPATIBLE_COARSE_STAGES_ALREADY_PRESENT',time=stamp(),queues_still_open=True));return
                fit=item['fit'];assert sha(ROOT/fit['path'])==fit['sha256']
                # Recheck the early cutoff immediately before the append. The
                # original later producers remain behind the full-validation,
                # locked-test and engineering barriers, far beyond this cutoff.
                if (BASE/'stages/validation_main/PROTOCOL.json').exists():continue
                count=stage(BASE,item['stage'],rows,arms(fit),[0],chunk=2,arm_chunk=64)
                atomic(DEST/'appended'/(item['stage']+'.json'),dict(status='APPENDED_IDENTICAL_FROZEN_STAGE',
                    time=stamp(),stage=item['stage'],tasks=count,fit_sha256=fit['sha256'],
                    panel_sha256=sha(VOUT/'development/COARSE_PANEL.json'),
                    original_producer_will_reuse_same_protocol_and_outputs=True))
                print('READY_COARSE_PREFILLED',item['stage'],count,flush=True)
            atomic(DEST/'STATUS.json',dict(time=stamp(),all_32_global_smokes_ready=ready,
                pending=tasks-receipts,appended=len(list((DEST/'appended').glob('*.json'))),
                original_main_processes_and_scientific_parameters_unchanged=True))
            time.sleep(5)


if __name__=='__main__':
    try:main()
    except BaseException as exc:
        atomic(VOUT/'late_token_coverage/failures/ready_coarse_prefill.json',dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()));raise
