"""Audit the same locked edits across independent queue stages, without selection."""
from common import *
import numpy as np
from candidate_repair_fit import OUT
from candidate_repair_followup import summarized

def main():
    setup('candidate_repair/repeatability')
    base=ROOT/'runs/candidate_repair_20261016_v1'
    target=read(base/'stages/navtrain_full_locked/PROTOCOL.json')['tasks']
    while sum(1 for _ in (base/'receipts').glob('navtrain_full_locked_s*.json'))<target:
        failures=list((base/'failures').glob('*.json'))
        if failures:raise RuntimeError(str(failures[0]))
        time.sleep(30)
    summarized('navtrain_full_locked')
    fullpath=OUT/'analysis/navtrain_full_locked';full=np.load(fullpath/'scores.npy',mmap_mode='r')
    positions={r['token']:i for i,r in enumerate(read(fullpath/'rows.json'))}
    full_ids={a['id']:i+1 for i,a in enumerate(read(fullpath/'arms.json'))}
    source={};checks=[];hashes={str((fullpath/'scores.npy').relative_to(ROOT)):sha(fullpath/'scores.npy')}
    for name in ['validation','validation_temporal','validation_combinations','validation_controls']:
        directory=OUT/'analysis'/name;data=np.load(directory/'scores.npy',mmap_mode='r')
        rows=read(directory/'rows.json');indices=[positions[r['token']] for r in rows]
        assert np.array_equal(full[:,indices,0],data[:,:,0]),name
        hashes[str((directory/'scores.npy').relative_to(ROOT))]=sha(directory/'scores.npy')
        for i,a in enumerate(read(directory/'arms.json'),1):
            arm=a['id'];values=np.asarray(data[:,:,i])
            if arm in full_ids:
                assert np.array_equal(full[:,indices,full_ids[arm]],values),arm
                checks.append(dict(arm=arm,reference=name,comparison='locked full-training subset',seeds=3,cases=len(rows),components=7,maximum_difference=0))
            if arm in source:
                previous,previous_rows,previous_data=source[arm]
                assert rows==previous_rows and np.array_equal(previous_data,values),arm
                checks.append(dict(arm=arm,reference=previous,comparison=name,seeds=3,cases=len(rows),components=7,maximum_difference=0))
            else:source[arm]=(name,rows,values.copy())
    assert set(full_ids).issubset({r['arm'] for r in checks})
    p=OUT/'CROSS_STAGE_REPEATABILITY.json';assert not p.exists()
    result=dict(status='PASS',time=stamp(),source_sha256=hashes,checks=checks,locked_candidates=len(full_ids),selection_changed=False)
    atomic(p,result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
