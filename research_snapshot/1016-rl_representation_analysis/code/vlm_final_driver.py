"""Freeze actual final parents/nulls and append test plus full-train replay to retained workers."""
from common import *
import numpy as np
from vlm_core import VOUT
from vlm_scan import save_npz
from vlm_results import summarize
from vlm_repair_queue_v6 import stage
from repair_queue_v2 import atomic_unique as atomic
BASE=ROOT/'runs/vlm_global_refine_20261016_v5';G=VOUT/'global_funnel';FINAL=VOUT/'final'

def null_part(parent,kind,replicate):
    a=dict(parent,control_kind=kind,control=True,control_parent=parent['id'])
    if kind=='haar_rotation':
        with np.load(ROOT/parent['fit_path']) as f:arrays={k:np.array(f[k]) for k in f.files}
        d,r=arrays['basis'].shape;rng=np.random.default_rng(int(digest(dict(parent=parent['id'],replicate=replicate,vlm_final_null=20261016))[:16],16))
        q,z=np.linalg.qr(rng.standard_normal((d,r)),mode='reduced');q*=np.where(np.diag(z)>=0,1.,-1.)[None,:];arrays['haar']=q.astype('float32')
        if parent['method']=='support_projection':
            q,z=np.linalg.qr(rng.standard_normal((d,d)));q*=np.where(np.diag(z)>=0,1.,-1.)[None,:];arrays['full_haar']=q.astype('float32')
        path=FINAL/'fits'/(parent['id']+f'__haar{replicate}.npz');h=save_npz(path,**arrays);a.update(fit_path=str(path.relative_to(ROOT)),fit_sha256=h,construction_replicate=replicate)
        atomic(path.with_suffix('.json'),dict(status='PASS',time=stamp(),parent=parent,replicate=replicate,sha256=h,scope='fixed independent orthogonal latent rotation, native RNG untouched',native_bf16_budget='same proposed norm and hard actual cap; report actual rounded edit distributions'))
    a.pop('id');a['id']='null_'+digest(a)[:18];return a

def null(parent,kind,replicate=0):
    if parent['method']!='combination':return null_part(parent,kind,replicate)
    parts=[null_part(p,kind,replicate) for p in parent['parts']];a=dict(parent,parts=parts,control=True,control_kind=kind,control_parent=parent['id'],construction_replicate=replicate);a.pop('id');a['id']='null_'+digest(a)[:18];return a

def engineering(arms,parents):
    import subprocess
    request=FINAL/'ENGINEERING_REQUEST.json';atomic(request,dict(arms=arms,parents=parents))
    # Existing stage compute is finished; this task-owned one-shot process exits normally.
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='0')
    for k in ['RANK','LOCAL_RANK','WORLD_SIZE','LOCAL_WORLD_SIZE','GROUP_RANK','ROLE_RANK','ROLE_WORLD_SIZE']:env.pop(k,None)
    log=(FINAL/'engineering.log').open('a')
    subprocess.run([sys.executable,'-u','-B',str(ROOT/'code/vlm_final_engineering.py')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True);log.close()
    assert read(FINAL/'ENGINEERING_PASS.json')['status']=='PASS'

def main():
    setup('vlm_repair/final_driver');FINAL.mkdir(exist_ok=True)
    while not (G/'FINAL_CANDIDATE_LOCK.json').exists():time.sleep(20)
    lock=read(G/'FINAL_CANDIDATE_LOCK.json');global_parents=list({v['arm']['id']:v['arm'] for v in lock['roles'].values()}.values());parents=list({v['arm']['id']:v['arm'] for v in list(lock['roles'].values())+list(lock['component_diagnostics'].values())}.values())
    if not (FINAL/'TEST_LOCK.json').exists():
        controls=[null(p,kind,j) for p in global_parents for kind,j in [('reverse',0),('haar_rotation',0),('haar_rotation',1),('haar_rotation',2)]]
        atomic(FINAL/'TEST_LOCK.json',dict(status='FROZEN_BEFORE_TEST',time=stamp(),parents=parents,global_parents=global_parents,controls=controls,arms=parents+controls,seeds=[0,1,2,3,4],
            primary_roles={k:v['arm']['id'] for k,v in lock['roles'].items()},component_diagnostics={k:v['arm']['id'] for k,v in lock['component_diagnostics'].items()},source_selection_sha256=sha(G/'FINAL_CANDIDATE_LOCK.json'),
            inference='session bootstrap and sign-flip with seeds averaged inside case; Holm for deduplicated primary, direction-control and component diagnostic families separately',bootstrap=2000,sign_flips=10000,inference_seed=20261016))
    frozen=read(FINAL/'TEST_LOCK.json')
    while len(read(BASE/'tasks.json'))!=len(list((BASE/'receipts').glob('*.json'))):time.sleep(10)
    if not (FINAL/'ENGINEERING_PASS.json').exists():engineering(frozen['arms'],frozen['parents'])
    rows=read(ROOT/'candidate_repair_v1/analysis/final_test/rows.json')
    if not (BASE/'stages/final_test/PROTOCOL.json').exists():stage(BASE,'final_test',rows,frozen['arms'],[0,1,2,3,4],chunk=2,arm_chunk=64)
    train=read(ROOT/'manifests/natural_s0.json')
    if not (BASE/'stages/navtrain_locked/PROTOCOL.json').exists():stage(BASE,'navtrain_locked',train,frozen['global_parents'],[0,1,2],chunk=2,arm_chunk=64)
    atomic(FINAL/'PRIMARY_STAGES_APPENDED.json',dict(status='PASS',time=stamp(),test_cases=len(rows),test_arms=len(frozen['arms']),test_seeds=5,train_cases=len(train),train_arms=len(frozen['global_parents']),train_seeds=3,resources_retained=True))
    for name in ['final_test','navtrain_locked']:
        while True:
            r=summarize(BASE,name)
            if r is not None:break
            time.sleep(30)
    atomic(FINAL/'PRIMARY_INFERENCE_COMPLETE.json',dict(status='PASS',time=stamp(),code_and_protocol_frozen=True,semantic_correction_and_full_search_may_still_be_pending=True))
if __name__=='__main__':
    try:main()
    except BaseException as error:
        import traceback
        atomic(VOUT/'failures/final_driver.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise
