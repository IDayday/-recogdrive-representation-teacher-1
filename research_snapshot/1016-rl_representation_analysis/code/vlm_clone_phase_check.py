"""Five-minute semantic and resource check inside an explicitly adopted clone."""
from common import *
import argparse,socket,collections,psutil
from vlm_elastic_registry import DEST,configuration
from repair_queue_v2 import atomic_unique as atomic

def main(a):
    c=configuration(a.id);folder=ROOT/c['folder'];lease=read(folder/'ADOPTED_CLONE.json')
    assert socket.gethostname().startswith(lease['job'])
    for name in ['EXECUTION.json','CLONE_EXECUTION.json','CLONE_ADMIN_EXECUTION.json']:
        for path,h in read(DEST/name)['code_sha256'].items():assert sha(ROOT/path)==h,path
    began=dt.datetime.fromisoformat(read(folder/'LAUNCHED.json')['time'])
    while (dt.datetime.now(dt.timezone.utc)-began).total_seconds()<a.minimum_age:time.sleep(5)
    states=read(folder/'STATUS.json');assert states['status']=='RUNNING'
    assert (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(states['time'])).total_seconds()<120
    for name in ['PREFLIGHT.json','CPU_SMOKE_PASS.json','GPU_SMOKE_PASS.json','ENGINEERING_PASS.json']:assert read(folder/name)['status']=='PASS'
    for sub in ['failures','clone_wrapper_failures','command_failures']:assert not list((folder/sub).glob('*.json'))
    scan=DEST.parent/'scan';ranks=set(range(c['cpu_rank_base'],c['cpu_rank_base']+c['cpu_workers']))
    cpu=[read(scan/'workers'/f'rank{rank:03d}.json') for rank in sorted(ranks)]
    assert all(d['rank'] in ranks and d['status'] in ['COMPUTING','RUNNING','QUEUE_WAIT'] for d in cpu)
    active=[]
    for d in cpu:
        if d['status']!='COMPUTING':continue
        owner=read(scan/'claims'/d['task']/'OWNER.json');assert owner['rank']==d['rank']
        assert (DEST.parent/'cells'/(owner['task']['cell']+'.json')).exists()
        active.append(dict(rank=d['rank'],task=d['task']))
    receipts=[];outcomes=collections.Counter()
    for p in (scan/'receipts').glob('*.json'):
        r=read(p)
        if r['rank'] not in ranks:continue
        result=scan/'results'/p.name;assert sha(result)==r['result_sha256'];v=read(result)
        assert v['cell']==r['task']['cell'];outcomes[v['status']]+=1
        if v['status']=='INELIGIBLE':assert v['reason']
        receipts.append(dict(path=str(p.relative_to(ROOT)),result_sha256=r['result_sha256'],rank=r['rank'],status=v['status']))
    gpu=[read(folder/'gpu_workers'/f'rank{rank:03d}.json') for rank in c['gpu_ranks']]
    assert all(d['status'] in ['WAITING_ACTIVATION','RUNNING','COMPUTING','QUEUE_WAIT'] for d in gpu)
    result=dict(status='PASS',time=stamp(),node=a.id,job=lease['job'],elapsed_seconds=(dt.datetime.now(dt.timezone.utc)-began).total_seconds(),
        all_configured_cards_real_smoke_pass=c['cards'],real_validation_replay_exact=True,
        cpu_workers=c['cpu_workers'],cpu_states=dict(collections.Counter(d['status'] for d in cpu)),
        active_tasks=active,completed_cpu_receipts=receipts,completed_status_counts=dict(outcomes),
        ineligible_results_are_not_quality_claims=True,gpu_states=dict(collections.Counter(d['status'] for d in gpu)),
        cpu_percent=psutil.cpu_percent(interval=1),memory_available=psutil.virtual_memory().available,
        queue_closed=False,main_retained=True,minimum_runtime_minutes=lease['confirmed_max_minutes'],
        checker_sha256=sha(Path(__file__)))
    atomic(folder/'FIVE_MINUTE_PHASE_CHECK.json',result)
    print('FIVE_MINUTE_CLONE_PHASE_PASS',a.id,'cpu',result['cpu_states'],'results',dict(outcomes),'gpu',result['gpu_states'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--id',required=True);p.add_argument('--minimum-age',type=int,default=300);main(p.parse_args())
