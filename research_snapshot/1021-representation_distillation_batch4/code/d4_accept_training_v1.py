"""Check final DDP exposure, checkpoint provenance and frozen development choice."""
from d4_common_v2 import *
import argparse
import math


def main(a):
    setup('training_acceptance/'+a.group,threads=4)
    import numpy as np
    import torch
    family='training_engineering_v4' if a.engineering_smoke else 'distillation_main_v4'
    run=ROOT/'runs'/(family+'_'+a.group);config_path=ROOT/'configs'/family/(a.group+'.json')
    config=read(config_path);hashed=sha(config_path);complete=read(run/'TRAINING_COMPLETE.json')
    assert config['engineering_only']==a.engineering_smoke and config['GT_used'] is False and config['group']==a.group
    assert complete['status']=='ALL_RANKS_TRAINING_COMPLETE_REQUIRES_FULL_EVALUATION' and complete['configuration_sha256']==hashed
    assert not list((run/'failures').glob('*.json'))
    for name,value in config['code_hashes'].items():assert sha(ROOT/'code'/name)==value
    train=read(config['train_indices']);assert sha(config['train_indices'])==config['train_indices_sha256']
    scenes=read(config['scene_manifest']);assert sha(config['scene_manifest'])==config['scene_manifest_sha256']
    assert all(scenes[i]['subset']=='exploration' and scenes[i]['pool'] in ['I','P'] for i in train)
    world=config['world_size'];batch=config['global_batch_size'];assert batch%world==0
    padded=math.ceil(len(train)/batch)*batch;steps=padded//batch*config['epochs'];rank_proofs=[]
    expected=[dict(I=0,P=0) for _ in range(world)]
    for epoch in range(config['epochs']):
        order=np.asarray(train,dtype=np.int64);np.random.default_rng(config['data_seed']+epoch).shuffle(order)
        if padded>len(order):order=np.concatenate([order,order[:padded-len(order)]])
        for rank in range(world):
            for index in order[rank::world]:expected[rank][scenes[int(index)]['pool']]+=1
    manifest=None
    for rank in range(world):
        path=run/'ranks'/('rank%02d'%rank)/'TRAINING_COMPLETE.json';proof=read(path)
        assert proof['status']=='TRAINING_COMPLETE_REQUIRES_FULL_EVALUATION' and proof['rank']==rank and proof['group']==a.group
        assert proof['configuration_sha256']==hashed and proof['optimizer_steps']==steps
        assert proof['local_exposures']==padded//world*config['epochs'] and set(proof['pools'])<=set(expected[rank])
        assert {k:proof['pools'].get(k,0) for k in expected[rank]}==expected[rank]
        assert proof['frozen_original_parameters_unchanged'] and not proof['GT_used']
        assert proof['best']==complete['best'] and proof['final_matched_exposure_checkpoint']==complete['final_matched_exposure_checkpoint']
        m=read(path.parent/'PREFLIGHT.json')['trainable_manifest']
        if manifest is None:manifest=m
        else:assert m==manifest
        rank_proofs.append(dict(path=str(path.relative_to(ROOT)),sha256=sha(path)))
    candidates=[]
    for epoch in range(1,config['epochs']+1):
        path=run/'development'/('epoch%02d'%epoch)/'SUMMARY.json';summary=read(path)
        assert summary['status']=='PASS_DEVELOPMENT_PANEL' and summary['cases']==len(read(config['development_indices']))
        assert summary['GT_used'] is False and summary['student_inference_teacher_or_PDMS_input'] is False
        candidates.append((summary['PDMS'],epoch,str(path.relative_to(ROOT)),sha(path)))
    winner=max(candidates,key=lambda x:(x[0],-x[1]));best=complete['best']
    assert best['epoch']==winner[1] and best['PDMS']==winner[0] and best['development_summary']==winner[2]
    references={v['sha256']:v for v in [complete['final_matched_exposure_checkpoint'],best['checkpoint']]}
    parameters={r['name']:r for r in manifest['trainable']};checkpoint_proofs=[]
    for hashed_checkpoint,ref in references.items():
        path=ROOT/ref['path'];assert sha(path)==hashed_checkpoint
        state=torch.load(path,map_location='cpu',weights_only=False)
        assert state['status']=='DISTILLATION_CHECKPOINT' and state['configuration_sha256']==hashed and state['configuration']==config
        assert state['frozen_parameters_unchanged'] and state['original_checkpoint_sha256']==read(B3/'teachers/first42_v1/PACK.json')['checkpoint_sha256']
        assert set(state['trainable'])==set(parameters)
        for name,tensor in state['trainable'].items():
            assert list(tensor.shape)==parameters[name]['shape'] and tensor.dtype==torch.float32 and torch.isfinite(tensor).all()
        assert state['global_step']==ref['global_step'] and state['epoch']==ref['epoch'] and state['next_micro']==ref['next_micro']==0
        assert len(state['random_states'])==world and {v['rank'] for v in state['random_states']}==set(range(world))
        if ref==complete['final_matched_exposure_checkpoint']:
            assert state['global_step']==steps and state['epoch']==config['epochs']
            assert all(v['exposure']==padded//world*config['epochs'] and
                {k:v['pools'].get(k,0) for k in expected[v['rank']]}==expected[v['rank']] for v in state['random_states'])
        checkpoint_proofs.append(dict(**ref,trainable_tensors=len(state['trainable']),all_trainable_values_finite=True))
        del state
    proof=dict(status='PASS_COMPLETE_MATCHED_EXPOSURE_DDP_TRAINING',time=stamp(),group=a.group,configuration_sha256=hashed,
        ranks=world,optimizer_steps=steps,epochs=config['epochs'],global_scene_exposures=padded*config['epochs'],
        unique_training_scenes=len(train),tail_repeated_exposures=(padded-len(train))*config['epochs'],
        validation_gradient_examples=0,GT_used=False,checkpoint_selection_uses_test_or_new_noise=False,
        frozen_original_parameters_unchanged=True,rank_proofs=rank_proofs,checkpoints=checkpoint_proofs,
        development_endpoints=[dict(PDMS=v[0],epoch=v[1],path=v[2],sha256=v[3]) for v in candidates],
        source_complete_sha256=sha(run/'TRAINING_COMPLETE.json'),evaluation_still_required=True)
    if a.engineering_smoke:
        proof['status']='PASS_TRAINING_ACCEPTOR_ON_REAL_ENGINEERING_CHECKPOINTS'
        proof['engineering_only']=True
        target=ROOT/'provenance'/('TRAINING_ACCEPTOR_ENGINEERING_'+a.group+'_V1.json')
    else:target=run/'TRAINING_AGENT_ACCEPTANCE.json'
    assert not target.exists();atomic(target,proof)
    print(json.dumps({k:proof[k] for k in ['status','group','ranks','optimizer_steps','global_scene_exposures']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--group',choices=['H','T','HT'],required=True);p.add_argument('--engineering-smoke',action='store_true');main(p.parse_args())
