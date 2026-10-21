"""Run unchanged controller math while preserving existing frozen marker bytes.

Only identical static marker content (apart from its top-level timestamp) may
be reused. Mutable status/heartbeat files retain normal atomic replacement.
"""
from common import *
import argparse,importlib


def main(a):
    setup('vlm_repair/resume_controller')
    import repair_queue_v2
    original=repair_queue_v2.atomic_unique
    static={'PROTOCOL.json','FITS_READY.json','PRIMARY_STAGES_APPENDED.json',
            'INFERENCE_COMPLETE.json','PRIMARY_INFERENCE_COMPLETE.json',
            'ENGINEERING_REQUEST.json','ENGINEERING_PASS.json',
            'FINAL_OPERATOR_ENGINEERING_REQUEST.json','FINAL_OPERATOR_ENGINEERING_PASS.json'}
    def preserve(path,value):
        p=Path(path).resolve()
        protected=(p.name in static or p.name.endswith('LOCK.json')
                   or ('final/fits' in str(p) and p.suffix=='.json'))
        if protected and p.exists():
            previous=read(p)
            def stable(v):return {k:x for k,x in v.items() if k!='time'} if isinstance(v,dict) else v
            assert stable(previous)==stable(value),'Existing frozen marker differs: '+str(p)
            return
        original(p,value)
    repair_queue_v2.atomic_unique=preserve;repair_queue_v2.atomic=preserve
    assert a.script in {'vlm_global_funnel_v6','vlm_final_driver','vlm_semantic_repair_v3',
        'vlm_late_repair','vlm_qneighbor_repair_v2','vlm_postcompute','vlm_analysis_finalize',
        'vlm_all_finalize','vlm_four_finalize','vlm_obs_qda_gate','vlm_obs_gate_test','vlm_five_finalize'}
    importlib.import_module(a.script).main()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--script',required=True);main(p.parse_args())
