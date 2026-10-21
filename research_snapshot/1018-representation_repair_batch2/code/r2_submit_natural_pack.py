"""Submit an explicitly frozen, shared-specification natural evaluation.

No policy selection, cloud resource operation, or automatic test admission.
All job sizes use the existing elastic dispatcher and small configurable chunks.
"""
from r2_common import *
from r2_resume_support import register_once
import argparse


def main(args):
    assert args.name.replace('_','').replace('-','').isalnum()
    mode=args.mode;pack_path=Path(args.pack).resolve();lock_path=Path(args.lock).resolve();rows_path=Path(args.rows).resolve()
    assert all(p.is_relative_to(ROOT) for p in [pack_path,lock_path,rows_path])
    pack=read(pack_path);lock=read(lock_path)
    assert lock['status']=='FROZEN_BEFORE_CONFIRMATION' and mode in lock['authorized_modes']
    assert lock['pack_sha256']==sha(pack_path) and lock['rows_sha256']==sha(rows_path)
    if mode=='test':assert lock['final_test_selection_frozen']
    proof=read(ROOT/'provenance/NATURAL_SHARED_SPEC_ENGINEERING_PASS.json')
    assert proof['status']=='PASS' and proof['all_trajectories_seeds_real_scores_and_decisions_exact']
    rows=read(rows_path);assert rows and all(r['subset']==mode for r in rows)
    if mode=='validation':assert len(rows)==17475
    assert len({r['token'] for r in rows})==len(rows)
    assert any(p['kind']=='Base' for p in pack['policies'])
    stage=ROOT/'runs'/('frozen_natural_'+mode+'_'+args.name);assert not stage.exists()
    handler='code/r2_natural_shared_spec.py';runtime='code/r2_frozen_policy_pack_v2.py'
    specification=dict(mode=mode,pack=str(pack_path.relative_to(ROOT)),pack_sha256=sha(pack_path),lock=str(lock_path.relative_to(ROOT)),lock_sha256=sha(lock_path),
        rows=str(rows_path.relative_to(ROOT)),rows_sha256=sha(rows_path),panel=list(range(len(rows))),seeds=[0,1,2,3,4] if mode=='test' else [0,1,2],
        evaluation_handler=runtime,evaluation_handler_sha256=sha(ROOT/runtime))
    if mode=='validation':specification['reference_mode']='navtrain_archive'
    common=stage/'SPECIFICATION.json';atomic(common,specification);hashed=sha(common);tasks=[]
    assert 1<=args.chunk_size<=32
    for start in range(0,len(rows),args.chunk_size):
        ident=args.name+'_'+str(start).zfill(6)
        tasks.append(dict(id=ident,evaluation_id=ident+'_actual',stage=str(stage.relative_to(ROOT)),specification=str(common.relative_to(ROOT)),specification_sha256=hashed,start=start,end=min(start+args.chunk_size,len(rows))))
    atomic(stage/'tasks.json',tasks);atomic(stage/'producer.json',dict(complete=True,time=stamp(),tasks=len(tasks),mode=mode,rows=len(rows),pack_sha256=sha(pack_path),locked_before_confirmation=True))
    register_once(dict(name='locked_natural_'+mode+'_'+args.name,path=str(stage.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=args.priority))
    atomic(stage/'SUBMISSION.json',dict(status='SUBMITTED_NOT_COMPLETED',time=stamp(),arguments=vars(args),specification_sha256=hashed,source_sha256=sha(ROOT/'code/r2_submit_natural_pack.py'),
        workers_and_devices='Existing elastic Running nodes; no fixed rank count.',no_cloud_operations=True,nodes_retained=True))
    print(json.dumps(dict(stage=str(stage.relative_to(ROOT)),tasks=len(tasks),rows=len(rows),mode=mode,metadata_bytes=(stage/'tasks.json').stat().st_size)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--mode',choices=['validation','test'],required=True)
    for name in ['pack','lock','rows']:p.add_argument('--'+name,required=True)
    p.add_argument('--chunk-size',type=int,default=4);p.add_argument('--priority',type=float,default=17.)
    main(p.parse_args())
