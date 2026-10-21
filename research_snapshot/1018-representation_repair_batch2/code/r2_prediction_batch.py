"""Share immutable inputs across critic checkpoints, project exact result columns.

Every original task is atomically claimed once. Existing candidate trajectories
and scores are unchanged; original predictor executes each frozen critic as usual.
"""
from r2_common import *


def run(engine,task,pool):
    import numpy as np
    from r2_expert_space import save_npz
    active=[];began=time.monotonic();worker=socket.gethostname()+'_'+str(os.getpid())
    for entry in task['entries']:
        base=ROOT/entry['stage'];t=entry['task'];assert sha(ROOT/entry['handler'])==entry['handler_sha256']
        if (base/'receipts'/(t['id']+'.json')).exists():continue
        claim=base/'claims'/t['id'];claim.parent.mkdir(parents=True,exist_ok=True)
        try:claim.mkdir()
        except FileExistsError:continue
        atomic(claim/'OWNER.json',dict(time=stamp(),worker=worker,pid=os.getpid(),hostname=socket.gethostname(),prediction_batch=task['id']));point=read(ROOT/t['point']);assert len(point['critics'])==1
        active.append((entry,point))
    if not active:return dict(status='ALREADY_ACCOUNTED_FOR',original_tasks=0)
    first=active[0][1];e0=active[0][0];t0=e0['task'];items=first['items'][t0['start']:t0['end']];critics=[]
    for entry,point in active:
        t=entry['task'];assert point['items'][t['start']:t['end']]==items and digest(point['parts'])==digest(first['parts']) and point['responses']==first['responses'] and point['mode']==first['mode'] and point['heldout_fold']==first['heldout_fold'];assert entry['handler']==e0['handler'];critics.extend(point['critics'])
    view={c.get('context_view','post_valid') for c in critics};assert len(view)==1
    base=ROOT/task['stage'];point_path=base/'points'/(task['id']+'.json');point=dict(first,id=task['id'],items=items,critics=critics);atomic(point_path,point)
    if e0['handler']=='code/r2_state_condition_predict.py':from r2_state_condition_predict import run as predict
    else:
        assert e0['handler']=='code/r2_context_predict.py'
        from r2_context_predict import run as predict
    result=predict(engine,dict(id=task['id']+'_physical',stage=task['stage'],point=str(point_path.relative_to(ROOT)),start=0,end=len(items)),pool);meta=read(ROOT/result['path'])
    assert sha(ROOT/meta['path'])==meta['sha256']
    with np.load(ROOT/meta['path']) as z:data={k:np.array(z[k]) for k in z.files}
    assert data['predicted'].shape[1]==len(active);projected=[]
    for j,(entry,point) in enumerate(active):
        t=entry['task'];destination=ROOT/entry['stage']/'results'/(t['id']+'.npz');arrays=dict(data,predicted=data['predicted'][:,j:j+1],critic_ids=data['critic_ids'][j:j+1]);hashed=save_npz(destination,**arrays)
        projected_meta=dict(meta,time=stamp(),task=t,path=str(destination.relative_to(ROOT)),sha256=hashed,seconds=0.,prediction_columns_projected_exactly=True,physical_batch_source=result['path'],physical_batch_matrix_sha256=meta['sha256'],physical_batch_seconds=meta['seconds'],original_predictor=entry['handler'],original_predictor_sha256=entry['handler_sha256'])
        atomic(destination.with_suffix('.json'),projected_meta);out=dict(path=str(destination.with_suffix('.json').relative_to(ROOT)),matrix=str(destination.relative_to(ROOT)),sha256=hashed,rows=meta['rows'],seconds=0.,physical_batch_source=result['path'])
        atomic(ROOT/entry['stage']/'receipts'/(t['id']+'.json'),dict(status='COMPLETE',time=stamp(),task=t,worker=worker,seconds=0.,result=out,prediction_batch=task['id'],compute_mode='exact_prediction_column_projection'))
        projected.append(dict(stage=entry['stage'],id=t['id'],matrix_sha256=hashed))
    engine.verify_engine();return dict(original_tasks=len(projected),physical_prediction=result,projections=projected,seconds=time.monotonic()-began,one_shared_input_read_per_scene=True)
