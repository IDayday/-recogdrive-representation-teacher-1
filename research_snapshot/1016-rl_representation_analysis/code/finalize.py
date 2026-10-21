"""Full scene coverage, independent rescoring, and baseline delivery artifacts."""
from common import *
import argparse
import csv
import html
import subprocess
from collections import Counter
from worker import population
from coordinate import latest_records


def main():
    import numpy as np
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);args=parser.parse_args()
    setup(f'{args.run}/finalize')
    config=read(ROOT/'configs/baseline.json')
    base=ROOT/'runs'/args.run
    output=base/'delivery';output.mkdir(parents=True,exist_ok=True)
    assert read(base/'BOTH_NODE_SMOKE_PASS.json')['status']=='PASS'
    for node in range(2):
        assert read(base/f'node{node}/NODE_COMPLETE.json')['status']=='COMPLETE'
        assert all(code==0 for code in read(base/f'node{node}/formal/COMPLETE.json')['all_worker_exit_codes'])
    manifest=population();by_token={r['token']:r for r in manifest}
    records=[];chunks={}
    for rank in range(32):
        group=latest_records(args.run,'formal',rank)
        assert [r['token'] for r in group]==[r['token'] for r in manifest[rank::32]]
        for file in sorted((base/'formal'/f'rank{rank:03d}'/'chunks').glob('*.json')):
            chunks[str(file.relative_to(ROOT))]=sha(file)
        records.extend(group)
    assert len(records)==len(manifest)==len({r['token'] for r in records})
    assert {r['token'] for r in records}==set(by_token)
    for r in records:
        assert r['identity']==config['identity'] and r['checkpoint_sha256']==config['checkpoint_sha256']
        assert r['seed']==seed(r['token']) and r['seed_index']==0 and r['valid']
        assert np.asarray(r['trajectory']).shape==(8,3) and np.isfinite(r['trajectory']).all()
        assert r['quality']==quality(r['score']['score'])
    # Sample independently of favorable outcomes, and cover every populated quality group.
    selected={r['token']:r for r in sorted(records,key=lambda r:digest(r['token']))[:64]}
    for kind in ['failure','intermediate','high_quality']:
        subset=sorted([r for r in records if r['quality']==kind],key=lambda r:digest(r['token']))[:16]
        selected.update({r['token']:r for r in subset})
    tasks=[dict(token=r['token'],trajectory=r['trajectory'],metric_cache=by_token[r['token']]['metric_cache'],
                metric_sha256=r['metric_sha256'],scoring=config['scoring']) for r in selected.values()]
    atomic(output/'independent_rescore_request.json',tasks)
    subprocess.run([sys.executable,'-B',str(ROOT/'code/score.py'),str(output/'independent_rescore_request.json'),
                    str(output/'independent_rescore.json'),'--original-source',config['shared_reference_source']],
                   check=True,timeout=1200,cwd=ROOT)
    rescored=read(output/'independent_rescore.json')
    difference=0.
    for actual in rescored['results']:
        expected=selected[actual['token']]
        assert actual['reference_sha256']==expected['reference_sha256']
        difference=max(difference,max(abs(actual['score'][k]-expected['score'][k]) for k in actual['score']))
    assert difference==0,difference
    records.sort(key=lambda r:r['token'])
    fields=['token','log_name','seed','seed_index','rank','quality','pdms_100',*COMPONENTS,'feature_sha256','metric_sha256']
    with (output/'scores.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for r in records:
            writer.writerow({**{k:r[k] for k in ['token','log_name','seed','seed_index','rank','quality','feature_sha256','metric_sha256']},
                             'pdms_100':r['score']['score']*100,**{k:r['score'][k] for k in COMPONENTS}})
    failures=[r for r in records if r['quality']=='failure']
    with (output/'failure_pool.csv').open('w',newline='') as stream:
        fields=['token','log_name','seed','feature_dir','metric_cache','raw_path','frame_index','pdms_100']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for r in failures:writer.writerow({**{k:r[k] for k in fields if k!='pdms_100'},'pdms_100':r['score']['score']*100})
    scores=np.array([r['score']['score']*100 for r in records])
    summary=dict(status='COMPLETE',time=stamp(),run_id=args.run,identity=config['identity'],cohort='navtrain',
                 checkpoint_sha256=config['checkpoint_sha256'],samples=len(records),expected=len(manifest),
                 unique_tokens=len({r['token'] for r in records}),missing=0,duplicates=0,invalid=0,
                 mean_pdms_100=float(scores.mean()),quality_counts=dict(Counter(r['quality'] for r in records)),
                 component_means={k:float(np.mean([r['score'][k] for r in records])) for k in COMPONENTS},
                 collision_cases=sum(r['score']['no_at_fault_collisions']<1 for r in records),
                 offroad_cases=sum(r['score']['drivable_area_compliance']<1 for r in records),zero_score_cases=int((scores==0).sum()),
                 pdms_quantiles={str(q):float(np.quantile(scores,q)) for q in [0,.1,.25,.5,.75,.9,1]},
                 root_seed=20261008,seed_index=0,independent_rescore_samples=len(tasks),max_rescore_difference=difference,
                 all_32_workers_exited=True,no_training=True,test_cache_access=False,
                 artifacts=dict(scores=str(output/'scores.csv'),failure_pool=str(output/'failure_pool.csv'),
                   source=str(ROOT/'provenance/source_snapshot.json'),protocol=str(ROOT/'configs/baseline.json')))
    atomic(output/'summary.json',summary)
    atomic(output/'chunk_sha256.json',chunks)
    report=ROOT.parent/'doc/work-output/1016-rl_representation_analysis/baseline.html'
    report.parent.mkdir(parents=True,exist_ok=True)
    counts=summary['quality_counts']
    body=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>RL S0训练集基线</title>
<style>body{{max-width:1000px;margin:35px auto;font:16px/1.7 sans-serif;color:#222;padding:0 20px}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:8px;text-align:center}}pre{{white-space:pre-wrap;font-size:13px}}.left{{text-align:left}}</style>
<h1>ReCogDrive RL S0训练集基线</h1><p>记录时间：{html.escape(summary['time'])}。本轮完成冻结RL权重在navtrain上的自然推理与评分，为后续表征观察建立失败池。</p>
<p><strong>平均PDMS：{summary['mean_pdms_100']:.4f}</strong>；完整覆盖{len(records):,}个场景，缺失、重复与无效输出均为0。</p>
<table><tr><th>质量类别</th><th>阈值（百分制）</th><th>场景数</th></tr>
<tr><td>失败</td><td>&lt;70</td><td>{counts.get('failure',0):,}</td></tr>
<tr><td>中间质量</td><td>70至90（含端点）</td><td>{counts.get('intermediate',0):,}</td></tr>
<tr><td>高质量成功</td><td>&gt;90</td><td>{counts.get('high_quality',0):,}</td></tr></table>
<p>碰撞分项未满分：{summary['collision_cases']:,}；道路合规分项未满分：{summary['offroad_cases']:,}；零分：{summary['zero_score_cases']:,}。失败池已保存，GT高质量筛选及表征采集尚未开展。</p>
<p>两节点各16卡完成并行冒烟后进入正式分片。同一场景使用固定S0种子；{len(tasks)}条保存轨迹由原始NAVSIM入口独立重评分，全部分项最大差异为0，32个正式推理进程均已退出。</p>
<details><summary>协议、来源与适用范围</summary><p>使用官方RL规划头及冻结VLM特征；复用训练集特征缓存，不复用旧轨迹或成绩。规划头FP32、batch=1、eval/no_grad、随机DDIM五步，eta=1；S0根种子20261008，逐场景SHA256映射。GRPO训练旧策略参数不参与推理，其余活跃权重严格完整加载。</p>
<p>这是navtrain上的单次固定随机采样基线。没有训练或修复，没有读取navtest缓存或成绩，不据此声明测试集泛化或稳定失败概率。</p><pre>{html.escape(json.dumps(summary,ensure_ascii=False,indent=2))}</pre></details></html>'''
    report.write_text(body)
    atomic(base/'BASELINE_READY.json',dict(summary,report=str(report)))
    atomic(ROOT/'STATUS.json',dict(status='COMPLETE',time=stamp(),run_id=args.run,summary=str(output/'summary.json'),report=str(report)))
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
