"""Inventory actual saved methods, never filter on online/scored performance."""
from r3_common import *
from collections import Counter
import argparse
import socket
import traceback


class Inventory:
    def __init__(self):
        self.items={}; self.sources=[]; self.errors=[]; self.counts=Counter(); self.started=time.monotonic()

    def progress(self,phase,count=0):
        atomic(ROOT/'provenance/inventory/LIVE.json',dict(status='RUNNING',time=stamp(),phase=phase,scanned=count,
               candidates=len(self.items),errors=len(self.errors),seconds=time.monotonic()-self.started,hostname=socket.gethostname()))

    def canonical(self,value):
        if isinstance(value,list): return [self.canonical(v) for v in value]
        if not isinstance(value,dict): return value
        ignored={'id','slot','system','parent_system','fit_seed','heldout_fold','K','expert','fit_id','config','centering','r','parent','ungated_parent'}
        result={}
        for k,v in value.items():
            if k in ignored: continue
            if k.endswith('_path') and (k[:-5]+'_sha256') in value: continue
            if k=='path' and 'sha256' in value: continue
            result[k]=self.canonical(v)
        return result

    def add(self,kind,spec,source,scope='unknown',alias=None):
        semantic=dict(kind=kind,definition=self.canonical(spec));ident='r3_'+digest(semantic)[:24]
        if ident not in self.items:
            self.items[ident]=dict(id=ident,kind=kind,specification=spec,source_scope=scope,aliases=[],source_manifests=[],
                                  asset_status='PENDING_RUNTIME_AND_ASSET_VERIFICATION',not_selected_on_online_gain=True)
        record=self.items[ident]
        if scope=='all_exploration_fit':record['source_scope']=scope
        alias=alias or spec.get('id')
        if alias and alias not in record['aliases']:record['aliases'].append(alias)
        if source not in record['source_manifests']:record['source_manifests'].append(source)
        self.counts[kind]+=1

    def first(self):
        files=sorted((BATCH1/'vlm_repair_v1/oracle_all/panels').glob('*.json'))
        for index,path in enumerate(files):
            try:
                panel=read(path)
                for method in panel.get('methods',[]):
                    arm=method['arm'];kind='batch1_upstream' if 'block' in arm else 'batch1_action_or_postprocess'
                    if arm.get('method') in ['patch','patch_full']:
                        kind='batch1_reference_patch'
                    self.add(kind,arm,str(path),scope='historical_fit_requires_audit',alias=arm.get('id'))
            except Exception as error:self.errors.append(dict(path=str(path),error=repr(error)))
            if index%25==0:self.progress('batch1_scored_methods',index)
        self.sources.append(dict(kind='batch1_actual_scored_panel_manifests',files=len(files)))

    def second_libraries(self):
        folders=['expert_library_selection','variant_library_selection','spatial_library_selection','unified_bc_library_selection',
                 'unified_bcs_library_selection','causal_library_selection']
        total=0
        for name in folders:
            files=sorted((BATCH2/'analysis'/name).glob('*.json'))
            for path in files:
                try:
                    data=read(path);scope='all_exploration_fit' if data.get('heldout_fold')==-1 else 'crossvalidation_fit'
                    for part in data.get('arms',[]): self.add('batch2_'+part['kind'],part,str(path),scope,part['id'])
                except Exception as error:self.errors.append(dict(path=str(path),error=repr(error)))
                total+=1
                if total%25==0:self.progress('batch2_library_parts',total)
            self.sources.append(dict(kind=name,files=len(files)))

    def training_checkpoints(self):
        # Include retained intermediate checkpoints and models not selected into
        # old libraries; whole-training duplicates deduplicate by checkpoint SHA.
        folders=sorted(p for p in (BATCH2/'learned_experts').iterdir() if p.is_dir())
        for index,folder in enumerate(folders):
            path=folder/'TRAINING.json'
            if not path.exists():continue
            try:
                data=read(path);task=data['task'];held=task.get('heldout_fold',data.get('heldout_fold'))
                if 'block' not in task or 'group' not in task:continue
                for cp in data.get('checkpoints',[]):
                    part=dict(kind='learned',id=folder.name+'_step'+str(cp['step']),training_task=task,checkpoint=cp,strength=1.)
                    self.add('batch2_learned',part,str(path),'all_exploration_fit' if held==-1 else 'crossvalidation_fit',part['id'])
            except Exception as error:self.errors.append(dict(path=str(path),error=repr(error)))
            if index%25==0:self.progress('batch2_all_retained_training_checkpoints',index)
        self.sources.append(dict(kind='retained_training_folders',files=len(folders)))

    def policies(self):
        latest=read(BATCH2/'analysis/all_data_policy_catalog/LATEST.json');catalog_path=BATCH2/latest['path'];catalog=read(catalog_path)
        assert sha(catalog_path)==latest['sha256']
        cache={}
        for index,entry in enumerate(catalog['entries']):
            try:
                path=BATCH2/entry['artifact']
                if str(path) not in cache:cache[str(path)]=read(path)
                value=cache[str(path)];kind=entry['kind']
                if kind in ['joint','finite']:
                    spec=dict(kind=kind,configuration=value.get('configuration',value));parts=spec['configuration']['model']['parts']
                else:
                    spec=dict(kind=kind,policy_path=entry['artifact'],policy_sha256=entry['sha256']);parts=value.get('parts',[])
                self.add('batch2_policy_'+kind,spec,str(path),'all_exploration_fit',entry.get('system','')+'/'+entry.get('policy',''))
                for part in parts:self.add('batch2_'+part['kind'],part,str(path),'all_exploration_fit',part['id'])
            except Exception as error:self.errors.append(dict(path=entry.get('artifact'),error=repr(error)))
            if index%25==0:self.progress('frozen_all_data_policy_catalog',index)
        self.sources.append(dict(kind='frozen_all_data_policy_catalog',path=str(catalog_path),sha256=latest['sha256'],entries=len(catalog['entries'])))

    def finish(self):
        items=sorted(self.items.values(),key=lambda v:(v['kind'],v['id']))
        counts=Counter(v['kind'] for v in items);scopes=Counter(v['source_scope'] for v in items)
        result=dict(status='METADATA_INVENTORY_COMPLETE_ASSET_AND_RUNTIME_AUDIT_PENDING',time=stamp(),candidates=items,
                    unique_candidates=len(items),kind_counts=dict(counts),scope_counts=dict(scopes),sources=self.sources,read_errors=self.errors,
                    seconds=time.monotonic()-self.started,models_loaded=False,scientific_inference_started=False,
                    scope='Actual scored batch1 definitions; saved batch2 library experts and all retained learned checkpoints; frozen all-data policies. No online-performance screening. CV variants retained separately; runtime readiness not yet asserted.')
        atomic(ROOT/'manifests/INVENTORY_RAW_V1.json',result)
        atomic(ROOT/'provenance/inventory/COMPLETE.json',{k:v for k,v in result.items() if k!='candidates'})
        self.progress('COMPLETE',len(items));print(json.dumps({k:v for k,v in result.items() if k not in ['candidates','read_errors','sources']},ensure_ascii=False),flush=True)


def main():
    setup('inventory',threads=2)
    lock=(ROOT/'provenance/inventory/LOCK');lock.parent.mkdir(parents=True,exist_ok=True)
    import fcntl
    with lock.open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert not (ROOT/'manifests/INVENTORY_RAW_V1.json').exists()
        task=Inventory();task.first();task.second_libraries();task.training_checkpoints();task.policies();task.finish()


if __name__=='__main__':
    try:main()
    except BaseException as error:
        atomic(ROOT/'provenance/inventory/FAILED.json',dict(time=stamp(),error=repr(error),traceback=traceback.format_exc()))
        raise
