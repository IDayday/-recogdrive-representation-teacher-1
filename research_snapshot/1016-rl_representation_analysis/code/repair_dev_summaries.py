"""Compute prespecified statistics as complete development stages arrive; no adaptive selection."""
from common import *
import subprocess
from repair_analysis import summarize,safety
from repair_result_details import details

def main():
    setup('repair/dev_summaries');compatibility()
    root=ROOT/'repair_v1';base=ROOT/'runs'/read(root/'ACTIVE_RUN.json')['run']
    pending=['validation_baseline','validation_repair','reference_validation_diagnostic','validation_preservation','validation_matched','validation_extra','validation_high_pdms']
    while pending:
        receipts={p.stem for p in (base/'receipts').glob('*.json')}
        tasks=read(base/'tasks.json')
        for name in pending[:]:
            selected=[t for t in tasks if t['stage']==name]
            if not selected or any(t['id'] not in receipts for t in selected):continue
            folder=root/'analysis'/name
            result=read(folder/'SUMMARY.json') if (folder/'SUMMARY.json').exists() else summarize(base,name)
            safety(name)
            if name!='validation_baseline' and not (folder/'DETAILS.json').exists():details(name)
            if name=='reference_validation_diagnostic' and not (folder/'REFERENCE_COVERAGE.json').exists():
                subprocess.run([sys.executable,'-B',str(ROOT/'code/repair_reference_analysis.py'),'--stage',name],check=True,cwd=ROOT)
            print(json.dumps(dict(status='ANALYZED',stage=name,records=result['records'])),flush=True);pending.remove(name)
        if pending:time.sleep(60)
    atomic(root/'DEVELOPMENT_ANALYSES_COMPLETE.json',dict(status='COMPLETE',time=stamp(),run=base.name))
    print(json.dumps(dict(status='DEVELOPMENT_ANALYSES_COMPLETE',time=stamp())),flush=True)

if __name__=='__main__':main()
