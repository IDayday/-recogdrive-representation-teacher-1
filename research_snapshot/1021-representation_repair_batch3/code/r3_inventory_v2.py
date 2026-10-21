"""Resolve finite-checkpoint schema and deduplicate executable learned states."""
from r3_common import *
from r3_inventory import Inventory
from collections import Counter
import socket
import traceback


class RevisedInventory(Inventory):
    def canonical(self,value):
        if isinstance(value,dict) and value.get('kind')=='learned' and 'checkpoint' in value:
            t=value['training_task']
            return dict(kind='learned',block=t['block'],group=t['group'],cap=t['cap'],strength=value.get('strength',1.),checkpoint_sha256=value['checkpoint']['sha256'])
        if isinstance(value,dict) and value.get('kind')=='delta' and 'fit' in value:
            f=value['fit']
            return dict(kind='delta',block=f['block'],group=f['group'],cap=f['cap'],strength=value.get('strength',1.),fit_sha256=f['sha256'])
        return super().canonical(value)

    def progress(self,phase,count=0):
        atomic(ROOT/'provenance/inventory_v2/LIVE.json',dict(status='RUNNING',time=stamp(),phase=phase,scanned=count,
               candidates=len(self.items),errors=len(self.errors),seconds=time.monotonic()-self.started,hostname=socket.gethostname()))

    def policies(self):
        latest=read(BATCH2/'analysis/all_data_policy_catalog/LATEST.json');path=BATCH2/latest['path'];catalog=read(path)
        assert sha(path)==latest['sha256'];cache={}
        for index,e in enumerate(catalog['entries']):
            try:
                if 'artifact' not in e:
                    training=read(BATCH2/e['training'])
                    spec=dict(kind='finite_checkpoint',training=e['training'],training_sha256=e['training_sha256'],checkpoint=e['checkpoint'],
                              input_dimension=training['input_dimension'],tier=training['tier'],parts=training['parts'],heldout_fold=training['heldout_fold'])
                    self.add('batch2_policy_finite_checkpoint',spec,str(BATCH2/e['training']),'all_exploration_fit',e['system']+'/'+e['policy'])
                    for part in training['parts']:self.add('batch2_'+part['kind'],part,str(BATCH2/e['training']),'all_exploration_fit',part['id'])
                else:
                    src=BATCH2/e['artifact']
                    if str(src) not in cache:cache[str(src)]=read(src)
                    p=cache[str(src)];kind=e['kind']
                    if kind in ['joint','finite']:
                        spec=dict(kind=kind,configuration=p.get('configuration',p));parts=spec['configuration']['model']['parts']
                    else:spec=dict(kind=kind,policy_path=e['artifact'],policy_sha256=e['sha256']);parts=p.get('parts',[])
                    self.add('batch2_policy_'+kind,spec,str(src),'all_exploration_fit',e['system']+'/'+e['policy'])
                    for part in parts:self.add('batch2_'+part['kind'],part,str(src),'all_exploration_fit',part['id'])
            except Exception as error:self.errors.append(dict(entry=e,error=repr(error)))
            if index%25==0:self.progress('all_data_policy_and_finite_checkpoints',index)
        self.sources.append(dict(kind='frozen_all_data_policy_catalog',path=str(path),sha256=latest['sha256'],entries=len(catalog['entries'])))

    def finish(self):
        items=sorted(self.items.values(),key=lambda v:(v['kind'],v['id']))
        result=dict(status='METADATA_INVENTORY_COMPLETE_ASSET_AND_RUNTIME_AUDIT_PENDING',time=stamp(),candidates=items,
                    unique_candidates=len(items),kind_counts=dict(Counter(v['kind'] for v in items)),scope_counts=dict(Counter(v['source_scope'] for v in items)),
                    sources=self.sources,read_errors=self.errors,seconds=time.monotonic()-self.started,models_loaded=False,
                    scope='Includes wide-search grid points, CV models and intermediate checkpoints; these are not all final formed experts. Candidate scope awaiting explicit clarification.',
                    previous_inventory='manifests/INVENTORY_RAW_V1.json',metadata_correction='Finite catalog entries use training+checkpoint rather than artifact; learned model dedup uses actual executable checkpoint SHA and site/cap.')
        assert not (ROOT/'manifests/INVENTORY_RAW_V2.json').exists()
        atomic(ROOT/'manifests/INVENTORY_RAW_V2.json',result)
        summary={k:v for k,v in result.items() if k!='candidates'};summary['read_error_count']=len(self.errors)
        atomic(ROOT/'provenance/inventory_v2/COMPLETE.json',summary)
        print(json.dumps({k:v for k,v in summary.items() if k not in ['read_errors','sources']},ensure_ascii=False),flush=True)


if __name__=='__main__':
    try:
        setup('inventory_v2',threads=2)
        task=RevisedInventory();task.first();task.second_libraries();task.training_checkpoints();task.policies();task.finish()
    except BaseException as error:
        atomic(ROOT/'provenance/inventory_v2/FAILED.json',dict(time=stamp(),error=repr(error),traceback=traceback.format_exc()));raise
