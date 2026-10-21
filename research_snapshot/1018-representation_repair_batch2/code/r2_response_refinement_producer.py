"""Stream response-driven subgroup updates and independent own-space refits."""
from r2_common import *
from r2_resume_support import append_once


def main():
    setup('response_refinement_producer')
    queued=set();refitted=set();cells={c['cell']:c for c in read(ROOT/'manifests/cells.json')}
    protocol=ROOT/'config/RESPONSE_REFINEMENT_PROTOCOL_V1.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN',time=stamp(),rounds=1,reason='One complete controlled feedback/refit iteration across all K/families/folds before further adaptive rounds.',
        temperature=.05,prior_mix=.2,risk_weight=.25,unresolved_threshold=.005,unresolved_membership='Preserve parent; no discarded failures',
        refit_sites=['interface_pre','interface_post'],refit_groups=['valid_mean'],centered=[False,True],
        scope='Refit subgroup-specific geometry and behavioral experts; wider initial layer/operator search remains independently active.',validation_fitted=False,test_accessed=False))
    while True:
        group_tasks=[];space_tasks=[]
        for p in sorted((ROOT/'analysis/expert_library_selection').glob('*.json')):
            d=read(p);responses=[ROOT/'analysis/responses'/name/p.name for name in ['expert_library_S0_v1','expert_library_noise_v1']]
            if not all(q.exists() for q in responses):continue
            spec=dict(selection=str(p.relative_to(ROOT)),responses=[str(q.relative_to(ROOT)) for q in responses],temperature=.05,risk_weight=.25)
            ident='outcome_response_update_'+digest(spec)[:24]
            if ident not in queued:group_tasks.append(dict(id=ident,handler='code/r2_response_groups.py',handler_sha256=sha(ROOT/'code/r2_response_groups.py'),**spec));queued.add(ident)
            fold='all' if d['heldout_fold']<0 else f"fold{d['heldout_fold']}";meta_path=ROOT/'analysis/response_refinement'/fold/(d['system']+'_em1.json')
            if not meta_path.exists() or ident in refitted:continue
            meta=read(meta_path)
            for expert in range(meta['K']):
                for site in ['interface_pre','interface_post']:
                    for centered in [False,True]:
                        spec=dict(cell=cells[site+'__valid_mean'],expert=expert,heldout_fold=meta['heldout_fold'],centered=centered,responsibility_meta=str(meta_path.relative_to(ROOT)))
                        space_tasks.append(dict(id='space_learned_em1_'+digest(spec)[:24],handler='code/r2_expert_space.py',handler_sha256=sha(ROOT/'code/r2_expert_space.py'),**spec))
            refitted.add(ident)
        if group_tasks:append_once('cpu',group_tasks)
        if space_tasks:append_once('cpu',space_tasks)
        atomic(ROOT/'analysis/response_refinement/PRODUCER.json',dict(time=stamp(),group_updates_queued=len(queued),group_spaces_queued=len(refitted),rounds=1))
        time.sleep(60)


if __name__=='__main__':main()
