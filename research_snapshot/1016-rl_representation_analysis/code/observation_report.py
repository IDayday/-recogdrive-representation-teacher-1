"""Standalone Chinese observation report with embedded scientific plots."""
from common import *
import argparse
import base64
import html
import io
import numpy as np


def number(x,d=3):
    return '—' if x is None else f'{x:.{d}f}'


def report(args):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    analysis=ROOT/'analysis/observation_v1';temporal=ROOT/'analysis/temporal_v1'
    complete=read(analysis/'COMPLETE.json');assert complete['status']=='COMPLETE'
    acceptance=read(ROOT/'runs'/args.run/'formal_acceptance/ACCEPTANCE.json')
    groups=read(temporal/'temporal_summary.json');primary=read(analysis/'primary_tests.json')
    secondary=read(analysis/'secondary_tests.json');meta=read(analysis/'cache/metadata.json')
    scores=np.load(analysis/'cache/scores.npy');valid=np.asarray([m['subset']=='validation' for m in meta])
    cells=[read(p) for p in sorted((analysis/'cells').glob('*.json'))]
    featured=read(analysis/'cells'/f'{complete["featured_cell"]}.json')
    narrative=read(ROOT/'analysis/observation_v1/report_conclusions.json')
    from observation_analysis import endpoint_mask
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    plots=analysis/'figures';plots.mkdir(exist_ok=True)
    images={}
    def save(fig,name):
        fig.savefig(plots/f'{name}.svg',bbox_inches='tight')
        buffer=io.BytesIO();fig.savefig(buffer,format='png',dpi=150,bbox_inches='tight');plt.close(fig)
        (plots/f'{name}.png').write_bytes(buffer.getvalue())
        images[name]='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()
    bystart=acceptance['by_start_t'];labels=[];bars=[]
    for r in bystart:
        combos={(v['failure_initialized'],v['gt_initialized']):v['count'] for v in r['combinations']}
        highfail=sum(n for (a,b),n in combos.items() if {a,b}=={'failure','high_quality'})
        bothfail=combos.get(('failure','failure'),0);bothhigh=combos.get(('high_quality','high_quality'),0)
        labels.append(str(r['start_t']));bars.append([highfail,bothfail,bothhigh,r['pairs']-highfail-bothfail-bothhigh])
    bars=np.asarray(bars,dtype=float);bars/=bars.sum(1,keepdims=True)
    fig,ax=plt.subplots(figsize=(7.4,3));bottom=np.zeros(len(labels))
    for i,(label,color) in enumerate([('Final high/fail pair','#167d8d'),('Both fail','#c34d56'),('Both high','#85b9aa'),('Contains middle','#d4c1a3')]):
        ax.bar(labels,bars[:,i]*100,bottom=bottom*100,color=color,label=label);bottom+=bars[:,i]
    ax.set(xlabel='Forward-noise start t (native schedule)',ylabel='All attempted pairs (%)',ylim=(0,100))
    ax.legend(ncols=4,fontsize=7.5,loc='upper center',bbox_to_anchor=(.5,1.22),frameon=False)
    fig.tight_layout();save(fig,'quality_coverage')
    layernames=['Action encoder','Condition fusion']+[f'DiT {i:02d}' for i in range(16)]+['DiT output (512D)']
    fig,axes=plt.subplots(1,2,figsize=(8.4,6.6),sharey=True)
    for g,ax in enumerate(axes):
        arr=np.full((19,8),np.nan)
        for r in primary:
            if r['noise_group']==g:arr[r['layer'],r['token']]=r['ordering']
        im=ax.imshow(arr,aspect='auto',vmin=.3,vmax=1,cmap='RdYlBu')
        ax.set(title=f'Held-out sessions, P{g}',xlabel='Action token',xticks=range(8))
        for r in primary:
            if r['noise_group']==g and r['q_fdr']<.05:ax.text(r['token'],r['layer'],'·',ha='center',va='center',color='black')
    axes[0].set_yticks(range(19),layernames);fig.colorbar(im,ax=axes,fraction=.04,pad=.04,label='Within-pair correct ordering (chance 0.5)')
    save(fig,'ordering_heatmap')
    fig,ax=plt.subplots(figsize=(7.4,3))
    for t0 in [20,40,60,80]:
        selected=[r for r in groups if r['start_t']==t0 and r['subset']=='validation' and r['mode']=='all' and r['noise_group']==0]
        r=selected[0]
        # Average tokens and common layers, preserving actually executed diffusion steps.
        rel=np.asarray(r['relative_representation_difference'])
        ax.plot(r['executed_timesteps'],rel.mean(axis=(1,2)),marker='o',label=f'start t={t0}')
    ax.invert_xaxis();ax.set(xlabel='Actually executed denoising step t',ylabel='Relative representation difference',yscale='log')
    ax.legend(ncols=2,fontsize=8);fig.tight_layout();save(fig,'temporal_convergence')
    fig,axes=plt.subplots(1,2,figsize=(8.2,3.5))
    data=np.load(analysis/'cells'/f'{complete["featured_cell"]}.npz',allow_pickle=False)
    for g,ax in enumerate(axes):
        coordinates=data[f'difference_coordinates_P{g}'];mask=valid&endpoint_mask(scores[g])
        for b,source,marker in [(0,'Base init','^'),(1,'GT init','o')]:
            for high,color in [(False,'#c34d56'),(True,'#167d8d')]:
                selected=mask&(scores[g,:,b]>.9 if high else scores[g,:,b]<.7)
                ax.scatter(coordinates[selected,b,0],coordinates[selected,b,1],s=14,marker=marker,color=color,alpha=.5,
                           label=f'{source}, {"high" if high else "fail"}')
        ax.set(title=f'{complete["featured_cell"]}, held-out P{g}',xlabel='Frozen difference SVD coordinate 1',ylabel='Coordinate 2')
    axes[1].legend(fontsize=7);fig.tight_layout();save(fig,'frozen_projection')
    fig,ax=plt.subplots(figsize=(7.4,3))
    for variant,label in [('paired_difference_svd','Paired difference SVD'),('paired_class_residual_pooled_centered','Paired residual, pooled center'),('global_class_residual_pooled_centered','Global residual, pooled center')]:
        values=[]
        for layer in range(19):
            rr=[r for r in primary+secondary if r['variant']==variant and r['noise_group']==0 and r['layer']==layer and r['ordering'] is not None]
            values.append(np.mean([r['ordering'] for r in rr]) if rr else np.nan)
        ax.plot(range(19),values,marker='.',label=label)
    ax.axhline(.5,color='grey',lw=.8,ls='--');ax.set(xlabel='Stage (0 action, 1 fusion, 2–17 DiT blocks, 18 output)',ylabel='Mean held-out pair ordering',ylim=(0,1.02))
    ax.legend(fontsize=8);fig.tight_layout();save(fig,'routes')
    # Quantities remain tied to final re-scored outputs; original GT score is a diagnostic only.
    qualityrows=[]
    for r in bystart:
        combos={(v['failure_initialized'],v['gt_initialized']):v['count'] for v in r['combinations']}
        qualityrows.append(f'<tr><td>{r["start_t"]}</td><td>{r["pairs"]:,}</td><td>{r["final_high_fail_pairs"]:,}</td><td>{r["reversed_orientation_pairs"]:,}</td><td>{combos.get(("failure","failure"),0):,}</td><td>{number(r["mean_pdms_100"]["baseline_failure"],2)}</td><td>{number(r["mean_pdms_100"]["GT"],2)}</td></tr>')
    counts=[]
    for subset,mask in [('探索集',~valid),('留出验证集',valid)]:
        for g in [0,1]:
            selected=mask&endpoint_mask(scores[g])
            counts.append(f'<tr><td>{subset}</td><td>P{g}</td><td>{int(mask.sum()):,}</td><td>{int(selected.sum()):,}</td><td>{len({meta[i]["session"] for i in np.flatnonzero(selected)})}</td></tr>')
    feature_rows=[]
    for v in featured['variants']:
        a,b=v['heldout']['0'],v['heldout']['1']
        feature_rows.append(f'<tr><td class="long">{html.escape(v["name"])}</td><td>{number(a["ordering"])}</td><td>{number(b["ordering"])}</td><td>{a["n"]}/{b["n"]}</td></tr>')
    continuous=featured['continuous_quality'];source_auc=featured['variants'][0]['heldout']
    mode_rows=[]
    for mode,label in [('collision','碰撞'),('offroad','出界'),('ttc','TTC')]:
        values={g:[r['by_baseline_mode'][mode] for r in primary if r['noise_group']==g and mode in r['by_baseline_mode']] for g in [0,1]}
        mode_rows.append(f'<tr><td>{label}</td><td>{values[0][0]["n"]}/{values[1][0]["n"]}</td><td>{number(float(np.mean([v["ordering"] for v in values[0]])))}</td><td>{number(float(np.mean([v["ordering"] for v in values[1]])))}</td></tr>')
    filename=Path(args.report).resolve();filename.parent.mkdir(parents=True,exist_ok=True)
    def fig(name,caption):return f'<figure><img src="{images[name]}" alt="{html.escape(caption)}"><figcaption>{html.escape(caption)}</figcaption></figure>'
    conclusions=''.join(f'<p>{html.escape(p)}</p>' for p in narrative['conclusions'])
    next_steps=''.join(f'<li>{html.escape(p)}</li>' for p in narrative['next_observations'])
    document=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RL基座失败样本配对去噪与表征观察</title><style>
body{{font-family:system-ui,"Microsoft YaHei",sans-serif;max-width:1050px;margin:32px auto;padding:0 20px;color:#25313b;line-height:1.75;background:#fff}}h1{{font-size:27px}}h2{{font-size:20px;margin-top:32px}}h3{{font-size:17px}}p{{margin:12px 0}}.muted,figcaption{{color:#62717a;font-size:13px}}.lead{{background:#f1f7f7;padding:14px 18px;border-left:4px solid #167d8d}}table{{width:100%;border-collapse:collapse;font-size:13px;margin:16px 0}}th,td{{border-bottom:1px solid #dce3e6;padding:9px 7px;text-align:center}}th{{background:#f3f6f8}}.long{{text-align:left}}img{{max-width:100%;height:auto}}figure{{margin:24px 0}}details{{border:1px solid #dce3e6;padding:12px 16px;margin:18px 0}}summary{{cursor:pointer;font-weight:600}}code{{font-size:12px;word-break:break-all}}li{{margin:8px 0}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.metric{{background:#f3f6f8;text-align:center;padding:12px}}.metric strong{{display:block;font-size:23px}}@media(max-width:650px){{.grid{{grid-template-columns:repeat(2,1fr)}}table{{font-size:11px}}}}
</style><body><h1>RL基座失败样本配对去噪与表征观察</h1><p class="muted">证据日期：2026-10-16 · ReCogDrive-2B-RL · navtrain · 只观察，不干预</p>
<div class="lead">{conclusions}</div>
<div class="grid"><div class="metric"><strong>2,288</strong>全部S0失败场景</div><div class="metric"><strong>45,760</strong>最终轨迹及重评分</div><div class="metric"><strong>432</strong>原始GT≤90仍保留</div><div class="metric"><strong>{complete['primary_family']}</strong>预定义主检验</div></div>
<h2>1. 质量门槛放在最终重评分后</h2><p>原始失败池只要求自然S0输出PDMS&lt;70，全部与同场景真实GT构造配对。原始GT分数仅记录：1,856条&gt;90，430条为70至90，2条&lt;70。<b>不提前按GT&gt;90筛除。</b>两分支共享观测、初始噪声和后续随机量，从对应时间表位置完整去噪后重新评分，再标记最终失败&lt;70、高质量&gt;90，中间质量含70与90。</p>
<p>每个场景比较五个原生起点t=0/20/40/60/80、两组独立配对噪声P0/P1。下面每个起点4,576对是2,288场景×2组噪声；重复噪声不算独立场景。两条都成功、两条都失败、反转和中间质量均保存。</p>
{fig('quality_coverage','全部尝试的最终质量组合；高低质量配对只占其中一部分，不能把其覆盖率当全体覆盖率。')}
<table><thead><tr><th>起点t</th><th>尝试对数</th><th>最终高／低配对</th><th>其中反转</th><th>两条都失败</th><th>失败初始化均分</th><th>GT初始化均分</th></tr></thead><tbody>{''.join(qualityrows)}</tbody></table>
<p class="muted">GT初始化续采是构造观察数据的方法，不能作为Base自然推理性能或修复成绩。真实GT与metric cache中的PDM参照轨迹分开记录。</p>
<h2>2. 同场景的差异在完整去噪中是否保留</h2><p>t=0对应原采样器最后一个原生去噪步，仍有非零前向噪声；每个起点都保存实际执行的层、token及去噪步。各噪声水平分开统计，不混成一个分离图。较重噪声的结果主要用于观察参考初始化差异能否在后续去噪中保留。</p>
{fig('temporal_convergence','留出会话P0：相同观测、配对噪声下，两分支相对表征差异沿实际去噪路径变化；共同384维阶段及动作token取均值。')}
<h2>3. 低维结构与留出验证</h2><p>低维主分析先看t=0；这是按预实验的最终质量覆盖决定，未按表征分离程度挑选。全部均值、投影、方向及连续分数探针只用探索集P0拟合，固定后检查留出会话P0和P1。对同场景最终高／低质量对做差分SVD，再检查配对类别子空间残差；随后独立检查全部最终高／低输出的类别子空间残差。可解释性不是本阶段门槛。</p>
<table><thead><tr><th>集合</th><th>噪声</th><th>全部场景</th><th>t=0最终高／低配对</th><th>对应独立采集会话</th></tr></thead><tbody>{''.join(counts)}</tbody></table>
{fig('ordering_heatmap','差分SVD k=8固定方向的同场景质量排序率；0.5为随机参考。点号表示主家族304项BH FDR<0.05。每个验证噪声组均独立列出。')}
<p>主家族中正向且FDR&lt;0.05的单元为{complete['primary_significant_positive']}/{complete['primary_family']}。推断按采集会话进行bootstrap及符号置乱，不把同场景多噪声输出当独立样本。完整效应量、区间、分失败模式及未显著结果均保留。</p>
<table><thead><tr><th>基线主要失败类型</th><th>验证配对数P0/P1</th><th>P0跨单元平均排序率</th><th>P1跨单元平均排序率</th></tr></thead><tbody>{''.join(mode_rows)}</tbody></table><p class="muted">此表为探索集共享方向在不同失败类型上的描述性表现，未分别拟合每类空间，也不等于已发现各类型共同机制。类型采用碰撞→出界→TTC→进度的优先归类，原始多标签安全分项仍完整保存。</p>
{fig('routes','三条低维路线的留出P0排序率，按动作token求均值；未中心化和公共中心化均单独保存，残差奇异值过小的方向不会归一化放大。')}
<details><summary>展示单元、二维图与连续质量关系</summary><p>展示单元{complete['featured_cell']}由探索P0差分前8维能量占比最高选定，未根据验证表现挑选。其前8维能量占比{number(featured['variants'][0]['top8_energy']*100,2)}%，相对全维差异RMS为{number(featured['variants'][0]['relative_paired_difference_rms'],5)}。二维图仅用于展示，不能替代留出统计。</p>
{fig('frozen_projection','固定探索集坐标下的留出高／低质量配对；颜色表示最终评分，点形表示初始化来源。')}
<table><thead><tr><th class="long">方法</th><th>验证P0排序率</th><th>验证P1排序率</th><th>配对数P0/P1</th></tr></thead><tbody>{''.join(feature_rows)}</tbody></table>
<p>保留中间质量和同类配对的连续PDMS差探针：P0留出Spearman={number(continuous['0']['spearman'])}，MAE={number(continuous['0']['mae_pdms_100'],2)}分（常数预测{number(continuous['0']['constant_mae_pdms_100'],2)}分）；P1对应为{number(continuous['1']['spearman'])}、{number(continuous['1']['mae_pdms_100'],2)}分（常数{number(continuous['1']['constant_mae_pdms_100'],2)}分）。探针是统计关联检查，不是模型修复。</p>
<p>同一冻结方向在GT初始化分支内部的最终高／低分类AUC：P0={number(source_auc['0']['within_source_auc']['GT'])}，P1={number(source_auc['1']['within_source_auc']['GT'])}。该诊断用于避免仅凭GT／模型来源差异判断失败机制；仍不能排除轨迹几何差异。</p></details>
<h2>4. 当前能支持什么，接下来继续观察什么</h2><p>{html.escape(narrative['interpretation_boundary'])}</p><ul>{next_steps}</ul>
<details><summary>方法、复核证据与完整产物</summary>
<p>模型权重SHA256：<code>23fb949b10387efeff87e093703d5faf41b61b9e5ead16d4076661e3c7c08a20</code>。使用冻结RL策略、FP32、batch=1、eval/no_grad、DDIM eta=1；同场景复用已核验的冻结条件特征。只观察动作编码、条件融合、16个DiT block和单独512维DiT输出，未分析上游视觉语言层。</p>
<p>前向加噪为sqrt(alpha_bar_t)×norm_odo(x0)+sqrt(1-alpha_bar_t)×epsilon，初始epsilon为未截断标准高斯。P0/P1根种子20261016，逐token/组/噪声分量SHA256映射到32位种子，CPU显式生成实际噪声并保存。后续各步使用原采样器的std下限、噪声截断和最终截断；从正确DDIM index接续，不能将任意加噪轨迹交给完整t=80起始循环。</p>
<p>原始GT物理坐标评分保留float64；模型输入与输出遵循FP32协议。最终评分采用相同训练集metric cache及官方NAVSIM评分，40×0.1s模拟，进度/TTC/舒适权重5/5/2。阈值按未四舍五入评分严格比较。</p>
<p>会话按log_name.rsplit('_',2)[0]成组，162个总体会话按种子20261016哈希固定80/20划分；失败池1850探索场景和438验证场景。所有层、token及k敏感性选择仅使用探索流程；主k=8，附带2/4/8/16/32维。SVD用float64的较小Gram矩阵精确特征分解，已与直接SVD实测核对。类别残差R=(I-U_success U_success^T)U_failure，再SVD；残差奇异值≤1e-6不生成方向。</p>
<p>16卡DLC作业<code>dlc1iu98gbsvgijx</code>。实际16卡冒烟640候选及全部张量与DSW精确一致；正式45,760候选、22,880个表征文件均覆盖、哈希、形状与有限值检查通过；{acceptance['original_source_independent_rescore_count']}条独立原始评分入口重算分项差异0。共享源码与资产未修改。未使用navtest，未训练修复模型，未干预表征。</p>
<p>计划：<code>1016-rl_representation_analysis/PLAN.md</code>；配对协议<code>configs/paired_formal_v1.json</code>；分析协议<code>configs/observation_analysis_v1.json</code>；原始配对<code>runs/gt_reference_full_20261016_v2/references.json</code>；正式运行<code>runs/{args.run}/</code>；逐cell基、坐标、谱与统计<code>analysis/observation_v1/cells/</code>；主／次检验<code>analysis/observation_v1/primary_tests.json</code>及<code>secondary_tests.json</code>；全部起点路径统计<code>analysis/temporal_v1/</code>。新代码均在任务code目录，不修改师兄源码。</p>
<p>本报告已检查数字、文件链接及HTML结构；未做浏览器渲染验收。</p></details>
<p class="muted">生成于{stamp()}。自然基线S0单独记录于baseline.html；本报告研究配对观察数据与表征，不将两类结果合并计分。</p></body></html>'''
    filename.write_text(document)
    atomic(analysis/'report_build.json',dict(status='COMPLETE',time=stamp(),report=str(filename),sha256=sha(filename),
            images=list(images),browser_render_verified=False))
    print(json.dumps(dict(report=str(filename),bytes=filename.stat().st_size,figures=len(images))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--report',required=True);a=p.parse_args()
    setup('observation_report');report(a)
