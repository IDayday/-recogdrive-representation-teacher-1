"""Descriptive matched dimension changes over the complete CV ledger, never held-out selection."""
from common import *
import numpy as np
from subspace_scan_prepare import OUT
from subspace_scan_math import KS,RS

def main():
    setup('subspace_scan/dimension_effects');index=read(OUT/'CELL_INDEX.json');ledger=np.load(OUT/'CV_SEARCH_LEDGER.npy',mmap_mode='r');n=len(index)
    assert len(ledger)==n*2*673
    shaped=ledger.reshape(n,2,673)
    assert np.array_equal(shaped['config'],np.broadcast_to(np.arange(673),(n,2,673)))
    assert np.array_equal(shaped['cell'][:,:,0],np.broadcast_to(np.arange(n)[:,None],(n,2)))
    fields={k:np.array(shaped[k][:,:,:648]).reshape(n,2,9,9,8) for k in ['valid','degenerate','auc_P0','ap_P0','gap_P0','auc_P1']};records=[]
    for route in ['r1','r2']:
        case=np.array([r['task']['route']==route for r in index])
        for center_i,center in enumerate(['uncentered','pooled_centered']):
            val={k:v[case,center_i] for k,v in fields.items()};good=(val['valid']==1)&(val['degenerate']==0)&np.isfinite(val['auc_P0'])
            for axis,settings in [('ks',KS),('kf',KS),('r',RS),('equal_main',KS)]:
                for j in range(len(settings)-1):
                    def select(x,at):
                        if axis=='ks':return x[:,at,:,:]
                        if axis=='kf':return x[:,:,at,:]
                        if axis=='r':return x[:,:,:,at]
                        return x[:,at,at,:]
                    mask=select(good,j)&select(good,j+1);row=dict(route=route,centering=center,axis=axis,start=settings[j],end=settings[j+1],matched_valid_combinations=int(mask.sum()))
                    for field,label in [('auc_P0','auc_P0'),('ap_P0','ap_P0'),('gap_P0','gap_P0'),('auc_P1','auc_P1')]:
                        before=select(val[field],j);after=select(val[field],j+1);use=mask&np.isfinite(before)&np.isfinite(after);delta=(after-before)[use]
                        row[label]=dict(n=len(delta),median=float(np.median(delta)) if len(delta) else None,mean=float(delta.mean()) if len(delta) else None,improved_fraction=float(np.mean(delta>1e-6)) if len(delta) else None,quantiles=np.quantile(delta,[.1,.25,.75,.9]).tolist() if len(delta) else None)
                    records.append(row)
    atomic(OUT/'DIMENSION_EFFECTS.json',dict(status='COMPLETE',time=stamp(),records=records,ledger_sha256=sha(OUT/'CV_SEARCH_LEDGER.npy'),code_sha256=sha(Path(__file__)),
        interpretation='descriptive matched configuration differences; each comparison fixes cell, center and remaining dimensions; repeated settings are not independent scenes; no hypothesis test or new selection'))
    print(json.dumps(dict(status='COMPLETE',rows=len(records))),flush=True)

if __name__=='__main__':main()
