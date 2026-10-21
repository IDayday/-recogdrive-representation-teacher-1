from r2_common import *
from r2_resume_support import append_once
while not (ROOT/"config/SPATIAL_DISCOVERY_WAVE1.json").exists():time.sleep(15)
append_once("cpu",[dict(id="outcome_prepare_spatial_uncentered_wave_v1",handler="code/r2_spatial_uncentered_prepare.py",handler_sha256=sha(ROOT/"code/r2_spatial_uncentered_prepare.py"))])
