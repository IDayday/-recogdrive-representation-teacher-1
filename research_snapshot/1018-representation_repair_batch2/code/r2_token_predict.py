"""Predict only on immutable already-generated candidates; preserve true outcomes.

No inference or scoring is repeated for unchanged trajectories. Predictive input
is current full tokens and candidate geometry only. Calibration and held mode are
strictly guarded; true outcomes travel as separate evaluation labels.
"""
from r2_common import *
from concurrent.futures import ThreadPoolExecutor


def run(engine,task,pool):
    import torch
    import numpy as np
    from r2_token_critic import load,inner_session
    from r2_cached_interfaces import from_cached
    from r2_expert_space import save_npz
    from r2_library_rollouts import rows
    from worker import load_features
    point=read(ROOT/task['point']);assert point['mode'] in ['calibration','heldout'];all_rows=rows();data={}
    for path in point['responses']:
        response=read(ROOT/path);assert sha(ROOT/response['matrix'])==response['matrix_sha256']
        with np.load(ROOT/response['matrix']) as z:data[path]={k:np.array(z[k]) for k in ['global_indices','arm_ids','seeds','scores','trajectory']}
    items=point['items'][task['start']:task['end']];selected_ids=['baseline']+[p['id'] for p in point['parts']];output={k:[] for k in ['indices','seeds','scores','trajectory','predicted']};began=time.monotonic()
    def fetch(item):
        path,j=item;index=int(data[path]['global_indices'][j]);features,_,_=load_features(all_rows[index],engine.cfg);return index,features
    with ThreadPoolExecutor(max_workers=1) as reader:
        future=reader.submit(fetch,items[0]) if items else None
        for step,item in enumerate(items):
            index,features=future.result()
            if step+1<len(items):future=reader.submit(fetch,items[step+1])
            row=all_rows[index];held=point['heldout_fold'];fold=int(digest(dict(session=row['session'],cv_root=20261016))[:8],16)%5
            assert row['subset']=='exploration'
            if point['mode']=='heldout':assert held==fold
            else:assert (held<0 or held!=fold) and inner_session(row['session'])
            path,j=item;d=data[path];ids=list(d['arm_ids']);pick=[ids.index(a) for a in selected_ids]
            trajectories=d['trajectory'][j,pick].transpose(1,0,2,3);scores=d['scores'][j,pick].transpose(1,0,2);n=len(d['seeds']);a=len(pick)
            with torch.no_grad():
                from_cached(engine,features,index);h=engine.prefix['interface_post'];mask,valid=engine.mask('interface_post','valid_mean');assert valid
                context=h.reshape(-1,h.shape[-1])[mask];candidates=torch.as_tensor(trajectories.reshape(n*a,8,3),device='cuda')
                predictions=[]
                for critic in point['critics']:
                    assert critic['heldout_fold']==held
                    model=load(critic['checkpoint']['path'],critic['checkpoint']['sha256']);predictions.append(model(context,candidates).reshape(n,a,7))
                predicted=torch.stack(predictions,1).cpu().numpy() # noise,critic,arm,metric
            output['indices'].extend([index]*n);output['seeds'].extend(d['seeds']);output['scores'].extend(scores);output['trajectory'].extend(trajectories);output['predicted'].extend(predicted)
    target=ROOT/task['stage']/'results'/(task['id']+'.npz')
    hashed=save_npz(target,global_indices=np.asarray(output['indices']),seeds=np.asarray(output['seeds']),arm_ids=np.asarray(selected_ids),
        scores=np.asarray(output['scores'],dtype=np.float64),trajectory=np.asarray(output['trajectory'],dtype=np.float32),
        predicted=np.asarray(output['predicted'],dtype=np.float32),critic_ids=np.asarray([p['id'] for p in point['critics']]))
    engine.verify_engine();meta=target.with_suffix('.json');atomic(meta,dict(status='COMPLETE',time=stamp(),task=task,path=str(target.relative_to(ROOT)),sha256=hashed,mode=point['mode'],
        rows=len(output['indices']),seconds=time.monotonic()-began,unchanged_candidate_scores_reused=True,
        predictive_features='Current interface tokens and candidate trajectory only',true_scores_not_input_to_prediction=True))
    return dict(path=str(meta.relative_to(ROOT)),matrix=str(target.relative_to(ROOT)),sha256=hashed,rows=len(output['indices']),seconds=time.monotonic()-began)
