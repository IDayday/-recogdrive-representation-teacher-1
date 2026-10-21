"""Read existing VLM timings without changing or rerunning any frozen experiment."""
from common import *
import argparse
import numpy as np
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic


def main(a):
    setup('vlm_repair/existing_timing_audit')
    source=ROOT/a.audit;proof=read(source);assert proof['status']=='PASS'
    base=ROOT/'runs/vlm_repair_20261016_v2';checks=[]
    for item in proof['checks']:
        p=base/'results'/(item['task']['id']+'.json');assert sha(p)==item['result_sha256']
        result=read(p);receipt=read(base/'receipts'/p.name);timing=result['timing']
        checks.append(dict(rank=item['rank'],task=item['task'],seconds=receipt['seconds'],
            write_seconds=receipt['write_seconds'],timing=timing,
            scene_visits=item['task']['end']-item['task']['start'],
            arms=item['task']['arm_end']-item['task']['arm_start'],records=len(result['records']),
            source_sha256=item['result_sha256']))
    keys=['read_decode_cpu_seconds','input_wait_seconds','gpu_submit_seconds',
          'device_return_wall_seconds','scoring_wait_seconds']
    summary={k:dict(median_seconds=float(np.median([r['timing'][k] for r in checks])),
        median_fraction_of_task_wall=float(np.median([r['timing'][k]/r['seconds'] for r in checks]))) for k in keys}
    summary['write_seconds']=dict(median_seconds=float(np.median([r['write_seconds'] for r in checks])),
        median_fraction_of_task_wall=float(np.median([r['write_seconds']/r['seconds'] for r in checks])))
    out=VOUT/'performance'/('existing_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
    atomic(out,dict(status='PASS',time=stamp(),source_audit=str(source.relative_to(ROOT)),source_audit_sha256=sha(source),
        tasks=checks,summary=summary,code_sha256=sha(Path(__file__)),no_experiment_rerun=True,
        interpretation='Read/decode CPU time overlaps inference and is not additive wall time. GPU submission and device return are host wall measurements; return includes pending device work, not pure copy time. Scoring wait is exposed stall after overlap, not total scorer CPU time. The mixed task sample is not a matched-work optimization A/B or a unique-scene throughput benchmark.'))
    print(json.dumps(dict(status='PASS',path=str(out.relative_to(ROOT)),tasks=len(checks),summary=summary)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--audit',required=True);main(p.parse_args())
