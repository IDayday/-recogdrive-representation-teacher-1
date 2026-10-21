"""Replay family-diverse per-block coarse finalists on fresh exploration cases."""
from common import *
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic
from vlm_repair_queue_v2 import stage
from vlm_results import summarize
RUN='vlm_repair_20261016_v2'

def panel():
    old={r['token'] for r in read(VOUT/'development/COARSE_PANEL.json')};rows=[r for r in read(ROOT/'manifests/natural_s0.json') if r['subset']=='exploration' and r['token'] not in old];take=[]
    for label,n in [('failure',128),('high_quality',64),('intermediate',64)]:
        group=sorted([r for r in rows if r['quality']==label],key=lambda r:digest(dict(token=r['token'],vlm_replay_root=20261016)));take.extend(group[:n])
    assert len(take)==256 and len({r['token'] for r in take})==256;return take

def choose(summaries):
    records=[r for s in summaries for r in s['summaries']];chosen={}
    def keep(r):chosen[r['arm']['id']]=r['arm']
    for method in sorted({r['arm']['method'] for r in records}):
        group=[r for r in records if r['arm']['method']==method]
        keep(max(group,key=lambda r:(r['population_weighted_delta_pdms'],-r['collision_new']-r['offroad_new'],-r['arm']['cap'])))
        keep(max(group,key=lambda r:(r['oracle_failure_gate_delta_pdms'],r['repaired_gt90'],r['oracle_benefit_gate_delta_pdms'])))
    for s in summaries:
        keep(max(s['summaries'],key=lambda r:(r['population_weighted_delta_pdms'],r['oracle_failure_gate_delta_pdms'])))
    return list(chosen.values())

def main():
    setup('vlm_repair/replay');folder=VOUT/'replay';folder.mkdir(exist_ok=True);base=ROOT/'runs'/RUN
    if not (folder/'PANEL.json').exists():atomic(folder/'PANEL.json',panel())
    rows=read(folder/'PANEL.json');done=set()
    while True:
        for p in sorted((VOUT/'development').glob('*.json')):
            if p.stem in done or p.name in ['COARSE_PANEL.json','STATUS.json','FIRST_FIT_READY.json','ALL_COARSE_APPENDED.json']:continue
            selected=read(p)
            if selected.get('status')!='FROZEN_DEVELOPMENT_BLOCK':continue
            block=selected['block'];fits=[read(q)['fit'] for q in (VOUT/'development/completed_fits').glob('*.json') if read(q)['fit']['block']==block]
            rejected=list((VOUT/'development/rejected_fits').glob('*.json'))
            if len(fits)<len(selected['selected']):continue
            name='replay_'+block
            if (base/'stages'/name/'PROTOCOL.json').exists():done.add(p.stem);continue
            summaries=[]
            for fit in fits:
                r=summarize(base,'coarse_'+fit['id'])
                if r is None:break
                summaries.append(r)
            if len(summaries)!=len(fits):continue
            arms=choose(summaries);atomic(folder/(block+'_LOCK.json'),dict(status='FROZEN',time=stamp(),block=block,source_coarse_stages=[s['stage'] for s in summaries],arms=arms,
                selection='per operator best population-weighted + best external failure-only Oracle, plus best of each rank-band/variance/full representative',new_exploration_panel=True,no_validation_or_test_used=True))
            count=stage(base,name,rows,arms,[0],chunk=4,arm_chunk=64);done.add(p.stem);print(json.dumps(dict(event='REPLAY_APPENDED',block=block,arms=len(arms),tasks=count)),flush=True)
        atomic(folder/'STATUS.json',dict(status='REPLAYING',time=stamp(),blocks_appended=len(done),expected_primary_blocks=62))
        if len(done)==62:break
        time.sleep(10)
    atomic(folder/'ALL_REPLAY_APPENDED.json',dict(status='PASS',time=stamp(),blocks=len(done)))
if __name__=='__main__':main()
