"""Complete null statistics and compare parent on identical cases, not independent samples."""
from common import *
import numpy as np
import subprocess
from repair_analysis import summarize,safety
from repair_result_details import details

def main():
    setup('repair/null_accept');compatibility()
    base=ROOT/'runs'/read(ROOT/'repair_v1/TRUE_RANDOM_READY.json')['run'];stage='validation_true_random'
    assert (base/'COMPUTE_DRAINED_RESOURCES_HELD.json').exists()
    summary=summarize(base,stage);safety(stage);details(stage)
    path=ROOT/'repair_v1/analysis'/stage;matrix=np.load(path/'scores.npy');arms=read(path/'arms.json');rows=read(path/'rows.json')
    old=ROOT/'repair_v1/analysis/validation_repair';oldmatrix=np.load(old/'scores.npy');parent=read(ROOT/'repair_v1/TRUE_RANDOM_PROTOCOL.json')['parent']
    pi=next(i+1 for i,a in enumerate(read(old/'arms.json')) if a['id']==parent['id'])
    assert [r['token'] for r in rows]==[r['token'] for r in read(old/'rows.json')]
    assert np.array_equal(matrix[:,:,0],oldmatrix[:,:,0])
    sessions=np.array([r['session'] for r in rows]);unique=np.unique(sessions);counts=np.array([(sessions==s).sum() for s in unique])
    rng=np.random.default_rng(20261016);draw=rng.integers(len(unique),size=(500,len(unique)));comparisons=[]
    targets=[(a['id'],matrix[:,:,i+1,0]) for i,a in enumerate(arms)]
    for kind in ['direction','subspace']:
        ii=[i+1 for i,a in enumerate(arms) if a['gaussian_null']==kind]
        targets.append((kind+'_mean_over_3_construction_seeds',matrix[:,:,ii,0].mean(2)))
    for label,score in targets:
        delta=oldmatrix[:,:,pi,0]-score;case=delta.mean(0);sums=np.array([case[sessions==s].sum() for s in unique])
        boot=sums[draw].sum(1)/counts[draw].sum(1)*100
        comparisons.append(dict(control=label,parent_minus_control_pdms=float(delta.mean()*100),session_bootstrap_ci95=np.quantile(boot,[.025,.975]).tolist()))
    atomic(path/'PARENT_COMPARISONS.json',dict(status='PASS',time=stamp(),parent=parent,comparisons=comparisons,
        all_matched_base_scores_exact=True,construction_seeds_not_independent_cases=True))
    subprocess.run([sys.executable,'-B',str(ROOT/'code/repair_audit.py'),'--execution','configs/repair_null_execution_v1.json','--retain'],check=True,cwd=ROOT)
    print(json.dumps(dict(status='NULL_ACCEPTED',records=summary['records'])),flush=True)

if __name__=='__main__':main()
