"""Source paths are relocated in memory; frozen files retain their SHA256."""
from __future__ import annotations
import gzip
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
BATCHES = ('1016-rl_representation_analysis', '1018-representation_repair_batch2',
           '1021-representation_repair_batch3', '1021-representation_distillation_batch4')

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8<<20), b''):h.update(block)
    return h.hexdigest()

def write_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    temporary.replace(path)

def inside(root, relative):
    root=Path(root).resolve();path=(root/relative).resolve()
    if not path.is_relative_to(root):raise ValueError('Path escapes the destination: '+str(relative))
    return path

def materialize(workspace, verify=True):
    workspace=Path(workspace).expanduser().resolve()
    if workspace==REPO or workspace.is_relative_to(REPO/'research_snapshot'):
        raise ValueError('Use a separate writable workspace')
    index=json.loads((REPO/'research_snapshot/INDEX.json').read_text())
    for item in index['files']:
        if item['role'].startswith('historical_'):continue
        source=inside(REPO,item['path']);dest=inside(workspace,item['workspace_path'])
        if verify and sha(source)!=item['stored_sha256']:raise ValueError('Export checksum mismatch: '+str(source))
        if dest.exists():
            if sha(dest)!=item['sha256']:raise ValueError('Existing frozen file differs: '+str(dest))
            continue
        dest.parent.mkdir(parents=True,exist_ok=True)
        opener=gzip.open if item['gzip'] else open
        with opener(source,'rb') as inp, dest.open('wb') as out:shutil.copyfileobj(inp,out,8<<20)
        if sha(dest)!=item['sha256']:raise ValueError('Installed checksum mismatch: '+str(dest))
    upstream=workspace/BATCHES[0]/'code/upstream'
    upstream.parent.mkdir(parents=True,exist_ok=True)
    if not upstream.exists():upstream.symlink_to(REPO/'vendor/upstream',target_is_directory=True)
    write_json(workspace/'PORTABLE_WORKSPACE.json',dict(schema=1,source_index_sha256=sha(REPO/'research_snapshot/INDEX.json')))
    return workspace

class Runtime:
    def __init__(self, paths, workspace):
        self.paths_file=Path(paths).expanduser().resolve()
        self.paths=json.loads(self.paths_file.read_text())
        self.workspace=Path(workspace).expanduser().resolve()
        if not (self.workspace/'PORTABLE_WORKSPACE.json').exists():raise ValueError('Run continuation.prepare first')
        original='/mnt/workspace/ReCogDrive'
        self.prefixes={original:str(self.workspace),
            '/mnt/data_and_weight/WM_Group/sjc_workspace/ReCogDrive':str(self.workspace),
            '/mnt/data/navsim/maps':self.paths['maps'],
            '/mnt/yehr_workspace/ReCogDrive/ReCogDrive/recogdrive/ReCogDrive-2B-RL/ReCogDrive_Diffusion_Planner_2B_RL.ckpt':self.paths['checkpoint'],
            '/mnt/yehr_workspace/ReCogDrive/ReCogDrive/recogdrive/ReCogDrive-VLM-2B':self.paths['vlm'],
            '/mnt/yehr_workspace/ReCogDrive/ReCogDrive/recogdrive/navsim/exp/metric_cache_train':self.paths['navtrain_metric'],
            '/mnt/yehr_workspace/ReCogDrive/ReCogDrive/recogdrive/navsim/exp/metric_cache':self.paths['navtest_metric']}
        for cohort,split in [('navtrain','trainval'),('navtest','test')]:
            for kind,folder in [('logs',split+'_navsim_logs'),('sensor',split+'_sensor_blobs')]:
                self.prefixes['/mnt/data/navsim/'+folder]=self.paths[cohort+'_'+kind]
        self.prefixes.update(self.paths.get('extra_prefixes',{}))
        self.prefixes=sorted(self.prefixes.items(),key=lambda x:-len(x[0]))

    def relocate(self,value):
        if isinstance(value,str):
            for old,new in self.prefixes:
                if value==old or value.startswith(old+'/'):return str(Path(new).expanduser())+value[len(old):]
            return value
        if isinstance(value,list):return [self.relocate(v) for v in value]
        if isinstance(value,dict):return {self.relocate(k):self.relocate(v) for k,v in value.items()}
        return value

    def read(self,path):
        return self.relocate(json.loads(Path(self.relocate(str(path))).read_text()))

    def hash(self,path):return sha(self.relocate(str(path)))

    def setup(self,name,threads=1):
        root=self.workspace/'.runtime'/name;root.mkdir(parents=True,exist_ok=True)
        for key in ['HF_HOME','HF_MODULES_CACHE','TRANSFORMERS_CACHE','TORCH_HOME','XDG_CACHE_HOME','MPLCONFIGDIR',
                    'NUMBA_CACHE_DIR','TORCHINDUCTOR_CACHE_DIR','TRITON_CACHE_DIR','TORCH_EXTENSIONS_DIR']:
            path=root/key.lower();path.mkdir(exist_ok=True);os.environ[key]=str(path)
        short=Path(os.environ.get('RECOGDRIVE_TMP_ROOT','/tmp'))/('recogdrive-'+hashlib.sha256(str(self.workspace).encode()).hexdigest()[:12])
        short.mkdir(parents=True,exist_ok=True);os.environ['TMPDIR']=str(short);tempfile.tempdir=str(short)
        for key in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[key]=str(threads)
        os.environ.update(PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
            TOKENIZERS_PARALLELISM='false',NUPLAN_MAPS_ROOT=self.paths['maps'],NUPLAN_MAP_VERSION='nuplan-maps-v1.0')

    def bootstrap(self):
        sys.dont_write_bytecode=True
        for batch in BATCHES:sys.path.insert(0,str(self.workspace/batch/'code'))
        sys.path.insert(0,str(REPO/'vendor/upstream'))
        for name in ['common','r2_common','r3_common','d4_common','d4_common_v2']:
            module=importlib.import_module(name)
            module.read=self.read;module.sha=self.hash;module.setup=self.setup
            if name=='common':module.UPSTREAM=REPO/'vendor/upstream'
        self.setup('portable')
        import common
        common.compatibility()
        return self
