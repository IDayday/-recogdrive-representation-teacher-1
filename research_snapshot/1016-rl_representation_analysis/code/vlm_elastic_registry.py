"""Task-private, credential-free identities for a variable number of DLC cards."""
from common import *
import contextlib,fcntl
from vlm_core import VOUT
from repair_queue_v2 import atomic_unique as atomic

DEST=VOUT/'elastic_v1'
BASE=ROOT/'runs/vlm_global_refine_20261016_v5'

@contextlib.contextmanager
def locked():
    DEST.mkdir(parents=True,exist_ok=True)
    with (DEST/'registry.lock').open('a+') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX);yield

def initialize(source):
    source=(ROOT/source).resolve();cloud=read(source)
    with locked():
        path=DEST/'REGISTRY.json'
        if path.exists():return read(path)
        nodes=[];cursor=0
        for index,job in enumerate(cloud['jobs']):
            proof=BASE/f'node{index}/SMOKE_PASS.json';cards=read(proof)['cards']
            nodes.append(dict(id=f'legacy_{index}',kind='legacy',job=job,
                gpu_ranks=list(range(cursor,cursor+cards)),cards=cards,
                source_cloud=str(source.relative_to(ROOT)),smoke_proof=str(proof.relative_to(ROOT))))
            cursor+=cards
        result=dict(schema=1,time=stamp(),run=BASE.name,nodes=nodes,
            next_gpu_rank=cursor,next_cpu_node=100,minimum_new_job_minutes=4320,
            retention='No automatic release. User consent required after completion.')
        atomic(path,result);return result

def register(profile_path,devices,cpu_workers=80,cpu_threads=2):
    assert devices and len(set(devices))==len(devices) and min(devices)>=0
    assert 1<=cpu_workers<=256 and 1<=cpu_threads<=8
    profile_path=(ROOT/profile_path).resolve();assert profile_path.is_relative_to(ROOT)
    profile=read(profile_path);assert profile['region'] and profile['workspace_id'] and profile['quota_id']
    with locked():
        r=read(DEST/'REGISTRY.json');index=len(r['nodes']);ident=f'elastic_{index:03d}'
        folder=DEST/'nodes'/ident;folder.mkdir(parents=True,exist_ok=False)
        ranks=list(range(r['next_gpu_rank'],r['next_gpu_rank']+len(devices)))
        cpu_node=r['next_cpu_node'];config=dict(id=ident,kind='elastic',time=stamp(),
            profile_path=str(profile_path.relative_to(ROOT)),profile_sha256=sha(profile_path),
            devices=devices,cards=len(devices),gpu_ranks=ranks,cpu_node=cpu_node,
            cpu_rank_base=cpu_node*1024,cpu_workers=cpu_workers,cpu_threads=cpu_threads,
            max_running_minutes=4320,run=BASE.name,folder=str(folder.relative_to(ROOT)))
        atomic(folder/'CONFIG.json',config)
        r['nodes'].append(dict(id=ident,kind='elastic',config=str((folder/'CONFIG.json').relative_to(ROOT)),
            config_sha256=sha(folder/'CONFIG.json'),gpu_ranks=ranks,cards=len(devices)))
        r.update(time=stamp(),next_gpu_rank=ranks[-1]+1,next_cpu_node=cpu_node+1)
        atomic(DEST/'REGISTRY.json',r);return config

def configuration(ident):
    r=read(DEST/'REGISTRY.json');entry=next(n for n in r['nodes'] if n['id']==ident)
    assert entry['kind']=='elastic';p=ROOT/entry['config'];assert sha(p)==entry['config_sha256']
    return read(p)

def allowed_ranks():
    return {rank for node in read(DEST/'REGISTRY.json')['nodes'] for rank in node['gpu_ranks']}
