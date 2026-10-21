"""Rebuild NAVSIM v1 metric caches directly from existing logs and maps."""
import argparse
from pathlib import Path
import json
from continuation.layout import BATCHES,Runtime,write_json

def main(a):
    runtime=Runtime(a.paths,a.workspace).bootstrap()
    from vlm_core import raw_log
    from navsim.common.dataclasses import Scene,SensorConfig
    from navsim.planning.scenario_builder.navsim_scenario import NavSimScenario
    from navsim.planning.metric_caching.metric_cache_processor import MetricCacheProcessor
    path=runtime.workspace/(BATCHES[0]+'/manifests/natural_s0.json'if a.cohort=='navtrain'else BATCHES[1]+'/manifests/frozen_evaluation_test_rows_v1.json')
    rows=runtime.read(path);indices=list(range(len(rows)))
    if a.indices:indices=runtime.read(a.indices)
    if a.limit:indices=indices[:a.limit]
    if not 0<=a.rank<a.world_size:raise ValueError('Invalid cache shard')
    output=Path(runtime.paths[a.cohort+'_metric']).expanduser().resolve()
    processor=MetricCacheProcessor(cache_path=str(output),force_feature_computation=False)
    done=0
    for index in indices[a.rank::a.world_size]:
        row=rows[index];dest=Path(row['metric_cache'])
        if dest.is_file():done+=1;continue
        data=raw_log(row['raw_path']);i=int(row['frame_index'])
        frames=data[i-3:i+11]
        if len(frames)!=14 or data[i]['token']!=row['token']:raise ValueError('Raw scene/frame identity differs')
        scene=Scene.from_scene_dict_list(frames,None,num_history_frames=4,num_future_frames=10,sensor_config=SensorConfig.build_no_sensors())
        scenario=NavSimScenario(scene,map_root=runtime.paths['maps'],map_version='nuplan-maps-v1.0')
        processor.compute_metric_cache(scenario)
        if not dest.is_file():raise ValueError('NAVSIM cache layout differs from the configured manifest path: '+str(dest))
        done+=1
        if done%100==0:print(json.dumps(dict(cohort=a.cohort,rank=a.rank,completed=done)),flush=True)
    write_json(runtime.workspace/f'CACHE_COMPLETE_{a.cohort}_rank{a.rank:03d}.json',dict(status='COMPLETE',cohort=a.cohort,rank=a.rank,world_size=a.world_size,cases=done))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--paths',required=True);p.add_argument('--workspace',required=True)
    p.add_argument('--cohort',choices=['navtrain','navtest'],default='navtrain');p.add_argument('--rank',type=int,default=0)
    p.add_argument('--world-size',type=int,default=1);p.add_argument('--limit',type=int);p.add_argument('--indices')
    main(p.parse_args())
