"""Small real RL/candidate/score/interface pipeline in an independent process."""
from r3_common import *
import argparse
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import socket
import traceback


def main(args):
    setup('smoke/'+args.node+'/device'+str(args.device));compatibility()
    import numpy as np
    import torch
    from vlm_intervene_v4 import Engine
    from vlm_core import raw_features
    from worker import load_features
    from repair_engine import baseline_row
    from repair_score import score_group
    from r3_runtime import Fits,prediction,candidate_condition,init_scorer,optimize
    from r2_counterfactual import edited_value
    config=read(ROOT/args.config);rows=read(config['rows']);dest=ROOT/'runs/engineering_v1'/args.node/('device%02d'%args.device)
    assert socket.gethostname().startswith(args.job+'-')
    atomic(dest/'LIVE.json',dict(status='LOADING_MODEL',time=stamp(),job=args.job,pid=os.getpid()))
    engine=Engine();fit1=Fits(BATCH1);fit2=Fits(BATCH2);checks=[];began=time.monotonic()
    assert engine.planner_runtime['checkpoint_sha256']==config['checkpoint_sha256']
    with ProcessPoolExecutor(max_workers=2,mp_context=mp.get_context('spawn'),initializer=init_scorer) as pool:
        for index in config['indices']:
            row=rows[index];features=raw_features(row);reference=baseline_row(row);arrays={};records=[];started=time.monotonic()
            with torch.no_grad():
                hidden=engine.forward_native(features)
                for candidate in config['candidates']:
                    for j in config['seeds']:
                        condition,post,statistics=candidate_condition(engine,candidate,features,hidden,j,row['token'],fit1,fit2)
                        trajectory,interface=prediction(engine,features,condition,j,row['token'],post)
                        ident=candidate['id']+'_S'+str(j);arr=trajectory.float().cpu().numpy()
                        if candidate['kind']=='Base':
                            native=engine.trajectory(features,hidden,seed(row['token'],j));assert torch.equal(native,trajectory)
                            if j==0:assert np.array_equal(arr,reference['trajectory'])
                        mask=engine.inputs['attention_mask'][0].bool();target=interface[0,mask].float().cpu().numpy()
                        assert target.ndim==2 and target.shape[-1]==384 and np.isfinite(target).all()
                        arrays[ident]=target
                        records.append(dict(arm=candidate['id'],kind=candidate['kind'],seed_index=j,seed=seed(row['token'],j),trajectory=arr.tolist(),statistics=statistics,
                                            interface_key=ident,interface_sha256=hashlib.sha256(target.tobytes()).hexdigest(),same_execution_interface=True))
            if config.get('optimization'):
                _,gt,_=load_features(row,engine.cfg);opt=config['optimization']
                parameters,trace=optimize(engine,features,gt.cuda().float(),row['token'],opt['noise_indices'],opt['block'],opt['group'],opt['cap'],opt['steps'])
                with torch.no_grad():
                    for step,delta in zip(trace,parameters):
                        changed,stat=edited_value(engine,opt['block'],opt['group'],torch.tensor(delta,device='cuda'),opt['cap']);condition,post=engine.suffix(opt['block'],changed)
                        for j in config['seeds']:
                            trajectory,interface=prediction(engine,features,condition,j,row['token'],post);ident='optimization_step'+str(step['step'])+'_S'+str(j)
                            target=interface[0,engine.inputs['attention_mask'][0].bool()].float().cpu().numpy();arrays[ident]=target
                            records.append(dict(arm='optimization_step'+str(step['step']),kind='case_optimization',seed_index=j,seed=seed(row['token'],j),trajectory=trajectory.cpu().numpy().tolist(),
                                                interface_key=ident,interface_sha256=hashlib.sha256(target.tobytes()).hexdigest(),same_execution_interface=True,optimization_noise_indices=opt['noise_indices'],GT_assisted=True))
            scored=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=records)).result(timeout=1800)
            native=next(v for v in scored if v['kind']=='Base' and v['seed_index']==0);assert native['score']==reference['score']
            out=dest/(row['token']+'.npz');out.parent.mkdir(parents=True,exist_ok=True)
            assert not out.exists()
            with out.open('wb') as stream:np.savez_compressed(stream,**arrays)
            atomic(dest/(row['token']+'.json'),dict(status='COMPLETE',time=stamp(),row=row,records=scored,interfaces=str(out.relative_to(ROOT)),interfaces_sha256=sha(out),seconds=time.monotonic()-started))
            checks.append(dict(token=row['token'],records=len(scored),Base_S0_exact=True,same_execution_interfaces=True))
            engine.verify_engine();atomic(dest/'LIVE.json',dict(status='CASE_BOUNDARY',time=stamp(),checks=checks,pid=os.getpid()))
    atomic(dest/'PASS.json',dict(status='PASS_SINGLE_DEVICE_ENGINEERING',time=stamp(),node=args.node,job=args.job,device=args.device,planner=engine.planner_runtime,
           checks=checks,seconds=time.monotonic()-began,not_multi_device_acceptance=True,source_sha256=sha(Path(__file__)),runtime_sha256=sha(ROOT/'code/r3_runtime.py')))
    print(json.dumps(dict(status='PASS_SINGLE_DEVICE_ENGINEERING',checks=checks,seconds=time.monotonic()-began)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--job',required=True);p.add_argument('--device',type=int,required=True);p.add_argument('--config',required=True)
    a=p.parse_args()
    try:main(a)
    except BaseException as error:
        atomic(ROOT/'runs/engineering_v1'/a.node/('device%02d'%a.device)/'FAILED.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        raise
