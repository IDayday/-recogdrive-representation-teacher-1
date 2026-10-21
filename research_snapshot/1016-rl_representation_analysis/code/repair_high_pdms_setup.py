"""Honor the user's dual priorities: validate the exploration winner without the damage guard."""
from common import *
import subprocess
from repair_queue_v2 import stage

def main():
    setup('repair/high_pdms_setup');compatibility()
    root=ROOT/'repair_v1';base=ROOT/'runs'/read(root/'ACTIVE_RUN.json')['run'];pool=[]
    for name in ['screen','natural_learn_screen','sensitivity_screen','budget_control','early_quality_screen']:
        for r in read(root/'analysis'/name/'SUMMARY.json')['summaries']:
            if r['arm']['method'] in ['random','random_subspace','reverse'] or r['arm'].get('control'):continue
            pool.append(dict(r,selection_source=name))
    best=max(pool,key=lambda r:r['population_weighted_screen_delta']);arm=best['arm']
    already={a['id'] for p in (base/'stages').glob('validation_*/arms.json') for a in read(p)}
    assert arm['id'] not in already, 'This setup is unnecessary if the unconstrained winner is already queued'
    path=root/'high_pdms_validation_arms.json';assert not path.exists();atomic(path,[arm])
    proof=root/'HIGH_PDMS_VALIDATION_SMOKE.json'
    subprocess.run([sys.executable,'-B',str(ROOT/'code/repair_gate_smoke.py'),'--arms',str(path.relative_to(ROOT)),
        '--output',str(proof.relative_to(ROOT))],check=True,cwd=ROOT)
    tasks=stage(base,'validation_high_pdms',read(root/'validation.json'),[arm],[0,1,2],chunk=24)
    atomic(root/'HIGH_PDMS_VALIDATION_ENQUEUED.json',dict(status='COMPLETE',time=stamp(),tasks=tasks,best=best,
        reason='Explicit user request to retain both PDMS-priority and safety-priority candidates; no damage guard on this exploration winner.',
        validation_or_test_used_for_selection=False))
    print(json.dumps(dict(status='HIGH_PDMS_VALIDATION_ENQUEUED',tasks=tasks,arm=arm['id'])),flush=True)

if __name__=='__main__':main()
