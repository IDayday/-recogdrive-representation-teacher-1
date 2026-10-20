"""Small actual model/score acceptance against frozen trajectories."""
from pathlib import Path
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parent
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--paths',type=Path,required=True);p.add_argument('--out',type=Path,default=ROOT/'outputs/golden');p.add_argument('--noise-bank',type=Path);a=p.parse_args()
    g=json.loads((ROOT/'reference/golden.json').read_text());tokens=sorted({r['token'] for r in g['records']});methods=sorted({r['arm'] for r in g['records'] if r['arm']!='baseline'})
    cmd=[sys.executable,'-B',str(ROOT/'run_teacher.py'),'--paths',str(a.paths.resolve()),'--out',str(a.out),'--cohort','navtest','--subset','all','--mode','historical','--allow-navtest','--seeds','0','--tokens',','.join(tokens),'--methods',','.join(methods)]
    if a.noise_bank:cmd+=['--noise-bank',str(a.noise_bank)]
    subprocess.run(cmd,check=True)
    subprocess.run([sys.executable,'-B',str(ROOT/'check_golden.py'),'--input',str(a.out)],check=True)
