"""Smoke the prepared natural-evaluation program using exploration anchors only."""
from r2_common import *
from r2_resume_support import register_once


def main():
    while not (ROOT/'provenance/CONTEXT_CRITIC_ENGINEERING_PASS.json').exists():time.sleep(15)
    stage=ROOT/'runs/frozen_pack_engineering_v1';policies=[]
    for kind,folder in [('hard','routers'),('candidate','candidate_selectors'),('joint','joint_policies')]:
        selected=[]
        for p in (ROOT/folder).glob('*/POLICY.json'):
            d=read(p)
            if d.get('heldout_fold')!=-1 or d.get('system')!='representation_K2_seed0':continue
            if d.get('role')!='PDMS' or d.get('tier')!='trajectory':continue
            selected.append((p,d))
        assert selected,'Preverified engineering policy unexpectedly missing: '+kind
        for j,(p,d) in enumerate(selected):policies.append(dict(id='engineering_'+kind+'_'+str(j),kind=kind,policy=str(p.relative_to(ROOT)),policy_sha256=sha(p)))
    trained=read(ROOT/'token_critics/token_critic_pilot_v1/TRAINING.json');source_point=read(ROOT/read(ROOT/trained['task']['responses'][0])['point']);by_id={p['id']:p for p in source_point['arms']}
    parts=[by_id[v] for _,v in sorted(source_point['policies']['PDMS'].items(),key=lambda p:int(p[0]))]
    for label,path,view in [('full','token_critics/token_critic_pilot_v1/TRAINING.json','post_valid'),('uniform','pooled_token_critics/uniform_token_critic_pilot_v1/TRAINING.json','post_valid'),('pre','context_critics/pre_all/context_pre_all_engineering_v1/TRAINING.json','pre_all')]:
        model=read(ROOT/path);p=stage/'policies'/(label+'.json');policy=dict(heldout_fold=-1,parts=parts,critic=dict(checkpoint=model['checkpoints'][-1],heldout_fold=-1,context_view=view,threshold=.01,risk_penalty=0.))
        atomic(p,policy);policies.append(dict(id='engineering_token_'+label,kind='token',policy=str(p.relative_to(ROOT)),policy_sha256=sha(p)))
    policies.append(dict(id='engineering_Base',kind='Base'));pack=stage/'PACK.json';atomic(pack,dict(policies=policies,include_raw_experts=True))
    source=read(ROOT/'manifests/data_source.json');lock=stage/'LOCK.json';atomic(lock,dict(status='ENGINEERING_ONLY',pack_sha256=sha(pack),rows_sha256=source['rows_sha256'],authorized_modes=['engineering'],final_test_selection_frozen=False))
    panel=read(ROOT/'config/EVAL_SMOKE_POINT_v2.json')['panel'];spec=dict(id='frozen_pack_engineering_v1_actual',stage=str(stage.relative_to(ROOT)),mode='engineering',lock=str(lock.relative_to(ROOT)),lock_sha256=sha(lock),pack=str(pack.relative_to(ROOT)),pack_sha256=sha(pack),rows=source['rows'],rows_sha256=source['rows_sha256'],panel=panel,start=0,end=len(panel),seeds=[0,1,2],reference_mode='navtrain_archive')
    task=dict(id='frozen_pack_engineering_v1',stage=str(stage.relative_to(ROOT)),evaluation=spec)
    if not (stage/'tasks.json').exists():atomic(stage/'tasks.json',[task]);atomic(stage/'producer.json',dict(complete=True,tasks=1,time=stamp()))
    register_once(dict(name='frozen_policy_pack_engineering_before_confirmation',path=str(stage.relative_to(ROOT)),handler='code/r2_frozen_pack_smoke.py',handler_sha256=sha(ROOT/'code/r2_frozen_pack_smoke.py'),kind='custom',priority=8))


if __name__=='__main__':main()
