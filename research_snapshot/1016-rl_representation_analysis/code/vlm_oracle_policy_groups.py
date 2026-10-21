"""Separate representation-operator bounds from simple trajectory scaling."""
from common import *
import numpy as np
from vlm_core import VOUT
from vlm_oracle_all import sources
from repair_oracle_inventory_v2 import category
from repair_oracle_extended import detail
from repair_queue_v2 import atomic_unique as atomic

def family(source,arm):
    if arm['method']=='trajectory_scale':return 'trajectory_scaling'
    return 'upstream_representation' if source['id'].startswith('vlm_repair_v1__') else 'action_head_representation'

def main():
    setup('vlm_repair/oracle_policy_groups');groups={}
    for s in sources():
        if len(s['rows']) not in [12146,17475,103288] or len(s['seeds'])<3:continue
        a=np.load(s['path'],mmap_mode='r');base=np.asarray(a[:,:,0,:]);key=digest(dict(tokens=[r['token'] for r in s['rows']],seeds=s['seeds'],baseline_sha=hashlib.sha256(base.tobytes()).hexdigest()))
        groups.setdefault(key,[]).append(s)
    out=[]
    for key,ss in groups.items():
        rows=ss[0]['rows'];base=np.asarray(np.load(ss[0]['path'],mmap_mode='r')[:,:,0,:]);failed=base[:,:,0]<.7
        candidates={name:dict(best=base.copy(),case_fixed=base.copy(),case_fixed_failure=base.copy(),case_fixed_failure_benefit=base.copy(),stable_single_method=np.zeros(len(rows),dtype=bool),methods=[]) for name in ['action_head_representation','trajectory_scaling','upstream_representation','all_representation','all_genuine']}
        for source in ss:
            x=np.load(source['path'],mmap_mode='r');assert np.array_equal(x[:,:,0,:],base)
            for i,arm in enumerate(source['arms'],1):
                if category(arm)!='repair':continue
                label=family(source,arm);value=np.asarray(x[:,:,i,:]);names=[label,'all_genuine']+(['all_representation'] if label!='trajectory_scaling' else [])
                for name in names:
                    slot=candidates[name];use=value[:,:,0]>slot['best'][:,:,0];slot['best'][use]=value[use];slot['methods'].append(dict(id=arm['id'],panel=source['id']))
                    for field,proposal in [('case_fixed',value),('case_fixed_failure',np.where(failed[:,:,None],value,base)),('case_fixed_failure_benefit',np.where((failed&(value[:,:,0]>base[:,:,0]))[:,:,None],value,base))]:
                        choose=proposal[:,:,0].mean(0)>slot[field][:,:,0].mean(0);slot[field][:,choose,:]=proposal[:,choose,:]
                    slot['stable_single_method']|=failed.all(0)&(value[:,:,0]>.9).all(0)
        result={}
        for name,slot in candidates.items():
            if not slot['methods']:continue
            result[name]=dict(methods=slot['methods'],all_case=detail(slot['best'],base,rows,ci=True),failure_only=detail(np.where(failed[:,:,None],slot['best'],base),base,rows,ci=True),
                case_fixed_method_all_case=detail(slot['case_fixed'],base,rows,ci=True),case_fixed_method_failure_only=detail(slot['case_fixed_failure'],base,rows,ci=True),case_fixed_method_failure_and_benefit=detail(slot['case_fixed_failure_benefit'],base,rows,ci=True),
                stable_failure_cases_with_at_least_one_single_method_above90_all_seeds=int(slot['stable_single_method'].sum()),
                selection_unit='Main bound may choose different methods per noise draw; case-fixed bounds choose one actual method per scene across all draws. Single-method stable repair is an existence test, not necessarily the maximum-mean selector.')
        out.append(dict(id=key,cases=len(rows),seeds=ss[0]['seeds'],panels=[s['id'] for s in ss],groups=result,base_failed_outputs=int(failed.sum()),baseline_mean_pdms=float(base[:,:,0].mean()*100)))
    dest=VOUT/'oracle_policy_groups'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')
    atomic(dest/'SUMMARY.json',dict(status='PASS',time=stamp(),compatible_pools=out,code_sha256=sha(Path(__file__)),interpretation='Oracle bounds on actually computed methods only; no assumed removal of internal gates and no uncomputed successful-case outputs. The representation-only pool excludes trajectory scaling, nulls and GT patches. Per-draw method choice is a stronger bound than one method fixed per scene.'))
    atomic(VOUT/'ORACLE_POLICY_GROUPS_LATEST.json',dict(path=str((dest/'SUMMARY.json').relative_to(ROOT))))
    print('ORACLE_POLICY_GROUPS_PASS',len(out),str(dest.relative_to(ROOT)),flush=True)

if __name__=='__main__':main()
