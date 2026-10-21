"""Fold-contained input centers for learned full-space experts, independent of K."""
from r2_common import *


def run(task):
    import numpy as np
    from r2_expert_space import save_npz
    source=read(ROOT/'manifests/data_source.json');rows=read(source['rows']);q=np.load(source['quality'])
    explore=np.array([r['subset']=='exploration' for r in rows])
    fold=np.array([int(digest(dict(session=r['session'],cv_root=20261016))[:8],16)%5 for r in rows])
    cells={c['cell']:c for c in read(ROOT/'manifests/cells.json')};references=[]
    for held in [-1,0,1,2,3,4]:
        selected=np.flatnonzero(explore&((fold!=held) if held>=0 else True)&((q<.7)|(q>.9)))
        for block in ['interface_pre','interface_post']:
            cell=cells[block+'__valid_mean'];x=np.load(cell['absolute_path'],mmap_mode='r');total=np.zeros(x.shape[1],dtype=np.float64)
            for start in range(0,len(selected),4096):total+=np.asarray(x[selected[start:start+4096]],dtype=np.float64).sum(0)
            center=(total/len(selected)).astype('float32')
            path=ROOT/'fullspace_references'/('all' if held<0 else f'fold{held}')/(block+'.npz')
            hashed=save_npz(path,basis=np.eye(len(center),dtype=np.float32),center=center,scale=np.ones(len(center),dtype=np.float32))
            record=dict(status='PASS',time=stamp(),path=str(path.relative_to(ROOT)),sha256=hashed,heldout_fold=held,
                        block=block,group='valid_mean',r=len(center),config=dict(kind='full_space_reference',r=len(center)),
                        training_cases=len(selected),center='Pooled high-quality and failure training cases, excluding held fold',
                        source_sha256=cell['sha256'],quality_subspace_selected=False)
            atomic(path.with_suffix('.json'),record);references.append(record)
    path=ROOT/'fullspace_references/COMPLETE.json';atomic(path,dict(status='PASS',time=stamp(),references=references,validation_fitted=False,test_accessed=False))
    return dict(path=str(path.relative_to(ROOT)),references=len(references))
