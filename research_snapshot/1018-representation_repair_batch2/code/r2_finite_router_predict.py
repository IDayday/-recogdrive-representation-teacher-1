"""Observable gate first; actual frozen candidate outcome lookup afterwards."""
from r2_common import *
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache


@lru_cache(maxsize=16)
def edit_records(path):
    return {(r['token'],r['arm'][len('candidate_'):],r['seed_index']):r['relative_edit'] for r in read(path)['records'] if r['arm'].startswith('candidate_')}


def run(engine,task,pool):
    import numpy as np
    import torch
    from worker import load_features
    from r2_cached_interfaces import from_cached
    from r2_behavior_router import checkpoint,current_feature
    from r2_point_response import FIELDS
    descriptor=read(ROOT/task['point']);bank=read(ROOT/descriptor['bank']);source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);held=descriptor['heldout_fold']
    with np.load(ROOT/bank['matrix']) as z:ii=np.array(z['global_indices']);ids=list(z['arm_ids']);seeds=np.array(z['seeds']);scores=np.array(z['scores']);trajectory=np.array(z['trajectory'])
    assert seeds.tolist()==[0,1,2];positions={int(i):j for j,i in enumerate(ii)};panel=descriptor['panel'][task['start']:task['end']];records=[];began=time.monotonic()
    def fetch(index):
        j=positions[index];chunk=Path(bank['point']).parent.parent/'results'/(read(ROOT/bank['point'])['id']+'_%04d.json'%((j//4)*4))
        return load_features(rows[index],engine.cfg)[0],edit_records(str(ROOT/chunk))
    with ThreadPoolExecutor(max_workers=1) as reader:
        future=reader.submit(fetch,panel[0]) if panel else None
        for k,index in enumerate(panel):
            features,edits=future.result()
            if k+1<len(panel):future=reader.submit(fetch,panel[k+1])
            row=rows[index];assert row['subset']=='exploration';fold=int(digest(dict(session=row['session'],cv_root=20261016))[:8],16)%5
            assert held==fold if bank['mode']=='heldout' else held<0 or held!=fold
            j=positions[index];observed={};choices=[]
            with torch.no_grad():
                from_cached(engine,features,index)
                for n,noise in enumerate(seeds):
                    records.append(dict(token=row['token'],session=row['session'],arm='baseline',seed_index=int(noise),trajectory=trajectory[j,0,n].tolist(),score={f:float(v) for f,v in zip(FIELDS,scores[j,0,n])}))
                for policy in descriptor['policies']:
                    model=policy['model'];assert model['heldout_fold']==held and model['tier'] in ['observation','trajectory'];module=checkpoint(policy['checkpoint']['path'],policy['checkpoint']['sha256'],model['input_dimension'],len(model['parts']))
                    for n,noise in enumerate(seeds):
                        key=(model['tier'],int(noise))
                        if key not in observed:observed[key]=current_feature(engine,torch.as_tensor(trajectory[j,0,n],device='cuda'),None,held,model['tier'])
                        logits,amount=module(observed[key]);assert torch.equal(amount,torch.ones_like(amount));choice=int(logits.argmax())
                        if policy.get('force_Base',False):assert descriptor['mode']=='engineering';choice=0
                        if 'force_choice' in policy:assert descriptor['mode']=='engineering';choice=int(policy['force_choice']);assert 0<=choice<=len(model['parts'])
                        choices.append((policy,choice,int(noise),n))
            # Actual labels are used only after all choices for this scene.
            for policy,choice,noise,n in choices:
                arm=0 if choice==0 else ids.index(policy['model']['parts'][choice-1]['id'])
                relative=0. if choice==0 else edits[(row['token'],policy['model']['parts'][choice-1]['id'],noise)]
                records.append(dict(token=row['token'],session=row['session'],arm=policy['id'],seed_index=noise,choice=choice,trajectory=trajectory[j,arm,n].tolist(),score={f:float(v) for f,v in zip(FIELDS,scores[j,arm,n])},relative_edit=relative))
    engine.verify_engine();path=ROOT/task['stage']/'results'/(task['id']+'.json')
    atomic(path,dict(status='COMPLETE',time=stamp(),task=task,mode=descriptor['mode'],records=records,seconds=time.monotonic()-began,
        only_existing_exact_candidate_outcomes_reused=True,no_actual_score_or_GT_in_decision=True,source_bank=descriptor['bank'],source_matrix_sha256=bank['matrix_sha256']))
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),records=len(records),seconds=time.monotonic()-began)
