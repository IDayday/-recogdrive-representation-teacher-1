"""Append predeclared matched subspace and leading-method null controls, no validation selection."""
from common import *
import subprocess
from repair_queue_v2 import stage

def main():
    setup('repair/matched_setup');compatibility()
    root=ROOT/'repair_v1';base=ROOT/'runs'/read(root/'ACTIVE_RUN.json')['run']
    assert not (base/'stages/validation_matched/PROTOCOL.json').exists()
    arms=read(root/'subspace_validation_arms.json')
    screen=read(root/'analysis/screen/SUMMARY.json')
    parent=max([r for r in screen['summaries'] if r['arm']['method']=='mean'],key=lambda r:r['population_weighted_screen_delta'])['arm']
    for method in ['random','random_subspace','reverse']:
        arm=dict(parent,method=method,matched_parent=parent['id'],control=True)
        arm.pop('id');arm['id']='matched_'+method+'_'+digest(arm)[:12];arms.append(arm)
    path=root/'matched_validation_arms.json';atomic(path,arms)
    proof=root/'MATCHED_VALIDATION_SMOKE.json'
    subprocess.run([sys.executable,'-B',str(ROOT/'code/repair_gate_smoke.py'),'--arms',str(path.relative_to(ROOT)),
        '--output',str(proof.relative_to(ROOT))],check=True,cwd=ROOT)
    tasks=stage(base,'validation_matched',read(root/'validation.json'),arms,[0,1,2],chunk=16)
    atomic(root/'MATCHED_VALIDATION_ENQUEUED.json',dict(status='COMPLETE',time=stamp(),tasks=tasks,arms=len(arms),
        selection='fixed strengths predeclared; null parent selected solely from exploration screen',parent=parent,
        proof_sha256=sha(proof),learned_fit_sha256=read(root/'SUBSPACE_FITS_READY.json')['sha256']))
    print(json.dumps(dict(status='MATCHED_VALIDATION_ENQUEUED',tasks=tasks,arms=len(arms))),flush=True)

if __name__=='__main__':main()
