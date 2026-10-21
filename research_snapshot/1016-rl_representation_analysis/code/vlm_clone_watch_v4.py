"""Quiet, lower-frequency event monitoring; frozen experiments are unchanged."""
from common import *
import argparse,contextlib
import vlm_clone_watch_v3 as cloud_watch
from vlm_clone_watch_v2 import resolved
from vlm_elastic_registry import DEST

class EventsOnly:
    def __init__(self, stream):self.stream=stream;self.pending=''
    def write(self, text):
        self.pending+=text
        while '\n' in self.pending:
            line,self.pending=self.pending.split('\n',1)
            if line.startswith(('WAKE_', 'TRANSIENT_')):
                self.stream.write(line+'\n');self.stream.flush()
        return len(text)
    def flush(self):self.stream.flush()

def main(a):
    assert 60<=a.period<=600
    previous=cloud_watch.previous
    previous.WATCH=previous.WATCH+[DEST/'analysis_move/SERVICE_READY.json']+[
        ROOT/read(ROOT/n['config'])['folder']/name
        for n in read(DEST/'REGISTRY.json')['nodes'] if n['kind']=='elastic'
        for name in ['FIVE_MINUTE_PHASE_CHECK.json','GPU_QUEUE_FIVE_MINUTE_CHECK.json']]
    previous.adapter_failure_resolved=resolved
    previous.age=cloud_watch.age;previous.atomic=cloud_watch.atomic
    with contextlib.redirect_stdout(EventsOnly(sys.stdout)):previous.main(a)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--legacy-resume',default='vlm_repair_v1/resume/20261017T035006')
    p.add_argument('--period',type=int,default=300);p.add_argument('--warn-minutes',type=float,default=120)
    p.add_argument('--once',action='store_true');main(p.parse_args())
