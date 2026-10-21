"""Wait for all prespecified full development results and lock before any test access."""
from common import *
import subprocess
from repair_select_final import STAGES

def main():
    setup('repair/lock_wait')
    targets=[ROOT/'repair_v1/analysis'/s/'DETAILS.json' for s in STAGES+['postprocess_validation']]
    while not all(p.exists() for p in targets):
        print(json.dumps(dict(status='WAIT_DEVELOPMENT',missing=[p.parent.name for p in targets if not p.exists()],time=stamp())),flush=True);time.sleep(60)
    subprocess.run([sys.executable,'-B',str(ROOT/'code/repair_select_final.py')],check=True,cwd=ROOT)

if __name__=='__main__':main()
