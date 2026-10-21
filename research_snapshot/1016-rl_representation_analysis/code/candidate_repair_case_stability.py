"""Descriptive case-level consistency across the five already-locked inference samples."""
from common import *
import numpy as np
from candidate_repair_fit import OUT

def analyze():
    folder=OUT/'analysis/final_test';path=folder/'CASE_STABILITY.json';matrix_path=folder/'scores.npy';source_sha=sha(matrix_path)
    if path.exists():
        previous=read(path);assert previous['scores_sha256']==source_sha;return previous
    scores=np.load(matrix_path,mmap_mode='r');arms=read(folder/'arms.json');base=scores[:,:,0,0]
    assert base.shape==(5,12146)
    fail=(base<.7).all(0);high=(base>.9).all(0);records=[]
    for i,a in enumerate(arms,1):
        after=scores[:,:,i,0];f=after[:,fail];h=after[:,high]
        records.append(dict(arm=a['id'],stable_failure_cases=int(fail.sum()),stable_high_cases=int(high.sum()),
            stable_failure_any_ge70=int((f>=.7).any(0).sum()),stable_failure_all_ge70=int((f>=.7).all(0).sum()),
            stable_failure_any_gt90=int((f>.9).any(0).sum()),stable_failure_all_gt90=int((f>.9).all(0).sum()),
            stable_high_any_failure=int((h<.7).any(0).sum()),stable_high_all_failure=int((h<.7).all(0).sum()),
            stable_high_failure_outputs=int((h<.7).sum())))
    result=dict(status='PASS',time=stamp(),scores_sha256=source_sha,seeds=5,cases=12146,stable_failure_cases=int(fail.sum()),stable_high_cases=int(high.sum()),
        other_cases=int((~(fail|high)).sum()),records=records,inference='descriptive only; five seeds belong to the same case, not independent cases')
    atomic(path,result);return result

if __name__=='__main__':
    setup('candidate_repair/case_stability');print(json.dumps({k:v for k,v in analyze().items() if k!='records'}),flush=True)
