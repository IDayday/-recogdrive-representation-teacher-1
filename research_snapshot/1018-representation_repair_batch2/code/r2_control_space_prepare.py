"""Fold-local quality/random control bases; existing cached observations only."""
from r2_common import *


def run(task):
    import numpy as np
    from scipy.linalg import svd
    from r2_expert_space import success_geometry,save_npz
    cells=read(ROOT/'manifests/cells.json');source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality']);held=task['heldout_fold'];group_path=ROOT/task['responsibility_meta'];group=read(group_path)
    assert sha(ROOT/group['path'])==group['sha256']
    with np.load(ROOT/group['path']) as z:indices=np.array(z['global_indices']);responsibility=np.array(z['responsibility'])
    assert all(rows[int(i)]['subset']=='exploration' and int(digest(dict(session=rows[int(i)]['session'],cv_root=20261016))[:8],16)%5!=held for i in indices)
    output=[]
    for block in ['interface_pre','interface_post']:
        cell=next(c for c in cells if c['block']==block and c['group']=='valid_mean');geometry=success_geometry(cell,held);assert sha(ROOT/geometry['path'])==geometry['sha256']
        x=np.load(cell['absolute_path'],mmap_mode='r');D=x.shape[1]
        with np.load(ROOT/geometry['path']) as z:success={k:np.array(z[k]) for k in ['common_center','centered_basis','uncentered_basis']}
        for centered in [False,True]:
            center=success['common_center'] if centered else np.zeros(D);us=success[('centered' if centered else 'uncentered')+'_basis'][:,:128]
            for expert in [-1,0,1]:
                weights=np.ones(len(indices)) if expert<0 else responsibility[:,expert];use=weights>0;xx=np.asarray(x[indices[use]],dtype=np.float64);ww=weights[use].astype(np.float64);ww/=ww.sum();weighted=(xx-center)*np.sqrt(ww[:,None]);_,s,vt=svd(weighted,full_matrices=False,check_finite=False)
                rank=int(np.sum(s>max(float(s[0])*1e-5,1e-10)));kf=min(128,rank);uf=vt[:kf].T;residual=uf-us@(us.T@uf);u,sing,_=svd(residual,full_matrices=False,check_finite=False);effective=int(np.sum(sing>max(float(sing[0])*1e-5,1e-10)));basis=u[:,:min(128,effective)]
                spec=dict(block=block,heldout_fold=held,centered=centered,expert=expert,ks=us.shape[1],kf=kf,kind='global_quality_residual' if expert<0 else 'own_group_quality_residual');ident='control_basis_'+digest(spec)[:24];path=ROOT/'control_space_bases'/(ident+'.npz');hashed=save_npz(path,basis=basis.astype(np.float32))
                meta=dict(id=ident,path=str(path.relative_to(ROOT)),sha256=hashed,dimension=D,rank=basis.shape[1],config=spec,source_cell_sha256=cell['sha256'],success_geometry=geometry,responsibility_meta=task['responsibility_meta'],responsibility_sha256=sha(group_path),heldout_fold=held,only_training_fold=True);atomic(path.with_suffix('.json'),meta);output.append(meta)
        for replicate in [0,1]:
            rng=np.random.default_rng(int(digest(dict(random_control_basis=20261018,held=held,block=block,replicate=replicate))[:16],16));basis=np.linalg.qr(rng.standard_normal((D,min(128,D))),mode='reduced')[0];spec=dict(block=block,heldout_fold=held,kind='Haar_random',replicate=replicate);ident='control_basis_'+digest(spec)[:24];path=ROOT/'control_space_bases'/(ident+'.npz');hashed=save_npz(path,basis=basis.astype(np.float32));meta=dict(id=ident,path=str(path.relative_to(ROOT)),sha256=hashed,dimension=D,rank=basis.shape[1],config=spec,heldout_fold=held,only_training_fold=True);atomic(path.with_suffix('.json'),meta);output.append(meta)
    path=ROOT/'analysis/control_space_preparation'/task['id'];atomic(path.with_suffix('.json'),dict(status='COMPLETE',time=stamp(),task=task,bases=output,matched_control_basis_definition='ks=kf128 before effective-rank clipping; take nested residual ranks8/32/128. Random sameD/r, two independent Haar bases. Full is shared-channel allD, not independent token-by-channel edits.',no_new_model_collection=True,validation_accessed=False,test_accessed=False));return dict(path=str(path.with_suffix('.json').relative_to(ROOT)),bases=len(output))
