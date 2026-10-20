"""Explicit local asset paths; no cloud SDK or download dependency."""
from pathlib import Path
import argparse,json,hashlib,importlib.metadata
ROOT=Path(__file__).resolve().parent
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def check(paths,full=True):
    local=json.loads(Path(paths).read_text());expected=json.loads((ROOT/'configs/repair_final_baseline.json').read_text());checks=[]
    for key in ['checkpoint','vlm']:
        if not Path(local[key]).exists():raise FileNotFoundError(local[key])
    if full:
        if sha(local['checkpoint'])!=expected['checkpoint_sha256']:raise AssertionError('RL checkpoint SHA mismatch')
    for name,hashed in expected['vlm_sha256'].items():
        p=Path(local['vlm'])/name
        if name in ['all_results.json','train_results.json','trainer_state.json'] and not p.exists():continue
        if not p.exists():raise FileNotFoundError(p)
        if full or p.stat().st_size<10_000_000:
            if sha(p)!=hashed:raise AssertionError(('VLM file mismatch',name))
    for p in (ROOT/'configs/methods.json',ROOT/'reference/golden.json'):
        if not p.exists():raise FileNotFoundError(p)
    for a in json.loads((ROOT/'configs/methods.json').read_text()):
        if sha(ROOT/a['fit_path'])!=a['fit_sha256']:raise AssertionError(a['id'])
        if 'observation_gate' in a:
            f=a['observation_gate']['fit']
            if sha(ROOT/f['path'])!=f['sha256']:raise AssertionError('Observation gate fit mismatch')
    versions={}
    expected_versions=json.loads((ROOT/'reference/environment.json').read_text())
    for package in expected_versions:
        try:versions[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:versions[package]='MISSING'
    result=dict(status='PASS',large_weight_hashes_checked=full,versions=versions,expected_versions=expected_versions,version_mismatches=[k for k in versions if versions[k]!=expected_versions[k]])
    print(json.dumps(result,ensure_ascii=False,indent=2));return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--paths',type=Path,required=True);p.add_argument('--fast',action='store_true');a=p.parse_args();check(a.paths,not a.fast)
