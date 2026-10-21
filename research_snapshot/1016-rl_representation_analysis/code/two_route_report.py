"""One coherent report: route1 natural predictions; route2 failure/GT pairs."""
from common import *
import argparse
import base64
from collections import Counter
import html
import io
import numpy as np


def num(value,d=3):return '—' if value is None else f'{value:.{d}f}'


def build(args):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    r1=ROOT/'analysis/natural_route1_v1';r2=ROOT/'analysis/paired_route2_completion_v2'
    one=read(r1/'COMPLETE.json');two=read(r2/'COMPLETE.json');assert one['status']==two['status']=='COMPLETE'
    tests=read(r1/'tests.json');modes=read(r2/'mode_transfer_tests.json')
    paired=read(ROOT/'analysis/observation_v1/primary_tests.json');coverage=read(ROOT/'runs/paired_formal_20261016T0728Z/formal_acceptance/ACCEPTANCE.json')
    narrative=read(ROOT/'analysis/two_route_conclusions.json')
    meta=read(r1/'metadata.json');valid=np.asarray([r['subset']=='validation' for r in meta]);train=~valid
    q=np.load(r1/'scores.npy');labels=['Action encoder','Condition fusion']+[f'DiT {i:02d}' for i in range(16)]+['DiT output (512D)']
    figures=ROOT/'analysis/two_route_figures';figures.mkdir(exist_ok=True);images={}
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    def save(fig,name):
        fig.savefig(figures/f'{name}.svg',bbox_inches='tight')
        stream=io.BytesIO();fig.savefig(stream,format='png',dpi=150,bbox_inches='tight');plt.close(fig)
        (figures/f'{name}.png').write_bytes(stream.getvalue());images[name]='data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()
    fig,axes=plt.subplots(1,2,figsize=(8.3,6.6),sharey=True)
    for ci,name in enumerate(['uncentered','pooled_centered']):
        values=np.zeros((19,8))
        for r in tests:
            if r['step_t']==0 and r['centering']==name:values[r['layer'],r['token']]=r['failure_auc']
        im=axes[ci].imshow(values,vmin=.3,vmax=.95,aspect='auto',cmap='RdYlBu')
        axes[ci].set(title=name+', natural t=0',xlabel='Action token',xticks=range(8))
        for r in tests:
            if r['step_t']==0 and r['centering']==name and r['q_fdr']<.05 and r['within_session_failure_minus_success_mean']>0:
                axes[ci].text(r['token'],r['layer'],'·',ha='center',va='center',color='black')
    axes[0].set_yticks(range(19),labels);fig.colorbar(im,ax=axes,fraction=.04,pad=.04,label='Held-out natural failure AUROC')
    save(fig,'route1_natural_auc_t0')
    fig,axes=plt.subplots(1,2,figsize=(9,3.4))
    for t in [80,60,40,20,0]:
        vals=[];energies=[]
        for l in range(19):
            rows=[r for r in tests if r['step_t']==t and r['layer']==l and r['centering']=='pooled_centered']
            vals.append(np.mean([r['failure_auc'] for r in rows]));energies.append(np.mean([r['residual_energy'] for r in rows]))
        axes[0].plot(range(19),vals,label=f't={t}');axes[1].plot(range(19),energies,label=f't={t}')
    axes[0].axhline(.5,color='grey',ls='--',lw=.8);axes[0].set(xlabel='Stage',ylabel='Mean held-out natural failure AUROC')
    axes[1].set(xlabel='Stage',ylabel='Residual subspace energy (exploration fit)');axes[1].legend(fontsize=8,ncols=2)
    fig.tight_layout();save(fig,'route1_all_steps')
    # Fixed architectural illustration: final native step, last DiT block, action token 7.
    cell='step4_layer17_token7';info=read(r1/'cells'/f'{cell}.json')
    with np.load(r1/'cells'/f'{cell}.npz',allow_pickle=False) as b:
        coordinate=np.asarray(np.load(r1/'coordinates_hidden.npy',mmap_mode='r')[:,4,17,7,8:16],dtype=np.float64)
        center=b['pooled_centered_center']@b['pooled_centered_residual_basis'];wd=b['pooled_centered_direction_coords']
    z=coordinate-center;s=z@wd;select=valid&((q<.7)|(q>.9))
    edges=np.unique(np.quantile(s[train&((q<.7)|(q>.9))],np.linspace(0,1,33)))
    width=edges[-1]-edges[0]
    edges[0]=min(edges[0],float(s[select].min()))-.05*max(width,1e-6)
    edges[-1]=max(edges[-1],float(s[select].max()))+.05*max(width,1e-6)
    fig,axes=plt.subplots(1,3,figsize=(11,3.1))
    for label,mask,color in [('Natural success',valid&(q>.9),'#167d8d'),('Natural failure',valid&(q<.7),'#c34d56')]:
        axes[0].hist(s[mask],bins=edges,density=True,histtype='step',lw=1.8,label=label,color=color)
    axes[0].set(xlabel='Frozen residual quality direction',ylabel='Density');axes[0].legend(fontsize=7)
    ds=info['variants'][1]['distributions']['validation'];mean_s=np.asarray(ds['high_quality']['mean']);mean_f=np.asarray(ds['failure']['mean'])
    cs=np.asarray(ds['high_quality']['covariance']);cf=np.asarray(ds['failure']['covariance'])
    ts=info['variants'][1]['distributions']['exploration'];scale=np.sqrt(np.maximum((np.diag(ts['high_quality']['covariance'])+np.diag(ts['failure']['covariance']))/2,1e-20))
    axes[1].plot(range(8),mean_s/scale,marker='o',label='success');axes[1].plot(range(8),mean_f/scale,marker='o',label='failure')
    axes[1].set(xlabel='Shared residual coordinate',ylabel='Mean / common exploration std');axes[1].legend(fontsize=7)
    dc=(cf-cs)/scale[:,None]/scale[None,:];bound=max(float(np.abs(dc).max()),1e-8)
    im=axes[2].imshow(dc,vmin=-bound,vmax=bound,cmap='RdBu_r');axes[2].set(title='Failure covariance − success',xlabel='Coordinate',ylabel='Coordinate')
    fig.colorbar(im,ax=axes[2],fraction=.05,pad=.03);fig.tight_layout();save(fig,'route1_shared_distribution')
    fig,axes=plt.subplots(1,2,figsize=(8.2,6.4),sharey=True)
    for g,ax in enumerate(axes):
        a=np.full((19,8),np.nan)
        for r in paired:
            if r['noise_group']==g:a[r['layer'],r['token']]=r['ordering']
        im=ax.imshow(a,aspect='auto',vmin=.3,vmax=.95,cmap='RdYlBu');ax.set(title=f'Route2 held-out P{g}',xlabel='Action token',xticks=range(8))
    axes[0].set_yticks(range(19),labels);fig.colorbar(im,ax=axes,fraction=.04,pad=.04,label='Within-scene high/fail pair ordering')
    save(fig,'route2_pair_ordering')
    names=['collision','offroad','ttc'];fig,axes=plt.subplots(1,2,figsize=(7.4,3.4),sharey=True)
    for g,ax in enumerate(axes):
        a=np.empty((3,3))
        for i,fit in enumerate(names):
            for j,test in enumerate(names):
                rr=[r['ordering'] for r in modes if r['fit_mode']==fit and r['test_mode']==test and r['method']=='paired_residual_uncentered' and r['noise_group']==g and r['ordering'] is not None]
                a[i,j]=np.mean(rr)
        im=ax.imshow(a,vmin=.45,vmax=.9,cmap='RdYlBu');ax.set(title=f'Independent mode spaces, P{g}',xticks=range(3),xticklabels=names,xlabel='Held-out failure mode')
        for i in range(3):
            for j in range(3):ax.text(j,i,f'{a[i,j]:.3f}',ha='center',va='center')
    axes[0].set(yticks=range(3),yticklabels=names,ylabel='Exploration fit mode');fig.colorbar(im,ax=axes,fraction=.04,pad=.04,label='Pair ordering')
    save(fig,'route2_mode_transfer')
    temporal=read(ROOT/'analysis/temporal_v1/temporal_summary.json');fig,ax=plt.subplots(figsize=(7.3,3))
    for t in [20,40,60,80]:
        r=next(x for x in temporal if x['start_t']==t and x['subset']=='validation' and x['mode']=='all' and x['noise_group']==0)
        ax.plot(r['executed_timesteps'],np.asarray(r['relative_representation_difference']).mean((1,2)),marker='o',label=f'start={t}')
    ax.set(xlabel='Actual continuation step t',ylabel='Relative paired representation difference',yscale='log');ax.invert_xaxis();ax.legend(fontsize=8,ncols=2)
    fig.tight_layout();save(fig,'route2_continuation')
    def image_tag(name,caption):return f'<figure><img src="{images[name]}" alt="{html.escape(caption)}"><figcaption>{html.escape(caption)}</figcaption></figure>'
    count=Counter((r['subset'],r['quality']) for r in meta)
    splitrows=''.join(f'<tr><td>{s}</td><td>{count[(s,"high_quality")]:,}</td><td>{count[(s,"failure")]:,}</td><td>{count[(s,"intermediate")]:,}</td></tr>' for s in ['exploration','validation'])
    natural_rows=[]
    for t in [80,60,40,20,0]:
        for name,label in [('uncentered','未中心化'),('pooled_centered','共同中心化')]:
            rows=[r for r in tests if r['step_t']==t and r['centering']==name]
            natural_rows.append(f'<tr><td>{t}</td><td>{label}</td><td>{num(float(np.median([r["failure_auc"] for r in rows])))}</td><td>{num(float(np.median([r["failure_average_precision"] for r in rows])))}</td><td>{num(float(np.median([r["shared_training_bin_overlap"] for r in rows])))}</td><td>{num(float(np.median([r["continuous_pdms_spearman"] for r in rows if r["continuous_pdms_spearman"] is not None])))}</td></tr>')
    pairrows=''.join(f'<tr><td>{r["start_t"]}</td><td>{r["pairs"]:,}</td><td>{r["final_high_fail_pairs"]:,}</td><td>{r["reversed_orientation_pairs"]}</td></tr>' for r in coverage['by_start_t'])
    modeinfo=read(r2/'cells/layer00_token0.json')['independent_mode_fit_coverage']
    moderows=''.join(f'<tr><td>{m["mode"]}</td><td>{m["train_pairs"]}</td><td>{m["train_sessions"]}</td><td>{"已拟合并检查留出噪声" if m["status"]=="FIT" else "有效对照不足，未拟合"}</td></tr>' for m in modeinfo)
    conclusions=''.join(f'<p>{html.escape(p)}</p>' for p in narrative['conclusions'])
    methodrows=[]
    for scope,label in [('route1','路线一'),('route2','路线二')]:
        for item in narrative['completion_checklist'][scope]:methodrows.append(f'<tr><td>{label}</td><td class="long">{html.escape(item[0])}</td><td class="long">{html.escape(item[1])}</td></tr>')
    text=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>自然成功失败与失败GT配对：两条表征观察路线</title>
<style>body{{max-width:1100px;margin:32px auto;padding:0 20px;font:15px/1.8 system-ui,"Microsoft YaHei",sans-serif;color:#26343c}}h1{{font-size:26px}}h2{{font-size:21px;margin-top:32px}}h3{{font-size:17px}}.lead{{background:#edf6f5;border-left:4px solid #167d8d;padding:12px 18px}}.note{{background:#fff5e6;padding:12px 18px}}.muted,figcaption{{font-size:13px;color:#62717a}}table{{width:100%;border-collapse:collapse;font-size:13px;margin:16px 0}}td,th{{text-align:center;padding:8px;border-bottom:1px solid #dce4e8}}th{{background:#f2f6f7}}.long{{text-align:left}}figure{{margin:24px 0}}img{{width:100%;height:auto}}details{{border:1px solid #dce4e8;padding:12px 16px;margin:16px 0}}summary{{font-weight:600;cursor:pointer}}code{{font-size:12px;word-break:break-all}}li{{margin:7px 0}}@media(max-width:650px){{table{{font-size:11px}}}}</style>
<body><h1>模型自然成功／失败与失败—GT配对：两条表征观察路线</h1><p class="muted">ReCogDrive-2B-RL · navtrain · 2026-10-16 · 当前只观察，不干预或训练修复</p><div class="lead">{conclusions}</div>
<h2>两条路线的数据和问题分别是什么</h2>
<table><thead><tr><th>路线</th><th class="long">输入表征来自哪里</th><th>规模</th><th class="long">比较问题</th></tr></thead><tbody>
<tr><td>路线一</td><td class="long">模型按原S0自然生成的成功／失败轨迹；纯噪声起步，完整原采样器</td><td>103,288场景<br>90,153成功／2,288失败／10,847中间</td><td class="long">自然成功与自然失败的类别子空间、残差和分布是否不同？</td></tr>
<tr><td>路线二</td><td class="long">自然S0失败输出与同场景GT配对加噪，再完整去噪重评分</td><td>2,288场景<br>45,760候选</td><td class="long">固定场景观测时，高低质量轨迹的表征差异是否可重复？</td></tr></tbody></table>
<p>两条数据流分别拟合与评价。路线二场景来自路线一的失败池，存在场景包含关系，但其参考初始化和执行路径不同，<b>不能用路线二的全部候选代替路线一十万级自然输出。</b>本报告已纠正此前的数据归类；原版本与更正记录保留于任务provenance目录。</p>
<h2>路线一：完整自然S0成功／失败表征</h2><p>对全部103,288场景按原种子精确重放，每条最终轨迹均须与已保存基线完全相等，才复用原评分。未传入GT或失败轨迹作为初始化；保存五个原生去噪步80/60/40/20/0、18个384维阶段及独立512维输出、全部8个动作token。两节点各16卡真实捕获，并按自然质量类别累计float64充分统计。原始FP32表征与逐chunk哈希齐备。</p>
<table><thead><tr><th>采集会话划分</th><th>自然成功&gt;90</th><th>自然失败&lt;70</th><th>中间质量（含70与90）</th></tr></thead><tbody>{splitrows}</tbody></table>
<p>路线一先对探索集自然成功、失败各自SVD取等维U_success/U_failure，再计算R=(I−U_success U_successᵀ)U_failure并SVD。未中心化与探索集共同中心化分开，保留均值差；残差奇异值≤1e−6不生成方向。所有投影、中心、归一化与统计探针均在探索会话拟合，固定后评价留出自然场景。主k=8，2/4/8/16/32维的谱、重合、残差能量及均值／协方差效应另存。</p>
{image_tag('route1_natural_auc_t0','路线一最后原生步t=0：留出自然成功／失败的失败AUROC；点号表示会话内均值差主检验FDR<0.05且方向为正。AUROC与该会话检验的统计量不同。')}
<p>每个单元的分布统计使用相同残差坐标，包括均值向量、完整协方差矩阵、均值与协方差差、固定探索分位数bin的经验重叠。分类关联报告失败AUROC和AP，避免只看极不平衡数据的accuracy；验证极端类别中失败比例为{num(float((q[valid]<.7).sum()/((q[valid]<.7)|(q[valid]>.9)).sum())*100,2)}%。</p>
{image_tag('route1_shared_distribution','固定展示单元：最后原生步、最后DiT block、动作token7。两类共用探索残差基和标准化；直方图使用全部留出样本，类内归一为密度。均值和协方差均在同一坐标系。')}
<details><summary>路线一全部五步与完整指标</summary>{image_tag('route1_all_steps','共同中心化路线：全部五步的跨token平均AUROC及探索残差能量，分步统计，不混合不同噪声水平。')}
<table><thead><tr><th>自然去噪步</th><th>处理</th><th>AUROC中位数</th><th>AP中位数</th><th>分布重叠中位数</th><th>连续PDMS ρ中位数</th></tr></thead><tbody>{''.join(natural_rows)}</tbody></table>
<p>主检验为每个留出采集会话内“失败−成功”的冻结方向均值差：会话等权bootstrap500、符号置乱1999次，BH控制5×19×8×2=1,520项。正向且FDR&lt;0.05共{one['positive_within_session_fdr05']}/1,520项；各层/token高度相关，不将其当作独立机制数。连续PDMS探针在全部探索样本（含中间质量）上用精确充分统计拟合ridge，再固定到全部留出样本。</p></details>
<h2>路线二：失败输出与GT配对</h2><p>全部2,288个原始S0失败与GT直接配对，原始GT分数只记录；432个原始GT≤90的场景没有被提前排除。两分支共用初始噪声和各后续步随机量，从对应时间表index接续至结束后官方重评分，再按&lt;70／&gt;90选择分析两端。全部同类、中间质量与反转结果均保留。</p>
<table><thead><tr><th>加噪起点</th><th>全部尝试对数</th><th>最终高／低配对</th><th>其中来源方向反转</th></tr></thead><tbody>{pairrows}</tbody></table>
<p>低维主分析t=0，源于预实验的最终质量覆盖，而不是表征分离效果选参。t=0最终1,733组高／低配对中，184组来自原始GT≤90场景、涉及115个场景。探索P0拟合后固定到留出会话P0/P1；主差分SVD及配对类别子空间／残差均完成。路线二的“全部配对候选残差”另作内部对照，始终不计作路线一。</p>
{image_tag('route2_pair_ordering','路线二固定差分SVD方向的同场景质量排序率；这是成对排序，与路线一跨自然场景的失败AUROC不同，不能直接比较数值高低。')}
<p>路线二补齐了各残差空间的均值、协方差、共享bin重叠与成功AUC，并在包括中间质量和同类结果的全部候选上检查绝对PDMS与场景内PDMS差值。完整结果在paired_route2_completion_v2逐单元JSON与NPZ中。</p>
<h3>失败类型分别拟合，而不只重列共享方向</h3><table><thead><tr><th>最终失败类型</th><th>探索P0配对数</th><th>探索采集会话</th><th>状态</th></tr></thead><tbody>{moderows}</tbody></table>
{image_tag('route2_mode_transfer','按最终失败分支分别拟合的配对残差空间（未中心化）：固定后检验同类及跨类留出样本，展示跨层/token平均排序率。P0与P1均不重新拟合。')}
<p>碰撞、出界、TTC均完成独立差分SVD与独立配对残差，保存类别谱、子空间、主角度及方向相似性；进度类有效对照只有1个探索场景，无法可靠估计该类空间。本项已如实记录为样本不足，不沿用初始化标签补造样本。模式迁移共有{two['mode_transfer_tests']:,}项描述结果，其中满足预定覆盖条件的{two['qualified_mode_transfer_family']:,}项构成独立FDR家族。</p>
<details><summary>路线二去噪过程中的差异保留与消失</summary>{image_tag('route2_continuation','相同观测与配对噪声下，较重初始化的分支差异沿实际去噪步骤收缩；所有起点及全部质量结果都保留。')}</details>
<h2>PLAN执行完成表</h2><table><thead><tr><th>路线</th><th class="long">计划项目</th><th class="long">完成证据与范围</th></tr></thead><tbody>{''.join(methodrows)}</tbody></table>
<h2>结论的适用范围</h2><p>{html.escape(narrative['boundary'])}</p><ul>{''.join('<li>'+html.escape(x)+'</li>' for x in narrative['next_observations'])}</ul>
<details><summary>协议、产出和复核入口</summary><p>RL checkpoint SHA256：<code>23fb949b10387efeff87e093703d5faf41b61b9e5ead16d4076661e3c7c08a20</code>；FP32、batch1、eval/no_grad、原DDIM eta=1。自然S0根种子20261008、j=0，逐场景SHA256映射；路线二配对噪声根种子20261016、P0/P1。二者随机协议分别保存。路线一不传init_actions，路线二传入对应加噪轨迹并从正确index续采。</p>
<p>路线一：<code>runs/{one['source_run']}/</code>，协议<code>configs/natural_route1_v1.json</code>、<code>configs/natural_analysis_v1.json</code>，全部谱／残差／协方差／连续指标<code>analysis/natural_route1_v1/</code>。路线二：<code>runs/paired_formal_20261016T0728Z/</code>、<code>analysis/observation_v1/</code>、<code>analysis/paired_route2_completion_v2/</code>、<code>analysis/temporal_v1/</code>。新报告代码为<code>code/two_route_report.py</code>。原报告及旧范围完成声明留档于<code>provenance/route-definition-correction/</code>，以本次两路线验收为准。</p>
<p>自然S0基线103,288个官方评分本身已独立验收。路线一逐条精确重放后复用它们，全部原始表征chunk在投影时验证SHA256；原始tensor抽取的独立tile统计与累计充分统计再次一致。32卡冒烟96个锚点比较全部张量、噪声、轨迹精确一致。路线二45,760候选与80条原始评分入口独立重算差异0。独立采集会话划分保持固定，未读取navtest，未训练修复模型、未修改共享代码或公共环境。</p>
<p>HTML结构、核心数字和数据来源已核对，图表另有PNG/SVG产物；未做浏览器渲染验收。</p></details><p class="muted">生成时间：{stamp()}。本报告只呈现观察证据，不把表征相关、子空间差异或GT初始化结果写成已实现的能力修复。</p></body></html>'''
    destination=Path(args.report).resolve();destination.write_text(text)
    atomic(ROOT/'analysis/two_route_report_build.json',dict(status='COMPLETE',time=stamp(),report=str(destination),sha256=sha(destination),
        figures=len(images),route1_source='natural_model_S0',route2_source='failed_output_GT_pairs',browser_render_verified=False))
    print(json.dumps(dict(report=str(destination),bytes=destination.stat().st_size,figures=len(images))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',required=True);args=p.parse_args();setup('two_route_report');build(args)
