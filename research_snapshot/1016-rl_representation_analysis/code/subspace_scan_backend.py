"""Engineering-only numerical/throughput probe; run after accepted repair report."""
from common import *
import numpy as np
from threadpoolctl import threadpool_limits
from subspace_scan_cv import mul

def main():
    setup('subspace_scan/backend')
    assert (ROOT/'provenance/REPAIR_REPORT_ACCEPTANCE.json').exists()
    rng=np.random.default_rng(20261016);x=rng.standard_normal((16000,384));w=rng.standard_normal((384,673));center=x.mean(0);trials=[];reference=None
    for threads in [2,4,8]:
        with threadpool_limits(limits=threads):
            seconds=[]
            for i in range(3):
                began=time.monotonic();value=mul(x,w,center,'cpu_float64');seconds.append(time.monotonic()-began)
            if reference is None:reference=value
            diff=float(np.max(np.abs(value-reference)));assert diff<1e-9
            trials.append(dict(backend='cpu_float64',threads=threads,seconds=seconds,median=float(np.median(seconds)),max_diff=diff))
    cpu=min(trials,key=lambda r:r['median']);selected=cpu;device_error=None
    try:
        import torch
        seconds=[]
        for i in range(4):
            torch.cuda.synchronize();began=time.monotonic();value=mul(x,w,center,'device_float64');torch.cuda.synchronize()
            if i:seconds.append(time.monotonic()-began)
        diff=float(np.max(np.abs(value-reference)));assert diff<1e-9
        device=dict(backend='device_float64',threads=cpu['threads'],seconds=seconds,median=float(np.median(seconds)),max_diff=diff);trials.append(device)
        if device['median']<=cpu['median']*.8:selected=device
    except Exception as error:device_error=type(error).__name__
    proof=dict(status='PASS',time=stamp(),selected_backend=selected['backend'],cpu_threads_per_worker=cpu['threads'],trials=trials,device_error=device_error,
        selection='Use device only if float64 agreement<1e-9 and >=20% faster including transfer; 16 independent workers per node',model_loaded=False)
    atomic(ROOT/'provenance/SUBSPACE_BACKEND_SMOKE.json',proof);print(json.dumps(proof),flush=True)

if __name__=='__main__':main()
