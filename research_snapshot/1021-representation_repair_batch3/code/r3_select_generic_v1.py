"""Three endpoints; every tie-break also respects its allowed noise indices."""


def select(records,order):
    import numpy as np
    assert order[0]=='Base' and len(order)==len(set(order))
    lookup={(r['arm'],r['seed_index']):r for r in records}
    assert len(lookup)==len(records)==len(order)*5
    q=np.asarray([[lookup[(ident,j)]['score']['score'] for j in range(5)] for ident in order],dtype=np.float64)
    edit=np.asarray([[lookup[(ident,j)]['relative_edit'] for j in range(5)] for ident in order],dtype=np.float64)
    assert np.isfinite(q).all() and np.isfinite(edit).all() and (edit>=0).all()
    def best(score,amount):
        tied=np.flatnonzero(score==score.max())
        return int(min(tied,key=lambda i:(order[i]!='Base',float(amount[i]),order[i])))
    c1=[best(q[:,j],edit[:,j]) for j in range(5)];c2=best(q.mean(1),edit.mean(1));c3=best(q[:,:3].mean(1),edit[:,:3].mean(1))
    return dict(R1=[dict(arm=order[c],seed_index=j) for j,c in enumerate(c1)],R2=[dict(arm=order[c2],seed_index=j) for j in range(5)],
                R3=[dict(arm=order[c3],seed_index=j) for j in [3,4]],R3_selection_seeds=[0,1,2],R3_evaluation_seeds=[3,4],R3_negative_evaluation_retained=True)
