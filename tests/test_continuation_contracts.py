import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from continuation.artifacts import pack_volume,install_volume
from continuation.layout import BATCHES,REPO,Runtime,inside,materialize,sha,write_json
from continuation.migrate_checkpoint import exposure_for_ranks,remap_state
from continuation.summarize import aggregate,paired_scores,read_complete,session_interval

class EvaluationContracts(unittest.TestCase):
    def fixture(self):
        identity=dict(noises='0,1')
        def score(value,safe=1):
            return dict(score=value,no_at_fault_collisions=safe,
                drivable_area_compliance=1,time_to_collision_within_bound=1)
        record=dict(identity=identity,token='a',session='session1',subset='validation',pool='P',records=[
            dict(kind='Base',seed_index=0,score=score(1)),dict(kind='student',seed_index=0,score=score(.5,0)),
            dict(kind='Base',seed_index=1,score=score(1)),dict(kind='student',seed_index=1,score=score(.8))])
        return identity,record

    def test_scene_draws_are_aggregated_and_safety_is_paired(self):
        identity,record=self.fixture();summary=aggregate([record],identity)
        self.assertAlmostEqual(summary['gain'],-35)
        self.assertEqual(summary['Base_over_90_harmed_scenes'],1)
        self.assertEqual(summary['safety_events']['no_at_fault_collisions'],dict(new=1,removed=0))
        self.assertEqual(summary['cases'],1)
        self.assertEqual(session_interval([3,3],['a','b']),[3,3])

    def test_reordered_or_missing_noise_draws_are_rejected(self):
        identity,record=self.fixture();record['records'][3]['seed_index']=0
        with self.assertRaises(ValueError):paired_scores(record,identity)

    def test_complete_cases_without_all_shard_receipts_are_rejected(self):
        identity,record=self.fixture()
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);write_json(root/'FROZEN_MODEL.json',identity)
            write_json(root/'cases/a.json',record)
            write_json(root/'COMPLETE_rank000.json',dict(status='COMPLETE_TARGET_BACKEND_EVALUATION_SHARD',
                identity=identity,rank=0,world_size=2,cases=1))
            with self.assertRaises(ValueError):read_complete(root)

class ArchiveContracts(unittest.TestCase):
    def test_roundtrip_is_verified_and_idempotent(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);(root/'source').mkdir();source=root/'source'/'a.bin';source.write_bytes(b'fixed\x00target'*100)
            item=dict(source_path='a.bin',path='batch/cases/a.bin',bytes=source.stat().st_size,sha256=sha(source))
            receipt=pack_volume(root/'part.tar',[item],root/'source','test-part')
            self.assertEqual(install_volume(root/'part.tar',root/'installed',receipt['sha256']),1)
            self.assertEqual((root/'installed/batch/cases/a.bin').read_bytes(),source.read_bytes())
            self.assertEqual(install_volume(root/'part.tar',root/'installed',receipt['sha256']),1)
            (root/'installed/batch/cases/a.bin').write_bytes(b'different')
            with self.assertRaises(ValueError):install_volume(root/'part.tar',root/'installed',receipt['sha256'])

    def test_corrupt_source_never_gets_a_completion_receipt(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);(root/'a').write_bytes(b'changed')
            item=dict(source_path='a',path='a',bytes=7,sha256='0'*64)
            with self.assertRaises(ValueError):pack_volume(root/'part.tar',[item],root,'bad')
            self.assertFalse((root/'part.tar.json').exists())

    def test_path_traversal_and_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory)
            for name,kind in [('../escape',tarfile.REGTYPE),('link',tarfile.SYMTYPE)]:
                path=root/'hostile.tar'
                with tarfile.open(path,'w')as archive:
                    payload=json.dumps(dict(id='hostile',files=[dict(path=name,bytes=1,sha256=hashlib.sha256(b'x').hexdigest())])).encode()
                    info=tarfile.TarInfo('VOLUME.json');info.size=len(payload);archive.addfile(info,io.BytesIO(payload))
                    info=tarfile.TarInfo(name);info.type=kind;info.size=1 if kind==tarfile.REGTYPE else 0;info.linkname='/tmp'
                    archive.addfile(info,io.BytesIO(b'x')if info.size else None)
                with self.assertRaises(ValueError):install_volume(path,root/'out',sha(path))
            self.assertFalse((root/'escape').exists())

class RelocationContracts(unittest.TestCase):
    def paths(self,root):
        return {name:str(root/name)for name in ['checkpoint','vlm','maps','navtrain_logs','navtrain_sensor',
            'navtrain_metric','navtest_logs','navtest_sensor','navtest_metric']}

    def test_hashes_remain_raw_while_json_paths_are_relocated(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);write_json(root/'PORTABLE_WORKSPACE.json',{})
            write_json(root/'paths.json',self.paths(root));runtime=Runtime(root/'paths.json',root)
            source=dict(raw_path='/mnt/data/navsim/trainval_navsim_logs/trainval/log.pkl',
                root='/mnt/workspace/ReCogDrive/'+BATCHES[2],metric_cache='/mnt/yehr_workspace/ReCogDrive/ReCogDrive/recogdrive/navsim/exp/metric_cache_train/log/unknown/token/metric_cache.pkl',
                sha256='abc')
            path=root/'frozen.json';write_json(path,source);before=sha(path);loaded=runtime.read(path)
            self.assertEqual(sha(path),before);self.assertEqual(runtime.hash(path),before)
            self.assertEqual(loaded['sha256'],'abc')
            self.assertEqual(loaded['raw_path'],str(root/'navtrain_logs/trainval/log.pkl'))
            self.assertEqual(loaded['root'],str(root/BATCHES[2]))
            self.assertEqual(loaded['metric_cache'],str(root/'navtrain_metric/log/unknown/token/metric_cache.pkl'))

    def test_materialize_preserves_fingerprints_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);repo=root/'repo';(repo/'research_snapshot').mkdir(parents=True)
            (repo/'vendor/upstream').mkdir(parents=True);data=b'{"frozen": true}\n';stored=repo/'research_snapshot/x.json.gz'
            stored.write_bytes(gzip.compress(data,mtime=0));relative=BATCHES[0]+'/configs/x.json'
            write_json(repo/'research_snapshot/INDEX.json',dict(files=[dict(path='research_snapshot/x.json.gz',workspace_path=relative,
                sha256=hashlib.sha256(data).hexdigest(),stored_sha256=sha(stored),gzip=True,role='configuration')]))
            with patch('continuation.layout.REPO',repo):
                materialize(root/'work');self.assertEqual((root/'work'/relative).read_bytes(),data)
                materialize(root/'work');(root/'work'/relative).write_text('changed')
                with self.assertRaises(ValueError):materialize(root/'work')

class RankMigrationContracts(unittest.TestCase):
    def fixture(self):
        config=dict(global_batch_size=64,data_seed=2026102102)
        indices=list(range(96));scenes=[dict(pool='I'if i%3 else 'P')for i in indices]
        return config,indices,scenes

    def test_16_to_8_preserves_optimizer_and_global_sample_prefix(self):
        config,indices,scenes=self.fixture();optimizer=object();weights=object()
        state=dict(epoch=1,next_micro=4,global_step=3,optimizer=optimizer,trainable=weights,
            random_states=[dict(rank=i,cpu=b'cpu',cuda=b'ppu',exposure=12,pools={})for i in range(16)])
        new=remap_state(state,config,'new',indices,scenes,8)
        self.assertIs(new['optimizer'],optimizer);self.assertIs(new['trainable'],weights)
        self.assertEqual(new['next_micro'],8);self.assertEqual(sum(v['exposure']for v in new['random_states']),192)
        self.assertEqual(sum(sum(v['pools'].values())for v in new['random_states']),192)
        old=exposure_for_ranks(config,indices,scenes,1,4,16)
        self.assertEqual({pool:sum(v['pools'].get(pool,0)for v in old)for pool in ['I','P']},
            {pool:sum(v['pools'].get(pool,0)for v in new['random_states'])for pool in ['I','P']})
        self.assertEqual(state['next_micro'],4)

    def test_epoch_boundary_has_no_extra_epoch_exposure(self):
        config,indices,scenes=self.fixture();counts=exposure_for_ranks(config,indices,scenes,2,0,8)
        self.assertEqual(sum(x['exposure']for x in counts),256)

    def test_uncommitted_microbatch_cannot_be_migrated(self):
        config,indices,scenes=self.fixture()
        with self.assertRaises(ValueError):remap_state(dict(epoch=0,next_micro=1,global_step=0,random_states=[{}]*16),config,'x',indices,scenes,8)

class FrozenResearchContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index=json.loads((REPO/'research_snapshot/INDEX.json').read_text())
        cls.by_path={v['workspace_path']:v for v in cls.index['files']}
    def load(self,relative):
        item=self.by_path[relative];path=REPO/item['path'];opener=gzip.open if item['gzip']else open
        with opener(path,'rb')as stream:data=stream.read()
        self.assertEqual(hashlib.sha256(data).hexdigest(),item['sha256'])
        return json.loads(data)

    def test_frozen_training_split_and_paired_gain_labels(self):
        rows=self.load(BATCHES[3]+'/manifests/R2_TRAINING_SCENES_V2.json')
        train=self.load(BATCHES[3]+'/manifests/TRAIN_INDICES_V2.json')
        dev=self.load(BATCHES[3]+'/manifests/DEVELOPMENT_512_V1.json')
        self.assertEqual(len(rows),103288);self.assertEqual(len(train),85339);self.assertEqual(len(dev),512)
        self.assertFalse(set(train)&set(dev));self.assertEqual(len(set(train)),len(train))
        for i in train:self.assertEqual(rows[i]['subset'],'exploration');self.assertIn(rows[i]['pool'],['I','P'])
        for i in dev:self.assertEqual(rows[i]['subset'],'validation')
        self.assertEqual(rows[61156]['pool'],'E')
        for row in rows:
            gain=math.fsum(t-b for t,b in zip(row['teacher_scores'],row['Base_scores']))/5
            expected='I'if gain>0 else 'P'if math.fsum(row['Base_scores'])/5>.9 else 'E'
            self.assertEqual(row['pool'],expected)

    def test_main_comparison_retains_actual_loss_weights_and_budget(self):
        configs={g:self.load(BATCHES[3]+f'/configs/distillation_main_v4/{g}.json')for g in ['H','T','HT']}
        for config in configs.values():
            self.assertEqual(config['global_batch_size'],64);self.assertEqual(config['epochs'],5)
            self.assertFalse(config['GT_used']);self.assertEqual(config['lora_rank'],16)
        self.assertEqual(configs['H']['lambda_T'],0);self.assertEqual(configs['T']['lambda_H'],0)
        self.assertEqual(configs['T']['lambda_T'],1);self.assertAlmostEqual(configs['HT']['lambda_T'],80.21022962075446)

    def test_all_42_candidate_parameters_are_included_with_exact_hashes(self):
        pack=self.load(BATCHES[2]+'/manifests/first42_v1.json')
        self.assertEqual(len(pack['entries']),42)
        for original,expected in pack['assets'].items():
            relative=original.split('/ReCogDrive/',1)[1];item=self.by_path[relative]
            self.assertEqual(item['sha256'],expected);self.assertEqual(sha(REPO/item['path']),expected)

    def test_rebuilt_R2_reference_targets_keep_the_same_selection_identity(self):
        path=REPO/'reference/continuation_20261022/r2/INDEX.json';index=json.loads(path.read_text())
        item=self.by_path[BATCHES[3]+'/manifests/R2_TRAINING_SCENES_V2.json']
        self.assertEqual(index['source_scene_manifest_sha256'],item['sha256'])
        item=index['interface_metadata'];self.assertEqual(sha(REPO/item['path']),item['sha256'])
        with gzip.open(REPO/item['path'],'rt')as stream:metadata=json.load(stream)
        self.assertEqual(len(metadata),103288)
        for i,row in enumerate(metadata):self.assertEqual(row['global_index'],i);self.assertGreaterEqual(row['full_tokens'],2800)
        for item in index['trajectory_blocks']:self.assertEqual(sha(REPO/item['path']),item['sha256'])

if __name__=='__main__':unittest.main()
