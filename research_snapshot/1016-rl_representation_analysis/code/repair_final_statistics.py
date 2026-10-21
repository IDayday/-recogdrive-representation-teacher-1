"""Four prespecified independent-test paired contrasts, sampling seeds averaged per scene."""
from common import *
import numpy as np

def freeze():
    lock=read(ROOT/'repair_v1/TEST_LOCK.json');chosen={k:v['summary']['arm']['id'] for k,v in lock['choices'].items()}
    contrasts=[dict(name='safety_vs_base',positive=chosen['safety_priority'],reference='baseline'),
        dict(name='pdms_vs_base',positive=chosen['pdms_priority'],reference='baseline'),
        dict(name='safety_vs_safe_scale',positive=chosen['safety_priority'],reference=chosen['action_safety_control']),
        dict(name='pdms_vs_pdms_scale',positive=chosen['pdms_priority'],reference=chosen['action_control'])]
    p=ROOT/'repair_v1/FINAL_STATISTICAL_PROTOCOL.json';assert not p.exists()
    atomic(p,dict(status='FROZEN_BEFORE_FINAL_COMPUTE',time=stamp(),contrasts=contrasts,bootstrap=500,sign_flips=20000,
        unit='sampling seeds averaged per case, acquisition session cluster',multiplicity='Holm one-sided PDMS improvement across all four contrasts',
        selection_lock_sha256=sha(ROOT/'repair_v1/TEST_LOCK.json'),no_final_results_used=True))

def analyze():
    folder=ROOT/'repair_v1/analysis/final_test';cfg=read(ROOT/'repair_v1/FINAL_STATISTICAL_PROTOCOL.json');scores=np.load(folder/'scores.npy');rows=read(folder/'rows.json');arms=read(folder/'arms.json')
    ai={'baseline':0,**{a['id']:i+1 for i,a in enumerate(arms)}};sessions=np.array([r['session'] for r in rows]);unique=np.unique(sessions);counts=np.array([(sessions==s).sum() for s in unique]);rng=np.random.default_rng(20261016)
    draw=rng.integers(len(unique),size=(cfg['bootstrap'],len(unique)));signs=rng.choice([-1.,1.],size=(cfg['sign_flips'],len(unique)));records=[]
    for c in cfg['contrasts']:
        delta=(scores[:,:,ai[c['positive']],0]-scores[:,:,ai[c['reference']],0]).mean(0);sums=np.array([delta[sessions==s].sum() for s in unique]);boot=sums[draw].sum(1)/counts[draw].sum(1)*100
        p=(1+np.count_nonzero(signs@sums>=sums.sum()-1e-12))/(cfg['sign_flips']+1)
        records.append(dict(**c,delta_pdms=float(delta.mean()*100),session_bootstrap_ci95=np.quantile(boot,[.025,.975]).tolist(),p_one_sided=float(p),
            session_signflip_null='symmetry of session aggregate paired PDMS differences'))
    order=np.argsort([r['p_one_sided'] for r in records]);maximum=0.
    for j,i in enumerate(order):maximum=max(maximum,min(1.,records[i]['p_one_sided']*(len(order)-j)));records[i]['p_holm']=maximum
    atomic(folder/'FINAL_COMPARISONS.json',dict(status='PASS',time=stamp(),protocol_sha256=sha(ROOT/'repair_v1/FINAL_STATISTICAL_PROTOCOL.json'),records=records))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','analyze']);args=p.parse_args();setup('repair/final_statistics')
    if args.command=='freeze':freeze()
    else:analyze()
