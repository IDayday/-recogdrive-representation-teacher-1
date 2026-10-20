"""Recompute the historical +2.1519 bound from local saved/generated score arrays."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
from selector import choose,summarize

ROOT=Path(__file__).resolve().parent
def run(scores,out,check_expected=True):
    catalog=json.loads((ROOT/'configs/methods.json').read_text())
    expected=json.loads((ROOT/'reference/expected.json').read_text())
    a=np.load(scores,mmap_mode='r',allow_pickle=False)
    if a.shape!=(5,12146,len(catalog)+1,7):raise ValueError(f'Unexpected score shape {a.shape}')
    index,selected=choose(a);result=summarize(selected,a[:,:,0,:])
    if check_expected:
        for k in ['base_pdms','selected_pdms','delta_pdms']:
            if abs(result[k]-expected[k])>1e-9:raise AssertionError((k,result[k],expected[k]))
        for k in ['outputs','failure_outputs','changed_outputs','improved_outputs','worsened_outputs','repaired_to70','repaired_above90','high_to_failure','collision_new','offroad_new','delta_failure_count','delta_zero_count']:
            if result[k]!=expected[k]:raise AssertionError((k,result[k],expected[k]))
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out/'case_fixed_selection.npz',method_index=index,selected_scores=selected)
    result.update(status='PASS',mode='historical_failure_only',reference_checked=check_expected,
                  score_sha256=hashlib.sha256(Path(scores).read_bytes()).hexdigest())
    (out/'SUMMARY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2));return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--scores',type=Path,required=True);p.add_argument('--out',type=Path,default=ROOT/'outputs/oracle');p.add_argument('--allow-hardware-drift',action='store_true');a=p.parse_args();run(a.scores,a.out,not a.allow_hardware_drift)
