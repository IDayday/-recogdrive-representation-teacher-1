"""First current-task test access is gated on the immutable selection lock."""
from common import *
import csv

def main():
    setup('repair/test_manifest_inspection');lock=ROOT/'repair_v1/TEST_LOCK.json'
    while not lock.exists():time.sleep(30)
    assert read(lock)['status']=='LOCKED_BEFORE_TEST_ACCESS'
    rows=[]
    for relative in ['1010-il_baseline/manifests/cases.csv','1010-il_baseline/manifests/input_features.csv']:
        path=ROOT.parent/relative
        with path.open() as f:
            reader=csv.DictReader(f);first=[next(reader) for _ in range(2)]
            rows.append(dict(path=str(path),fields=reader.fieldnames,first=first,manifest_sha256=sha(path)))
    proof=dict(status='PASS',time=stamp(),lock_sha256=sha(lock),first_current_test_access_after_lock=True,manifests=rows)
    atomic(ROOT/'provenance/NAVTEST_MANIFEST_INSPECTION.json',proof)
    print(json.dumps(proof,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
