"""Real DSW test smoke, then freeze new final runtime on retained jobs."""
from common import *
import shutil
import subprocess

def main():
    setup('repair/final_setup')
    root=ROOT/'repair_v1'
    while not (root/'FINAL_TEST_INPUTS_READY.json').exists():time.sleep(5)
    info=read(root/'FINAL_TEST_INPUTS_READY.json');run=info['run'];base=ROOT/'runs'/run
    smoke_run='repair_final_dsw_v1';folder=ROOT/'runs'/smoke_run/'stages/final_test';folder.mkdir(parents=True,exist_ok=False)
    shutil.copy2(base/'stages/final_test/panel.json',folder/'panel.json')
    subprocess.run([sys.executable,'-B',str(ROOT/'code/repair_final_queue.py'),'worker','--run',smoke_run,'--rank','0','--dsw'],check=True,cwd=ROOT)
    proof=ROOT/'runs'/smoke_run/'smoke/rank000.json';assert read(proof)['status']=='PASS'
    old=read(ROOT/'configs/repair_execution_v2.json');paths=set(old['code_sha256'])-{'code/repair_queue_v2.py','code/repair_launch_v2.sh'}
    paths.update(['code/repair_final_queue.py','code/repair_test_features.py','code/repair_postprocess.py','configs/repair_final_baseline.json'])
    cfg=dict(time=stamp(),run=run,code_sha256={p:sha(ROOT/p) for p in sorted(paths)},dsw_reference=str(proof.relative_to(ROOT)),
        submissions=old['submissions'],resources=old['resources'],initial_tasks_sha256=sha(base/'tasks.json'),
        test_selection_lock_sha256=sha(root/'TEST_LOCK.json'),arms_sha256=sha(root/'final_test_arms.json'),
        panel_sha256=sha(base/'stages/final_test/panel.json'),fit_sha256=read(root/'TEST_LOCK.json')['fit_sha256'],gate_sha256=read(root/'TEST_LOCK.json')['gate_sha256'],
        retain_resources=True,stage='independent_navtest',model_config='configs/repair_final_baseline.json')
    for p,h in cfg['fit_sha256'].items():assert sha(ROOT/p)==h
    for p,h in cfg['gate_sha256'].items():assert sha(ROOT/p)==h
    cfg['identity']=digest(cfg);atomic(ROOT/'configs/repair_final_execution_v1.json',cfg)
    atomic(root/'FINAL_TEST_READY.json',dict(status='FROZEN',time=stamp(),run=run,execution_sha256=sha(ROOT/'configs/repair_final_execution_v1.json'),dsw_smoke_sha256=sha(proof),
        inputs_proof_sha256=sha(root/'FINAL_TEST_INPUTS_READY.json'),tasks=info['tasks'],cases=info['cases'],seeds=[0,1,2,3,4]))
    print(json.dumps(dict(status='FINAL_TEST_READY',run=run)),flush=True)

if __name__=='__main__':main()
