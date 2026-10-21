"""Matched failed scenes: cyclic equal-budget seen versus fold-held repair banks."""
from r2_common import *


def main():
    setup('seen_unseen_audit')
    import numpy as np
    source=read(ROOT/'manifests/data_source.json');q=np.load(source['quality']);available={};rows=[]
    for path in (ROOT/'analysis/expert_library_selection').glob('*.json'):
        selection=read(path);response=ROOT/'analysis/responses/expert_library_S0_v1'/path.name
        if response.exists():available[(selection['heldout_fold'],selection['system'])]=(path,selection,response)
    for path in (ROOT/'analysis/responses/candidate_bank_v1').glob('*.json'):
        bank=read(path)
        if bank.get('mode')!='heldout' or '_K2_seed0' not in bank['system']:continue
        held=bank['heldout_fold'];seen_fold=(held+1)%5;other=available.get((seen_fold,bank['system']))
        if other is None:continue
        selection_path,selection,response_path=other;response=read(response_path)
        with np.load(ROOT/bank['matrix']) as z:indices=np.array(z['global_indices']);unseen=np.array(z['scores']);ids=list(z['arm_ids'])
        with np.load(ROOT/response['matrix']) as z:other_indices=np.array(z['global_indices']);seen=np.array(z['scores']);other_ids=list(z['arm_ids'])
        selected=np.flatnonzero(q[indices]<.7);positions={int(i):j for j,i in enumerate(other_indices)};aligned=np.asarray([positions[int(indices[j])] for j in selected]);assert np.array_equal(unseen[selected,0,0],seen[aligned,0,0])
        point=read(ROOT/bank['point']);configuration=next(c for c in point['policies'] if c['id']=='PDMS_trajectory');policy=read(ROOT/configuration['policy'])
        a=[0]+[ids.index(p['id']) for p in policy['parts']];b=[0]+[other_ids.index(v) for _,v in sorted(selection['policies']['PDMS'].items(),key=lambda p:int(p[0]))];assert len(a)==len(b)==3
        first=unseen[selected][:,a,0,0].max(1);second=seen[aligned][:,b,0,0].max(1)
        rows.append(dict(system=bank['system'],heldout_fold=held,seen_model_excluded_fold=seen_fold,cases=len(selected),Base_pdms=float(unseen[selected,0,0,0].mean()*100),
            held_oracle_pdms=float(first.mean()*100),seen_oracle_pdms=float(second.mean()*100),seen_minus_held_oracle=float((second-first).mean()*100),
            held_repaired90=int(np.sum(first>.9)),seen_repaired90=int(np.sum(second>.9)),held_bank=str(path.relative_to(ROOT)),held_matrix_sha256=bank['matrix_sha256'],
            seen_selection=str(selection_path.relative_to(ROOT)),seen_response=str(response_path.relative_to(ROOT)),seen_matrix_sha256=response['matrix_sha256']))
    folder=ROOT/'analysis/seen_unseen_gap'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S');path=folder/'SUMMARY.json'
    atomic(path,dict(status='EXPLORATORY_MATCHED_SCENE_AUDIT',time=stamp(),comparisons=rows,anchor_noise=0,experts_each=2,identity_additional=True,
        design='Unseen model excludes the scene session fold f; seen model excludes the next cyclic fold (f+1)%5, so it was allowed to fit these scenes. Neither uses final validation/test.',
        limitation='Different fitting folds can change grouping, location and selected configuration. This is a response generalization diagnostic, not a controlled causal memorization proof. Do not treat three fold0 comparisons as a global result.',
        validation_accessed=False,test_accessed=False))
    atomic(ROOT/'analysis/seen_unseen_gap/LATEST.json',dict(time=stamp(),path=str(path.relative_to(ROOT)),sha256=sha(path)));print(__import__('json').dumps(dict(path=str(path.relative_to(ROOT)),comparisons=len(rows))))


if __name__=='__main__':main()
