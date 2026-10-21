"""Independent final checks of frozen natural scores, events and own-K Oracle."""
from r2_common import *
import argparse
from collections import Counter


def main(args):
    setup('natural_final_acceptance',threads=2)
    import numpy as np
    stage=(ROOT/args.stage).resolve();assert stage.is_relative_to(ROOT/'runs')
    done=read(stage/'completion_monitor/COMPLETE.json');mode=done['mode'];assert mode in ['validation','test']
    assessment=read(ROOT/done['assessment']['path']);pack=read(ROOT/assessment['pack']);lock=read(ROOT/assessment['lock'])
    assert assessment['status']=='COMPLETE_NATURAL_EVALUATION'
    assert sha(ROOT/assessment['pack'])==assessment['pack_sha256']==lock['pack_sha256']
    assert sha(ROOT/assessment['rows'])==assessment['rows_sha256']==lock['rows_sha256']
    assert lock['status']=='FROZEN_BEFORE_CONFIRMATION' and lock['final_test_selection_frozen']
    assert sha(ROOT/assessment['matrix'])==assessment['matrix_sha256']
    tasks=read(stage/'tasks.json');receipts=[read(p) for p in (stage/'receipts').glob('*.json')]
    assert {t['id'] for t in tasks}=={r['task']['id'] for r in receipts}
    assert not list((stage/'failures').glob('*.json'))
    with np.load(ROOT/assessment['matrix']) as z:
        score=np.array(z['scores']);arms=list(z['arms']);panel=np.array(z['panel']);seeds=[int(v) for v in z['seeds']]
    n=17475 if mode=='validation' else 12146;expected_seeds=[0,1,2] if mode=='validation' else [0,1,2,3,4]
    assert score.dtype==np.float64 and score.shape[0]==n and score.shape[2:]==(len(expected_seeds),7)
    assert np.isfinite(score).all() and seeds==expected_seeds and len(set(panel))==n
    rows=read(ROOT/assessment['rows']);assert len(rows)==n and all(r['subset']==mode for r in rows)
    base=score[:,arms.index('baseline')];extra={}
    def events(value):return np.stack([value[:,:,1]<1,value[:,:,2]<1,value[:,:,0]==0,value[:,:,3]<1,value[:,:,0]<.7],-1)
    for config in pack['policies']:
        ident=config['id'];value=score[:,arms.index(ident)];result=assessment['results'][ident]
        assert np.allclose((value[:,:,0]-base[:,:,0]).mean(0)*100,result['PDMS_gain_by_noise'],atol=1e-12,rtol=0)
        old=events(base);new=events(value);added=(new&~old).sum(0);removed=(old&~new).sum(0)
        assert np.array_equal(added,result['newly_bad_by_noise']) and np.array_equal(removed,result['resolved_bad_by_noise'])
        assert np.array_equal(added-removed,result['net_bad_by_noise'])
        extra[ident]=dict(high_to_failure_by_noise=np.sum((base[:,:,0]>.9)&(value[:,:,0]<.7),0).tolist())
        if config['kind']=='Base':continue
        policy=read(ROOT/config['policy']);assert sha(ROOT/config['policy'])==config['policy_sha256']
        parts=policy['configuration']['model']['parts'] if config['kind'] in ['joint','finite'] else policy['parts']
        candidates=score[:,[arms.index('baseline')]+[arms.index('candidate_'+p['id']) for p in parts]]
        oracle=candidates[:,:,:,0].max(1)
        assert abs(((oracle-base[:,:,0])*100).mean()-assessment['privileged_diagnostics'][ident]['actual_candidate_oracle']['mean_PDMS_gain'])<1e-12
        K=len(parts);comparison='matched_'+str(K+1)+'_Base_draw_oracle'
        if comparison in assessment['privileged_diagnostics'][ident]:
            control=score[:,[arms.index('baseline')]+[arms.index('base_resample_'+str(i)) for i in range(1,K+1)]]
            actual=((control[:,:,:,0].max(1)-base[:,:,0])*100).mean()
            assert abs(actual-assessment['privileged_diagnostics'][ident][comparison]['mean_PDMS_gain'])<1e-12
    stats=read(ROOT/done['statistics']['path']);assert stats['cases']==n and stats['hypotheses']==12
    strata=read(ROOT/done['stability']['path']);assert strata['cases']==n and sum(strata['stratum_counts'].values())==n
    target=stage/'AGENT_FINAL_ACCEPTANCE_V1.json';assert not target.exists()
    result=dict(status='PASS_COMPLETE_FROZEN_NATURAL_'+mode.upper(),time=stamp(),
        assessment=done['assessment'],assessment_sha256=sha(ROOT/done['assessment']['path']),
        statistics=done['statistics'],stability=done['stability'],cases=n,noise_indices=seeds,
        matrix_shape=list(score.shape),matrix_sha256=assessment['matrix_sha256'],chunks=len(tasks),
        worker_job_chunks=dict(Counter(r['worker'].split('-master-')[0] for r in receipts)),
        all_direct_PDMS_and_events_recomputed=True,all_own_K_oracles_and_matched_Base_recomputed=True,
        additional_high_to_failure=extra,pack_sha256=assessment['pack_sha256'],
        no_candidate_or_parameter_reselection=True,source_sha256=sha(Path(__file__)))
    atomic(target,result);print(json.dumps({k:result[k] for k in ['status','cases','noise_indices','matrix_shape','chunks','worker_job_chunks']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);main(p.parse_args())
