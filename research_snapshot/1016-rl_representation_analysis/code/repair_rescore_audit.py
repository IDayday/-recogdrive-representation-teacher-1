"""Stratified independent rescoring through the original readonly source, after test lock."""
from common import *
import argparse
import subprocess

def main(args):
    setup('repair/rescore_audit');compatibility()
    base=ROOT/'runs'/args.run;panel=read(base/'stages/final_test/panel.json');by={r['token']:r for r in panel}
    cfg=read(ROOT/'configs/baseline.json');groups={k:[] for k in ['repair','damage','new_collision','collision_removed','random']}
    import random
    rng=random.Random(20261016);reservoir=[];seen=0
    for path in sorted((base/'results').glob('final_test_s*.json')):
        doc=read(path);per={}
        for r in doc['records']:per.setdefault(r['token'],[]).append(r)
        for token,records in per.items():
            baseline=next(r for r in records if r['arm']=='baseline')
            for r in records:
                kinds=[];b=baseline['score'];e=r['score']
                if r['arm']!='baseline':
                    if b['score']<.7 and e['score']>=.7:kinds.append('repair')
                    if b['score']>.9 and e['score']<.7:kinds.append('damage')
                    if b['no_at_fault_collisions']==1 and e['no_at_fault_collisions']<1:kinds.append('new_collision')
                    if b['no_at_fault_collisions']<1 and e['no_at_fault_collisions']==1:kinds.append('collision_removed')
                for kind in kinds:groups[kind].append(r)
                seen+=1
                if len(reservoir)<600:reservoir.append(r)
                else:
                    j=rng.randrange(seen)
                    if j<600:reservoir[j]=r
    selected={};counts={}
    for kind in ['repair','damage','new_collision','collision_removed']:
        rng.shuffle(groups[kind]);take=groups[kind][:100];counts[kind]=len(take)
        for r in take:selected[(r['token'],r['seed_index'],r['arm'])]=r
    rng.shuffle(reservoir)
    for r in reservoir:
        if len(selected)>=600:break
        selected[(r['token'],r['seed_index'],r['arm'])]=r
    assert len(selected)==600
    folder=base/'independent_rescore';folder.mkdir(exist_ok=True);expected=list(selected.values())
    tasks=[dict(token=r['token'],trajectory=r['trajectory'],metric_cache=by[r['token']]['metric_cache'],metric_sha256=r['metric_sha256'],scoring=cfg['scoring']) for r in expected]
    request=folder/'request.json';response=folder/'response.json';assert not request.exists() and not response.exists()
    atomic(request,tasks);atomic(folder/'expected.json',expected)
    subprocess.run([sys.executable,'-B',str(ROOT/'code/score.py'),str(request),str(response),
        '--original-source','/mnt/yehr_workspace/ReCogDrive/ReCogDrive/recogdrive'],check=True,cwd=ROOT)
    actual=read(response);assert actual['status']=='PASS'
    assert len(actual['results'])==len(expected)==600
    maximum=0.
    for a,b in zip(expected,actual['results']):
        assert a['token']==b['token'] and a['quality']==b['quality']
        for key,v in a['score'].items():maximum=max(maximum,abs(v-b['score'][key]))
    assert maximum==0.
    atomic(folder/'ACCEPTANCE.json',dict(status='PASS',time=stamp(),records=600,strata_available={k:len(v) for k,v in groups.items() if k!='random'},
        strata_requested=counts,maximum_component_difference=maximum,source=actual['import_source'],
        request_sha256=sha(request),response_sha256=sha(response),saved_trajectories_scored=True))
    print(json.dumps(dict(status='PASS',records=600,maximum_difference=maximum)),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);main(p.parse_args())
