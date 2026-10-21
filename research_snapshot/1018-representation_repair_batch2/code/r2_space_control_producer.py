"""Prepare matched control experiment; formal release remains an agent decision."""
from r2_common import *
from r2_resume_support import register_once,enqueue


def main():
    setup('space_control_producer')
    import numpy as np
    from r2_coarse_producer import balanced
    preparation=ROOT/'analysis/control_space_preparation/outcome_control_space_preparation_fold0_K2.json'
    while not preparation.exists():time.sleep(30)
    prepared=read(preparation);bases=prepared['bases'];source=read(ROOT/'manifests/data_source.json');rows=read(source['rows'])
    bank_path=next(p for p in (ROOT/'analysis/responses/candidate_bank_v1').glob('*.json') if read(p).get('mode')=='heldout' and read(p).get('heldout_fold')==0 and read(p).get('system')=='representation_K2_seed0');bank=read(bank_path)
    with np.load(ROOT/bank['matrix']) as z:ii=np.array(z['global_indices']);s=np.array(z['scores'])
    old=read(ROOT/'analysis/correction_diagnostics/SUMMARY.json');gt={int(v['index']):v['gt'] for v in old['per_configuration']['interface_pre_0.1']};eligible=[int(i) for i,v in zip(ii,np.all(s[:,0,:,0]<.7,axis=1)) if v and gt[int(i)]>.9];panel=balanced(eligible,rows,24,dict(space_control_panel=20261018,held=0));assert len(panel)==24
    protocol=ROOT/'config/SPACE_CONTROLLABILITY_PROTOCOL_V1.json'
    if not protocol.exists():atomic(protocol,dict(status='FROZEN_DIAGNOSTIC_DESIGN',time=stamp(),diagnostic_fold=0,panel=panel,panel_definition='24 session-balanced exploration-fold0 scenes: actual Base fails in all three observed draws, GT trajectory independently scores>90. Never filter by previous optimizer or expert repair success.',panel_source=str(bank_path.relative_to(ROOT)),panel_source_sha256=sha(bank_path),basis_preparation=str(preparation.relative_to(ROOT)),basis_preparation_sha256=sha(preparation),
        scope='Shared-channel additive perturbation across current valid interface tokens, not arbitrary independent token-channel edits.',sites=['interface_pre','interface_post'],caps=[.02,.1],requested_ranks=[8,32,128],main_ks=128,main_kf=128,quality=['global_failure_vs_shared_success','each_of_K2_group_failures_vs_shared_success'],centering=['uncentered','common_centered'],random_replicates=2,steps=24,score_checkpoints=[0,4,8,12,16,20,24],
        optimization='Same original Adam/GT surrogate/sampler. lr=radius/sqrt(actual_parameter_rank)*.25 matches first-step channel-norm scale; shared-channel norm cap exact. Base retained in trueS0 selection; same chosen vector reused onS1/S2.',
        comparison='First compare each basis with same-rank random controls, same cap/steps/scores and scenes. More quality bases do not license a matched max6-quality versus max2-random claim.',
        main_order='Engineering and existing-cache CPU preparation can run in parallel. Formal batches require explicit MECHANISM_DIAGNOSTICS_RELEASE after reviewing expertization results; no automatic scientific decision.',validation_accessed=False,test_accessed=False))
    stage=ROOT/'runs/space_control_engineering_v1';handler='code/r2_space_controllability.py';queue=read(stage/'tasks.json') if (stage/'tasks.json').exists() else [];known={t['id'] for t in queue}
    for index in panel[:2]:
        paths=list((ROOT/'analysis/case_corrections').glob('*_%06d.json'%index));references=[(p,read(p)) for p in paths]
        for block in ['interface_pre','interface_post']:
            for cap in [.02,.1]:
                p,ref=next((p,d) for p,d in references if d['block']==block and d['cap']==cap and d['steps']==24)
                spec=dict(indices=[index],diagnostic_fold=0,block=block,cap=cap,steps=24,space='full',rank=1536 if block.endswith('pre') else 384,reference_compare=str(p.relative_to(ROOT)));ident='space_control_eng_'+digest(spec)[:24];enqueue(queue,known,dict(id=ident,**spec))
            selected=[next(b for b in bases if b['config']['block']==block and b['config']['kind']=='global_quality_residual' and b['config']['centered']),next(b for b in bases if b['config']['block']==block and b['config']['kind']=='Haar_random' and b['config']['replicate']==0)]
            for basis in selected:
                spec=dict(indices=[index],diagnostic_fold=0,block=block,cap=.1,steps=8,space=basis['config']['kind'],rank=min(8,basis['rank']),basis=basis);ident='space_control_eng_'+digest(spec)[:24];enqueue(queue,known,dict(id=ident,**spec))
    if not (stage/'tasks.json').exists():atomic(stage/'tasks.json',queue);atomic(stage/'producer.json',dict(complete=True,tasks=len(queue),time=stamp(),engineering_only=True))
    register_once(dict(name=stage.name,path=str(stage.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=8))
    while not all((stage/'receipts'/(t['id']+'.json')).exists() for t in queue):time.sleep(30)
    workers=set();exact=0
    for task in queue:
        r=read(stage/'receipts'/(task['id']+'.json'));workers.add(r['worker'])
        for record in r['result']['records']:
            d=read(ROOT/record['path']);assert np.isfinite(d['gradient_norms']).all() and max(d['gradient_norms'])>0
            if task['space']=='full':assert d['reference_exact'];exact+=1
    proof=ROOT/'provenance/SPACE_CONTROLLABILITY_ENGINEERING_PASS.json'
    if not proof.exists():atomic(proof,dict(status='PASS',time=stamp(),tasks=len(queue),actual_worker_processes=len(workers),full_cached_optimizers_match_original_raw_trajectory_score_and_delta_arrays=exact,quality_and_random_nonzero_gradients=True,Base_at_zero_exact=True,recorded_actual_cap=True,only_two_exploration_diagnostic_scenes=True))
    release=ROOT/'config/MECHANISM_DIAGNOSTICS_RELEASE.json'
    while not release.exists():time.sleep(60)
    r=read(release);assert r['status']=='RELEASED_AFTER_EXPERTIZATION_REVIEW'
    formal=ROOT/'runs/space_controllability_v1';tasks=[];known=set();ineligible=[]
    for block in ['interface_pre','interface_post']:
        entries=[dict(space='full',rank=1536 if block.endswith('pre') else 384)]
        for b in bases:
            if b['config']['block']!=block:continue
            if b['rank']<1:ineligible.append(b);continue
            ranks=sorted({min(v,b['rank']) for v in [8,32,128]})
            for rank in ranks:entries.append(dict(space=b['config']['kind'],rank=rank,basis=b))
        for entry in entries:
            for cap in [.02,.1]:
                for start in range(0,len(panel),2):
                    spec=dict(indices=panel[start:start+2],diagnostic_fold=0,block=block,cap=cap,steps=24,**entry);ident='space_control_'+digest(spec)[:24];enqueue(tasks,known,dict(id=ident,**spec))
    if not (formal/'tasks.json').exists():atomic(formal/'tasks.json',tasks)
    else:assert digest(read(formal/'tasks.json'))==digest(tasks)
    atomic(formal/'producer.json',dict(complete=True,tasks=len(tasks),case_configurations=sum(len(t['indices']) for t in tasks),ineligible=ineligible,time=stamp(),release_sha256=sha(release),finite_stage_only=True,global_queues_and_nodes_retained=True))
    register_once(dict(name=formal.name,path=str(formal.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=25,enabled=False))
    atomic(ROOT/'analysis/space_controllability/SUBMISSION.json',dict(time=stamp(),tasks=len(tasks),panel=panel,ineligible=ineligible,formal=True))


if __name__=='__main__':main()
