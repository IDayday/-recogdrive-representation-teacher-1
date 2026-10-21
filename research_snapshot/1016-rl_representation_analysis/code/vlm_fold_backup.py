"""Checkpoint CPU CV by fold, preserving the running frozen whole-cell scans.

Reuses the exact original directions and scan aggregation. Results stay in an
independent directory. Adoption is forbidden until both original jobs terminate;
any already committed original result always takes precedence.
"""
from common import *
import argparse,subprocess,traceback,shutil
import numpy as np
from threadpoolctl import threadpool_limits
from vlm_core import VOUT
from vlm_scan import metadata,moment,subtract,save_npz
from vlm_space import directions,configs
from repair_queue_v2 import claim,append,atomic_unique as atomic
OUT=VOUT/'fold_backup';BASE=ROOT/'runs/vlm_fold_backup_20261017_v1'
CONTROL='interface_post__valid_mean'
CELLS=[CONTROL,'bridge_pre__patch_mean','bridge_0__patch_mean']

def fingerprint(mom):
    h=hashlib.sha256()
    for n,s,g in mom:
        h.update(np.asarray(n,dtype=np.int64).tobytes())
        for a in [s,g]:h.update(memoryview(np.ascontiguousarray(a,dtype=np.float64)).cast('B'))
    return h.hexdigest()

def unpack(z):return [(int(z['ns']),np.array(z['ss']),np.array(z['gs'])),(int(z['nf']),np.array(z['sf']),np.array(z['gf']))]

def prepare():
    assert not (OUT/'PROTOCOL.json').exists();reference=read(VOUT/'scan/results'/(CONTROL+'.json'));assert reference['status']=='COMPLETE'
    assert digest(configs())==digest(read(VOUT/'scan/CONFIGS.json'))
    for cell in CELLS:
        p=VOUT/'cells'/(cell+'.json');d=read(p);assert sha(ROOT/d['path'])==d['sha256'];target=OUT/'cells'/p.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    atomic(OUT/'PROTOCOL.json',dict(status='FROZEN_BEFORE_BACKUP',time=stamp(),cells=CELLS,control=CONTROL,
        original_math_sha256={'code/'+p:sha(ROOT/'code'/p) for p in ['vlm_scan.py','vlm_space.py']},code_sha256=sha(Path(__file__)),threads=4,
        proof_rule='Control full aggregate must match original status/rank and nondegenerate metrics before any 4096-direction task starts.',
        no_current_process_stopped=True,no_original_output_modified=True,
        adoption='Only after both old jobs and pods terminate; always prefer an original committed result, never choose by score.',
        source_reference_sha256=sha(VOUT/'scan/results'/(CONTROL+'.json'))))
    tasks=[dict(id=cell+'__held'+str(k),kind='held',cell=cell,fold=k) for cell in CELLS for k in range(5)];append(BASE,tasks)
    print('FOLD_BACKUP_PREPARED',len(tasks),flush=True)

def compute(task):
    cell=task['cell'];k=task['fold'];dest=OUT/'work'/cell
    if task['kind']=='held':
        path=dest/f'held{k}.npz'
        if path.exists():return dict(path=str(path.relative_to(ROOT)),sha256=sha(path))
        proof=read(OUT/'cells'/(cell+'.json'));x=np.load(ROOT/proof['path'],mmap_mode='r');rows,q,exp,fold,sessions,high=metadata();valid=np.isfinite(x[:,0]);masks=[exp&valid&(fold==k)&a for a in [q>.9,q<.7]];mom=[moment(x,a) for a in masks]
        h=save_npz(path,ns=mom[0][0],ss=mom[0][1],gs=mom[0][2],nf=mom[1][0],sf=mom[1][1],gf=mom[1][2],mask_s=np.asarray(hashlib.sha256(masks[0].tobytes()).hexdigest()),mask_f=np.asarray(hashlib.sha256(masks[1].tobytes()).hexdigest()))
        return dict(path=str(path.relative_to(ROOT)),sha256=h)
    path=dest/f'direction_c{task["centered"]}f{k}.npz'
    if path.exists():return dict(path=str(path.relative_to(ROOT)),sha256=sha(path))
    with np.load(dest/f'train{k}.npz') as z:mom=unpack(z)
    construction_seed=int(digest(dict(cell=cell,vlm_space_root=20261016))[:16],16);w,c,s,rank,degen,g=directions(mom,bool(task['centered']),construction_seed,return_geometry=True);assert g is not None
    # The unmodified scan uses only these geometry entries for energy/QDA.
    us,es,uf,ef,rs,rf,ms,mf,center,cov=g
    h=save_npz(path,w=w,center=c,status=s,ranks=rank,degenerate=degen,us128=us[:,:128],rs=rs,rf=rf,ms=ms,mf=mf,geometry_center=center,moment_fingerprint=np.asarray(fingerprint(mom)))
    return dict(path=str(path.relative_to(ROOT)),sha256=h)

def worker(a):
    setup(f'vlm_repair/fold_backup/rank{a.rank:03d}');p=read(OUT/'PROTOCOL.json');assert sha(Path(__file__))==p['code_sha256']
    for path,h in p['original_math_sha256'].items():assert sha(ROOT/path)==h,path
    with threadpool_limits(4):
        while True:
            task=claim(BASE,a.rank)
            if task is None:atomic(BASE/'workers'/f'rank{a.rank:03d}.json',dict(status='QUEUE_WAIT',time=stamp(),rank=a.rank));time.sleep(5);continue
            assert task!='CLOSED';atomic(BASE/'workers'/f'rank{a.rank:03d}.json',dict(status='COMPUTING',time=stamp(),rank=a.rank,task=task['id']));started=time.monotonic();out=compute(task)
            atomic(BASE/'receipts'/(task['id']+'.json'),dict(status='COMPLETE',time=stamp(),rank=a.rank,task=task,seconds=time.monotonic()-started,**out))

def prepare_train(cell):
    dest=OUT/'work'/cell;marker=dest/'TRAIN_READY.json'
    if marker.exists():return True
    if not all((BASE/'receipts'/(cell+'__held'+str(k)+'.json')).exists() for k in range(5)):return False
    held=[]
    for k in range(5):
        proof=read(BASE/'receipts'/(cell+'__held'+str(k)+'.json'));assert sha(ROOT/proof['path'])==proof['sha256']
        with np.load(ROOT/proof['path']) as z:held.append(unpack(z))
    totals=[tuple(sum(h[group][field] for h in held) for field in range(3)) for group in range(2)]
    for k in range(5):
        m=[subtract(t,h) for t,h in zip(totals,held[k])];save_npz(dest/f'train{k}.npz',ns=m[0][0],ss=m[0][1],gs=m[0][2],nf=m[1][0],sf=m[1][1],gf=m[1][2])
    atomic(marker,dict(status='PASS',time=stamp(),class_sizes=[int(t[0]) for t in totals]));return True

def aggregate(cell):
    import vlm_scan as module
    target=OUT/'scan/results'/(cell+'.json')
    if target.exists():return read(target)
    paths=[BASE/'receipts'/(cell+f'__c{cc}f{k}.json') for cc in [0,1] for k in range(5)]
    if not all(p.exists() for p in paths):return None
    cache={}
    for k in range(5):
        with np.load(OUT/'work'/cell/f'held{k}.npz') as z:
            m=unpack(z);cache[str(z['mask_s'].item())]=m[0];cache[str(z['mask_f'].item())]=m[1]
    counts={0:0,1:0};original=(module.VOUT,module.moment,module.directions)
    def cached_moment(x,mask):return cache[hashlib.sha256(mask.tobytes()).hexdigest()]
    def cached_direction(mom,centered,construction_seed,return_geometry=False):
        cc=int(centered);k=counts[cc];counts[cc]+=1;proof=read(BASE/'receipts'/(cell+f'__c{cc}f{k}.json'));assert sha(ROOT/proof['path'])==proof['sha256']
        with np.load(ROOT/proof['path']) as z:
            assert z['moment_fingerprint'].item()==fingerprint(mom)
            result=(np.array(z['w']),np.array(z['center']),np.array(z['status']),np.array(z['ranks']),np.array(z['degenerate']))
            g=(np.array(z['us128']),None,None,None,int(z['rs']),int(z['rf']),np.array(z['ms']),np.array(z['mf']),np.array(z['geometry_center']),None)
        return (*result,g) if return_geometry else result
    try:
        module.VOUT=OUT;module.moment=cached_moment;module.directions=cached_direction;result=module.scan(cell);assert counts=={0:5,1:5}
    finally:module.VOUT,module.moment,module.directions=original
    atomic(OUT/'completed'/(cell+'.json'),dict(status='PASS',time=stamp(),cell=cell,result_path=str(target.relative_to(ROOT)),result_sha256=sha(target),directions_checkpointed=10,original_aggregation_unmodified=True));return result

def compare_control():
    old=read(VOUT/'scan/results'/(CONTROL+'.json'));new=read(OUT/'scan/results'/(CONTROL+'.json'))
    with np.load(ROOT/old['array_path']) as a,np.load(ROOT/new['array_path']) as b:
        for key in ['status','ranks','evaluation_indices','fold_ids']:assert np.array_equal(a[key],b[key]),key
        assert np.array_equal(a['cutoff_degenerate'],b['cutoff_degenerate'])
        valid=(a['status']==0).all(1)&~a['cutoff_degenerate'].any(1);differences=[]
        for cc in [0,1]:
            av=a['metrics'][cc,:,valid[cc],:];bv=b['metrics'][cc,:,valid[cc],:];assert np.allclose(av,bv,rtol=1e-6,atol=1e-6,equal_nan=True);differences.append(float(np.nanmax(np.abs(av-bv))))
        assert np.allclose(a['secondary_metrics'],b['secondary_metrics'],rtol=1e-6,atol=1e-6,equal_nan=True)
    atomic(OUT/'ENGINEERING_PASS.json',dict(status='PASS',time=stamp(),control=CONTROL,nondegenerate_metric_max_abs_difference=differences,status_ranks_indices_and_degeneracy_exact=True,original_result_unchanged=True))

def controller():
    setup('vlm_repair/fold_backup/controller')
    with threadpool_limits(4):
        while True:
            for cell in CELLS:
                if not prepare_train(cell):continue
                if cell!=CONTROL and not (OUT/'ENGINEERING_PASS.json').exists():continue
                name=OUT/'work'/cell/'DIRECTIONS_APPENDED.json'
                if not name.exists():
                    tasks=[dict(id=cell+f'__c{cc}f{k}',kind='direction',cell=cell,centered=cc,fold=k) for cc in [0,1] for k in range(5)];append(BASE,tasks);atomic(name,dict(status='PASS',time=stamp(),tasks=10))
                result=aggregate(cell)
                if result is not None and cell==CONTROL and not (OUT/'ENGINEERING_PASS.json').exists():compare_control()
            if all((OUT/'completed'/(cell+'.json')).exists() for cell in CELLS):atomic(OUT/'ALL_BACKUPS_COMPLETE.json',dict(status='PASS',time=stamp(),cells=CELLS,original_processes_and_outputs_untouched=True));return
            time.sleep(10)

def node(a):
    setup(f'vlm_repair/fold_backup/node{a.node}')
    import psutil
    assert os.cpu_count()>=160 and psutil.virtual_memory().available>128*1024**3
    folder=BASE/f'node{a.node}';folder.mkdir(parents=True,exist_ok=True);children=[];streams=[]
    for i in range(10):
        rank=a.node*10+i;stream=(folder/f'rank{rank:03d}.log').open('a');streams.append(stream);children.append(subprocess.Popen([sys.executable,'-u','-B',str(Path(__file__).resolve()),'worker','--rank',str(rank)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,preexec_fn=lambda:os.nice(10)))
    while True:
        bad=[dict(rank=a.node*10+i,returncode=p.returncode) for i,p in enumerate(children) if p.poll() is not None]
        if bad:raise RuntimeError(str(bad))
        atomic(folder/'STATUS.json',dict(status='RUNNING',time=stamp(),pids=[p.pid for p in children],low_priority=True));time.sleep(10)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','controller','node','worker']);p.add_argument('--node',type=int);p.add_argument('--rank',type=int);a=p.parse_args()
    try:prepare() if a.mode=='prepare' else controller() if a.mode=='controller' else globals()[a.mode](a)
    except BaseException as e:
        atomic(OUT/'failures'/(a.mode+'_'+str(a.node)+'_'+str(a.rank)+'.json'),dict(status='FAILED',time=stamp(),error=repr(e),traceback=traceback.format_exc()));raise
