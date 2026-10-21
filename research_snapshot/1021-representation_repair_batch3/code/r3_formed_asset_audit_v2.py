"""Read-only fingerprint audit of formed candidates; no outcome-based filtering."""
from r3_common import *
from concurrent.futures import ThreadPoolExecutor,as_completed
from collections import Counter
import argparse
import socket
import traceback
import zipfile


def main(a):
    setup('formed_asset_audit_v2/'+a.node,threads=1)
    if a.node=='dsw':assert socket.gethostname()==read(ROOT/'resources/DSW_PREFLIGHT_V1.json')['hostname']
    else:
        node=next(v for v in read(ROOT/'resources/REGISTRY.json')['nodes'] if v['name']==a.node);assert socket.gethostname().startswith(node['job']+'-')
    destination=ROOT/'provenance/formed_asset_audit_v2';assert not (destination/'COMPLETE.json').exists()
    catalog_path=ROOT/'manifests/FORMED_CATALOG_DRAFT_V3.json';catalog=read(catalog_path);assets={};requirements={};definitions={};problems=[]
    def asset(path,hashed,ident,role):
        path=Path(path).resolve();assert path.is_relative_to(BATCH1) or path.is_relative_to(BATCH2)
        assert len(hashed)==64
        key=digest(dict(path=str(path),sha256=hashed));record=assets.setdefault(key,dict(path=str(path),sha256=hashed,required_by=[],roles=[]))
        if ident not in record['required_by']:record['required_by'].append(ident)
        if role not in record['roles']:record['roles'].append(role)
        requirements.setdefault(ident,[]).append(key)
    def arm(root,value,ident):
        if value.get('method')=='combination':
            for part in value['parts']:arm(root,part,ident)
        elif value.get('fit_path'):asset(root/value['fit_path'],value['fit_sha256'],ident,'analytic_fit')
        if value.get('observation_gate'):
            fit=value['observation_gate']['fit'];asset(root/fit['path'],fit['sha256'],ident,'observation_gate')
    def part(value,ident):
        if value['kind']=='analytic':arm(BATCH2,value['arm'],ident)
        elif value['kind']=='learned':
            cp=value['checkpoint'];asset(BATCH2/cp['path'],cp['sha256'],ident,'learned_checkpoint')
        elif value['kind']=='delta':
            fit=value['fit'];asset(BATCH2/fit['path'],fit['sha256'],ident,'delta_fit')
        else:raise ValueError(value['kind'])
    for entry in catalog['entries']:
        ident=entry['id'];definition=entry['definition'];kind=entry['kind'];definitions[ident]=entry
        try:
            if kind=='batch1_upstream':arm(BATCH1,definition['arm'],ident)
            elif kind=='batch1_action_or_postprocess':
                # The legacy action editor derives fit paths from step/layer/k;
                # resolve these in its separate runtime adapter, not by guessing.
                entry['asset_status']='REQUIRES_LEGACY_DERIVED_FIT_RESOLUTION';continue
            elif kind.startswith('batch2_policy_'):
                path=BATCH2/definition['policy_path'];asset(path,definition['policy_sha256'],ident,'complete_policy')
                assert sha(path)==definition['policy_sha256'];policy=read(path);assert policy['heldout_fold']==-1
                policy_kind=kind[len('batch2_policy_'):]
                if policy_kind in ['joint','finite']:
                    config=policy['configuration'];cp=config['checkpoint'];asset(BATCH2/cp['path'],cp['sha256'],ident,'router_checkpoint');parts=config['model']['parts']
                else:
                    parts=policy['parts']
                    if policy_kind in ['hard','candidate']:
                        asset(BATCH2/policy['model_path'],policy['model_sha256'],ident,'router_model');meta=policy['feature_meta'];asset(BATCH2/meta['path'],meta['sha256'],ident,'router_feature_transform')
                    elif policy_kind=='token':
                        cp=policy['critic']['checkpoint'];asset(BATCH2/cp['path'],cp['sha256'],ident,'token_critic_checkpoint')
                for value in parts:part(value,ident)
            else:part(definition,ident)
        except Exception as error:problems.append(dict(candidate=ident,error=repr(error)));entry['asset_status']='DEFINITION_REQUIRES_REVIEW'
    atomic(destination/'ASSET_TASKS.json',dict(catalog_sha256=sha(catalog_path),assets=assets,requirements=requirements,definition_problems=problems))
    def check(item):
        key,record=item
        try:
            path=Path(record['path']);actual=sha(path);assert actual==record['sha256'],dict(expected=record['sha256'],actual=actual)
            result=dict(status='PASS_FINGERPRINT',bytes=path.stat().st_size)
            if path.suffix=='.npz':
                with zipfile.ZipFile(path) as archive:result['array_names']=[name[:-4] for name in archive.namelist() if name.endswith('.npy')]
            return key,result
        except Exception as error:return key,dict(status='FAILED_ASSET_AUDIT',error=repr(error))
    results={};began=time.monotonic()
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for future in as_completed([pool.submit(check,item) for item in assets.items()]):
            key,result=future.result();results[key]=result
            if len(results)%64==0:atomic(destination/'LIVE.json',dict(status='RUNNING',time=stamp(),completed=len(results),total=len(assets),failed=sum(v['status']!='PASS_FINGERPRINT' for v in results.values()),seconds=time.monotonic()-began,pid=os.getpid(),node=a.node))
    for ident,entry in definitions.items():
        if entry.get('asset_status') in ['DEFINITION_REQUIRES_REVIEW','REQUIRES_LEGACY_DERIVED_FIT_RESOLUTION']:continue
        failed=[key for key in set(requirements.get(ident,[])) if results[key]['status']!='PASS_FINGERPRINT']
        entry['asset_status']='PASS_ALL_EXPLICIT_ASSET_FINGERPRINTS' if not failed else 'FAILED_ASSET_AUDIT';entry['failed_asset_keys']=failed
    atomic(destination/'RESULTS.json',dict(assets=assets,results=results,requirements=requirements,definition_problems=problems))
    atomic(ROOT/'manifests/FORMED_CATALOG_ASSET_AUDITED_V2.json',dict(catalog,entries=list(definitions.values()),asset_audit_source=str((destination/'RESULTS.json').relative_to(ROOT)),asset_audit_sha256=sha(destination/'RESULTS.json'),
             status='ASSET_AUDITED_RUNTIME_ADMISSION_PENDING',test_or_online_gain_used_for_filtering=False))
    summary=dict(status='AUDIT_COMPLETE_REVIEW_REQUIRED',time=stamp(),node=a.node,assets=len(assets),failed_assets=sum(v['status']!='PASS_FINGERPRINT' for v in results.values()),
                 definition_problems=problems,candidate_status_counts=dict(Counter(v['asset_status'] for v in definitions.values())),seconds=time.monotonic()-began,model_inference=False)
    atomic(destination/'COMPLETE.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    try:main(a)
    except BaseException as error:
        atomic(ROOT/'provenance/formed_asset_audit_v2/FAILED.json',dict(status='FAILED',time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise
