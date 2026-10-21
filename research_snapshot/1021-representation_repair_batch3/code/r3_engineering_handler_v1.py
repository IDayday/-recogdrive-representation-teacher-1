"""Per-physical-device semantic checks using existing resident frozen models."""
from r3_common import *
import socket


def run(engine,task,pool):
    import numpy as np
    import torch
    from vlm_core import raw_features
    from worker import load_features
    from repair_engine import baseline_row
    from repair_score import score_group
    from r3_runtime import Fits,prediction,candidate_condition,optimize
    from r2_counterfactual import edited_value
    node=task['node'];device=task['device'];dest=ROOT/'runs/resident_engineering_v1'/node/('device%02d'%device)
    config=read(ROOT/'configs/engineering_v1.json');rows=read(config['rows']);fit1=Fits(BATCH1);fit2=Fits(BATCH2);checks=[];began=time.monotonic()
    assert engine.planner_runtime['checkpoint_sha256']==config['checkpoint_sha256']
    for index in config['indices']:
        row=rows[index];features=raw_features(row);reference=baseline_row(row);records=[];captured={}
        with torch.no_grad():
            hidden=engine.forward_native(features);cached,gt,_=load_features(row,engine.cfg)
            assert torch.equal(hidden[0].cpu(),cached['last_hidden_state'])
            for candidate in config['candidates']:
                for j in config['seeds']:
                    condition,post,stats=candidate_condition(engine,candidate,features,hidden,j,row['token'],fit1,fit2)
                    trajectory,interface=prediction(engine,features,condition,j,row['token'],post)
                    key=candidate['id']+'_S'+str(j);arr=interface[0,engine.inputs['attention_mask'][0].bool()].float().cpu().numpy()
                    captured[key]=arr
                    records.append(dict(arm=candidate['id'],seed_index=j,seed=seed(row['token'],j),trajectory=trajectory.cpu().numpy().tolist(),interface_key=key,
                                        interface_sha256=hashlib.sha256(arr.tobytes()).hexdigest(),same_execution_interface=True))
        opt=config['optimization'];parameters,trace=optimize(engine,features,gt.cuda().float(),row['token'],opt['noise_indices'],opt['block'],opt['group'],opt['cap'],opt['steps'])
        with torch.no_grad():
            for delta,step in zip(parameters,trace):
                value,stats=edited_value(engine,opt['block'],opt['group'],torch.tensor(delta,device='cuda'),opt['cap']);condition,post=engine.suffix(opt['block'],value)
                for j in config['seeds']:
                    trajectory,interface=prediction(engine,features,condition,j,row['token'],post);key='optimization_step'+str(step['step'])+'_S'+str(j)
                    arr=interface[0,engine.inputs['attention_mask'][0].bool()].float().cpu().numpy();captured[key]=arr
                    records.append(dict(arm='optimization_step'+str(step['step']),seed_index=j,seed=seed(row['token'],j),trajectory=trajectory.cpu().numpy().tolist(),interface_key=key,
                                        interface_sha256=hashlib.sha256(arr.tobytes()).hexdigest(),same_execution_interface=True))
        scored=pool.submit(score_group,dict(metric_cache=row['metric_cache'],metric_sha256=reference['metric_sha256'],scoring=engine.cfg['scoring'],records=records)).result(timeout=1800)
        golden=read(ROOT/'runs/engineering_v2/replacement_a2/device15'/(row['token']+'.json'))
        expected={(v['arm'],v['seed_index']):v for v in golden['records']}
        for record in scored:
            old=expected[record['arm'],record['seed_index']]
            assert record['trajectory']==old['trajectory'] and record['score']==old['score']
            assert record['interface_sha256']==old['interface_sha256']
        arrays=dest/(row['token']+'.npz');arrays.parent.mkdir(parents=True,exist_ok=True)
        with arrays.open('wb') as stream:np.savez_compressed(stream,**captured)
        atomic(dest/(row['token']+'.json'),dict(status='PASS',time=stamp(),records=scored,interface_file=str(arrays.relative_to(ROOT)),interface_sha256=sha(arrays)))
        checks.append(dict(token=row['token'],records=len(scored),native_hidden_cache_exact=True,all_trajectories_scores_and_interfaces_equal_single_device=True))
        engine.verify_engine()
    result=dict(status='PASS_RESIDENT_PHYSICAL_DEVICE',time=stamp(),node=node,job=task['job'],device=device,
                worker_pid=os.getpid(),hostname=socket.gethostname(),checks=checks,seconds=time.monotonic()-began,
                config_sha256=sha(ROOT/'configs/engineering_v1.json'),handler_sha256=sha(Path(__file__)),runtime_sha256=sha(ROOT/'code/r3_runtime.py'))
    atomic(dest/'PASS.json',result);return result
