"""Prespecified residual coverage review over the complete saved CV arrays.

Keep all S0-eligible configurations in compact, sorted tables. Lazily evaluate
S1/S2 only in that fixed order, using checkpointed existing representations.
Neither validation nor test outcomes are candidate-selection inputs.
"""
from common import *
import argparse, fcntl, subprocess, traceback
import numpy as np
from threadpoolctl import threadpool_limits
from vlm_core import VOUT
from vlm_selection import neighbor_indices, finite
from vlm_scan import metric_dict
from vlm_late_qualification import qualify, DEST
from repair_queue_v2 import atomic_unique as atomic
from repair_queue_v2 import append, claim

BASE=ROOT/'runs/vlm_late_qualification_20261017_v1'

DT=np.dtype([('score','f8'),('minimum','f8'),('ap','f8'),('cell','u2'),
             ('config','u2'),('center','u1'),('supported','u1')])


def component(block):
    return 'vision' if block.startswith('vision') else 'bridge' if block.startswith('bridge') else 'interface' if block.startswith('interface') else 'language'


def groups():
    p=read(VOUT/'LATE_TOKEN_COVERAGE_PROTOCOL_v3.json')['groups']
    return [(c,k,e,lo,hi) for c in p['components'] for k in p['constructions']
            for e in p['equal'] for lo,hi in p['rank_bands']]


def group_key(g):
    c,k,e,lo,hi=g
    return f'{c}_{k}_{"equal" if e else "unequal"}_r{lo}_{hi}'


def physical(cell,cfg,center):
    return cell,cfg['kind'],cfg.get('ks'),cfg.get('kf'),cfg.get('r'),int(center)


def neighbors(entries):
    result=np.full((len(entries),6),-1,dtype=np.int32)
    for i,c in enumerate(entries):
        if c['kind'].endswith('residual'):
            at=neighbor_indices(c,entries);assert len(at)<=6
            result[i,:len(at)]=at
    return result


def pool():
    marker=DEST/'POOL_READY.json'
    if marker.exists():
        previous=read(marker);assert previous['code_sha256']==sha(Path(__file__))
        return previous
    tasks=read(VOUT/'scan/tasks.json')
    assert len(tasks)==len(list((VOUT/'scan/receipts').glob('*.json')))==2272
    entries=read(VOUT/'scan/CONFIGS.json');near=neighbors(entries);safe_near=np.maximum(near,0)
    cells=sorted(t['cell'] for t in tasks);tested=set();fit_proofs=[]
    for p in sorted((VOUT/'fits').glob('*.json')):
        fit=read(p);cfg=fit['config']
        if cfg['kind'].endswith('residual'):
            tested.add(physical(fit['cell'],cfg,fit['centering']=='pooled_centered'))
            fit_proofs.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p)))
    bins={g:[] for g in groups()};source_proofs=[];excluded=[]
    masks={g:np.array([c['kind']==g[1] and c.get('equal')==g[2] and g[3]<=(c.get('r') or 0)<=g[4] for c in entries]) for g in groups()}
    for ci,cell in enumerate(cells):
        path=VOUT/'scan/results'/(cell+'.json');r=read(path)
        receipt=read(VOUT/'scan/receipts'/path.name);assert sha(path)==receipt['result_sha256']
        if r['status']!='COMPLETE' or r['valid_cases']!=103288:
            excluded.append(dict(cell=cell,status=r['status'],valid_cases=r.get('valid_cases')));continue
        assert r['training_class_sizes']==[74900,1850]
        assert sha(ROOT/r['array_path'])==r['array_sha256']
        source_proofs.append(dict(path=str(path.relative_to(ROOT)),sha256=sha(path),array_path=r['array_path'],array_sha256=r['array_sha256']))
        with np.load(ROOT/r['array_path']) as z:
            matrix=z['metrics'];eligible=(z['status']==0).all(1)&~z['cutoff_degenerate'].any(1)
            for cc in [0,1]:
                m=matrix[cc,5];folds=matrix[cc,:5,:,0]
                minimum=np.min(folds,axis=0);spread=np.std(folds,axis=0)
                supported=((m[safe_near,0]>=np.maximum(.55,m[:,0]-.03)[:,None])
                           &eligible[cc,safe_near]&(near>=0)).sum(1)
                keep=eligible[cc]&np.isfinite(m[:,[0,1,2,4,8]]).all(1)&(m[:,0]>=.6)&(m[:,2]>=.2)
                keep&=(m[:,1]>m[:,8])&(minimum>.55)&(m[:,4]>=.65)&(supported>=2)
                keep&=np.array([physical(cell,c,cc) not in tested for c in entries])
                score=m[:,0]-.25*spread-.10*np.maximum(0.,.6-minimum)
                for g,mask in masks.items():
                    if component(cell.split('__',1)[0])!=g[0]:continue
                    indices=np.flatnonzero(keep&mask)
                    if not len(indices):continue
                    values=np.empty(len(indices),dtype=DT)
                    values['score']=score[indices];values['minimum']=minimum[indices];values['ap']=m[indices,1]
                    values['cell']=ci;values['config']=indices;values['center']=cc;values['supported']=supported[indices]
                    bins[g].append(values)
        if ci%100==0:print('LATE_FULL_ARRAY_POOL_PROGRESS',ci,len(cells),flush=True)
    tables=[]
    for g,parts in bins.items():
        values=np.concatenate(parts) if parts else np.empty(0,dtype=DT)
        order=np.lexsort((values['config'],values['center'],values['cell'],-values['ap'],-values['minimum'],-values['score']))
        values=values[order];path=DEST/'pool'/(group_key(g)+'.npy');path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():assert np.array_equal(np.load(path),values)
        else:
            temporary=path.with_suffix('.npy.tmp')
            with temporary.open('wb') as stream:np.save(stream,values)
            temporary.replace(path)
        tables.append(dict(group=list(g),key=group_key(g),path=str(path.relative_to(ROOT)),sha256=sha(path),candidates=len(values)))
    result=dict(status='ALL_S0_ELIGIBLE_CONFIGS_RETAINED_BEFORE_NOISE_QUALIFICATION',time=stamp(),cells=cells,
            tables=tables,excluded_cells=excluded,source_proofs=source_proofs,tested_fit_proofs=fit_proofs,
            old_physical_spaces_excluded=True,old_shortlist_not_a_limit=True,no_candidate_selected_using_validation_or_test=True,
            protocol_sha256=sha(VOUT/'LATE_TOKEN_COVERAGE_PROTOCOL_v3.json'),code_sha256=sha(Path(__file__)))
    atomic(marker,result)
    return result


def select_family(table,threads):
    p=read(DEST/'POOL_READY.json');entries=read(VOUT/'scan/CONFIGS.json')
    lock=DEST/'selected'/(table['key']+'.json')
    if lock.exists():return read(lock)
    path=ROOT/table['path'];assert sha(path)==table['sha256'];candidates=np.load(path,mmap_mode='r')
    winner=None;rejections=[]
    for row in candidates:
        cell=p['cells'][int(row['cell'])];i=int(row['config']);cc=int(row['center'])
        with threadpool_limits(threads):qualification=qualify(cell,i,cc)
        if not all(finite(n['metrics']['auc'])>.55 for n in qualification['other_sampling_seeds']):
            rejections.append(dict(cell=cell,config_index=i,center=cc,qualification=qualification));continue
        result_path=VOUT/'scan/results'/(cell+'.json');r=read(result_path)
        with np.load(ROOT/r['array_path']) as z:
            metric=np.array(z['metrics'][cc,5,i]);folds=np.array(z['metrics'][cc,:5,i,0])
            ranks=np.array(z['ranks'][cc,:,i]);adj=neighbor_indices(entries[i],entries)
            good=(z['status'][cc]==0).all(0)&~z['cutoff_degenerate'][cc].any(0)
            adj=[j for j in adj if good[j]];adj_values=z['metrics'][cc,5,adj,0]
        block,group=cell.split('__',1)
        winner=dict(config_index=i,config=entries[i],centering='pooled_centered' if cc else 'uncentered',
            metrics=metric_dict(metric),auc_fold_min=float(folds.min()),auc_fold_std=float(folds.std()),
            cutoff_degenerate_any=False,ranks=ranks.tolist(),other_sampling_seeds=qualification['other_sampling_seeds'],
            cell=cell,block=block,group=group,analysis_source='scan',source_result_sha256=sha(result_path),
            moment=dict(path=r['moment_path'],sha256=r['moment_sha256']),cell_proof_path=str((VOUT/'cells'/(cell+'.json')).relative_to(ROOT)),
            neighbor_supported=int(row['supported']),neighbor_tested=len(adj),neighbor_auc=adj_values.tolist(),
            stable_cv_region=True,rank_band=list(table['group'][-2:]),late_group=table['key'])
        break
    record=dict(status='FROZEN_FAMILY_SELECTION',time=stamp(),group=table['group'],selected=winner,
                rejected_secondary_seed_checks=rejections,pool_sha256=table['sha256'])
    atomic(lock,record);return record


def finalize_selection():
    marker=DEST/'SELECTION_LOCK.json'
    if marker.exists():
        previous=read(marker);assert previous['selector_sha256']==sha(Path(__file__))
        return previous
    p=read(DEST/'POOL_READY.json');family_records=[read(DEST/'selected'/(t['key']+'.json')) for t in p['tables']]
    selected=[r['selected'] for r in family_records if r['selected'] is not None]
    assert len(selected)<=48
    result=dict(status='FROZEN_BEFORE_LATE_REPAIR_AND_TEST',time=stamp(),selected=selected,
            families=family_records,source_pool_sha256=sha(DEST/'POOL_READY.json'),
            protocol_sha256=sha(VOUT/'LATE_TOKEN_COVERAGE_PROTOCOL_v3.json'),test_accessed=False,
            validation_used_for_selection=False,all_original_full_grids_complete=True,
            selector_sha256=sha(Path(__file__)))
    atomic(marker,result);print('LATE_TOKEN_SELECTION_LOCKED',len(selected),flush=True)
    return result


def select(threads):
    p=pool()
    for table in p['tables']:select_family(table,threads)
    return finalize_selection()


def verify_execution():
    for p,h in read(VOUT/'LATE_SELECTION_EXECUTION.json')['code_sha256'].items():
        assert sha(ROOT/p)==h,p


def controller(a):
    setup('vlm_repair/late_selection/controller');verify_execution()
    DEST.mkdir(exist_ok=True)
    with (DEST/'controller.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while len(list((VOUT/'scan/receipts').glob('*.json')))!=2272:time.sleep(60)
        document=pool()
        if not (BASE/'tasks.json').exists():
            # Interleave components so both nodes share large and small cells.
            tables=sorted(document['tables'],key=lambda t:(t['group'][1:],t['group'][0]))
            append(BASE,[dict(id=t['key'],table=t) for t in tables])
        while len(list((BASE/'receipts').glob('*.json')))!=48:
            atomic(DEST/'CONTROLLER_STATUS.json',dict(status='QUALIFYING_FIXED_FAMILIES',time=stamp(),
                completed=len(list((BASE/'receipts').glob('*.json'))),total=48))
            time.sleep(30)
        for p in (BASE/'receipts').glob('*.json'):
            receipt=read(p);assert sha(ROOT/receipt['result_path'])==receipt['result_sha256']
        finalize_selection()


def worker(a):
    setup(f'vlm_repair/late_selection/rank{a.rank:03d}');verify_execution()
    while not (BASE/'tasks.json').exists():time.sleep(30)
    with threadpool_limits(a.threads):
        while True:
            task=claim(BASE,a.rank)
            if task is None:time.sleep(15);continue
            assert task!='CLOSED'
            atomic(BASE/'workers'/f'rank{a.rank:03d}.json',dict(status='QUALIFYING',time=stamp(),rank=a.rank,task=task['id']))
            select_family(task['table'],a.threads)
            result=DEST/'selected'/(task['id']+'.json')
            atomic(BASE/'receipts'/result.name,dict(status='COMPLETE',time=stamp(),rank=a.rank,
                    task=task,result_path=str(result.relative_to(ROOT)),result_sha256=sha(result)))


def node(a):
    setup(f'vlm_repair/late_selection/node{a.node}');verify_execution()
    import psutil
    assert os.cpu_count()>=160 and psutil.virtual_memory().available>128*1024**3
    folder=(ROOT/a.launch).resolve();assert folder.is_relative_to(VOUT/'resume')
    folder.mkdir(parents=True,exist_ok=False)
    ranks=list(range(a.node*a.workers,(a.node+1)*a.workers))
    atomic(folder/'PREFLIGHT.json',dict(status='PASS',time=stamp(),node=a.node,ranks=ranks,
            threads=a.threads,no_model_loaded=True,waits_for_full_grid=True))
    children=[];streams=[]
    for r in ranks:
        stream=(folder/f'rank{r:03d}.log').open('a');streams.append(stream)
        command=[sys.executable,'-u','-B',str(Path(__file__).resolve()),'worker',
                 '--rank',str(r),'--threads',str(a.threads)]
        children.append(subprocess.Popen(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                preexec_fn=lambda:os.nice(10)))
    while True:
        bad=[dict(rank=r,returncode=p.poll()) for r,p in zip(ranks,children) if p.poll() is not None]
        assert not bad,bad
        atomic(folder/'STATUS.json',dict(time=stamp(),node=a.node,
                workers={r:p.pid for r,p in zip(ranks,children)},no_gpu_worker_created=True))
        time.sleep(30)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['controller','node','worker','pool'])
    p.add_argument('--node',type=int,choices=[0,1]);p.add_argument('--rank',type=int)
    p.add_argument('--workers',type=int,default=16);p.add_argument('--threads',type=int,default=2)
    p.add_argument('--launch');a=p.parse_args()
    try:
        DEST.mkdir(exist_ok=True)
        pool() if a.mode=='pool' else globals()[a.mode](a)
    except BaseException as exc:
        # Wake the agent without aborting unrelated frozen model controllers.
        atomic(DEST/'failures'/f'{a.mode}_{a.node}_{a.rank}.json',
                dict(status='FAILED',time=stamp(),error=repr(exc),traceback=traceback.format_exc()))
        raise


