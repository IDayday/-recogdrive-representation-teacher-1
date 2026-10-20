"""Validate locally regenerated metric caches on saved trajectories before model replay."""
from pathlib import Path
import argparse,json,hashlib,os,sys
import numpy as np
ROOT=Path(__file__).resolve().parent
def main(a):
    import portable_common as c
    os.environ['RECOGDRIVE_PORTABLE_PATHS']=str(a.paths.resolve());os.environ['RECOGDRIVE_PORTABLE_WORKDIR']=str(a.out.parent.resolve()/'runtime')
    sys.modules['common']=c;c.setup('rescore');c.compatibility();sys.path.insert(0,str(ROOT/'vendor'))
    from repair_score import score_group
    from run_teacher import read_rows
    paths=json.loads(a.paths.read_text());golden=json.loads((ROOT/'reference/golden.json').read_text());rows={r['token']:r for r in read_rows('navtest',paths)};checks=[]
    for r in golden['records']:
        row=rows[r['token']];hashed=c.sha(row['metric_cache'])
        actual=score_group(dict(metric_cache=row['metric_cache'],metric_sha256=hashed,scoring=c.read(ROOT/'configs/repair_final_baseline.json')['scoring'],records=[dict(arm=r['arm'],trajectory=r['trajectory'])]))[0]['score']
        error=max(abs(actual[k]-r['score'][k]) for k in r['score'])
        if error>a.score_atol:raise AssertionError(('Local cache changes golden scores',r['token'],error))
        checks.append(dict(token=r['token'],method=r['arm'],local_metric_sha256=hashed,original_metric_sha256=row['metric_sha256'],score_max_abs_error=error))
    receipt=dict(status='PASS',paths_sha256=c.sha(a.paths),score_atol=a.score_atol,golden_sha256=c.sha(ROOT/'reference/golden.json'),checks=checks,scope='Only saved golden trajectories checked; full population equivalence is not assumed')
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--paths',type=Path,required=True);p.add_argument('--out',type=Path,default=ROOT/'outputs/cache_calibration.json');p.add_argument('--score-atol',type=float,default=0);main(p.parse_args())
