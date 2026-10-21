"""Standalone expanded section with complete scan surfaces, controls and frozen distributions."""
from common import *
import base64
import html
import numpy as np
from subspace_scan_prepare import OUT,TIMES
from subspace_scan_math import KS,RS,configs
from repair_report import table

def esc(x):return html.escape(str(x))
def n(x,d=3):return '—' if x is None else f'{x:.{d}f}'
def m(row,key,group='P0'):return row.get(group,{}).get(key) if row.get(group) else None
def ci(infer,key):return '—' if not infer else '['+', '.join(n(v) for v in infer[key])+']'

def main(args):
    setup('subspace_scan/report')
    assert read(OUT/'REPORT_DATA_READY.json')['status']=='PASS';accepted=read(OUT/'FINAL_ACCEPTANCE.json');assert accepted['status']=='PASS'
    direct=read(OUT/'DIRECT_SVD_INDEPENDENT_AUDIT.json');assert direct['status']=='PASS'
    doc=read(OUT/'CONFIRMATION_RESULTS.json');regions=doc['regions'];records=doc['records'];lock=read(OUT/'FROZEN_CONFIRMATION.json');dist=read(OUT/'FROZEN_DISTRIBUTIONS.json');control=read(OUT/'CONTROL_COMPARISONS.json');narrative=read(OUT/'REPORT_NARRATIVE.json');cfg=read(ROOT/'configs/subspace_scan_execution_v2.json');base=ROOT/'runs'/cfg['run']
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    figures=OUT/'figure_versions'/args.version;figures.mkdir(parents=True,exist_ok=False);images={};proofs=[]
    def save(fig,key,caption):
        if not fig.get_constrained_layout():fig.tight_layout()
        fig.canvas.draw();p=figures/(key+'.png');fig.savefig(p,dpi=150,bbox_inches='tight');fig.savefig(p.with_suffix('.svg'),bbox_inches='tight');plt.close(fig)
        images[key]=f'<figure><img src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}" alt="{esc(caption)}"><figcaption>{esc(caption)}</figcaption></figure>'
        proofs.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p),caption=caption))
    cell_index={r['cell']:r for r in read(OUT/'CELL_INDEX.json')};response={};representatives=[]
    for route in ['r1','r2']:
        for center in ['uncentered','pooled_centered']:
            pool=[r for r in regions if r['route']==route and r['centering']==center and r['equal_main']]
            if not pool:continue
            region=max(pool,key=lambda r:(r['stable_region_confirmed'],not r['diagnostic_only'],r['cv']['neighbor_median_conservative_auc']));representatives.append(region)
            leader=region['leader'];cc=leader['config'];cell=region['cell'];task=cell_index[cell]['task'];data=read(base/'results'/(task['id']+'.json'));rows=[r for r in data['search'] if r['centering']==center];response[(route,center)]=rows
            lookup={(r['config']['ks'],r['config']['kf'],r['config']['r']):r for r in rows if r['config']['kind']=='residual'}
            def area(ks,kf,r,g='P0'):
                row=lookup[(ks,kf,r)];return m(row,'auc',g) if row['status']=='VALID' else None
            fig,axes=plt.subplots(1,2,figsize=(10.8,4.5),constrained_layout=True)
            equal=np.array([[area(k,k,r) if area(k,k,r) is not None else np.nan for k in KS] for r in RS]);fixed=np.array([[area(ks,kf,cc['r']) if area(ks,kf,cc['r']) is not None else np.nan for ks in KS] for kf in KS])
            for ax,z,xlabels,ylabels in [(axes[0],equal,KS,RS),(axes[1],fixed,KS,KS)]:
                cmap=plt.get_cmap('viridis').copy();cmap.set_bad('#e4e7e9');im=ax.imshow(z,origin='lower',aspect='auto',vmin=.4,vmax=1.,cmap=cmap)
                ax.set(xticks=range(len(xlabels)),xticklabels=xlabels,yticks=range(len(ylabels)),yticklabels=ylabels);ax.tick_params(axis='x',rotation=45)
                for y in range(z.shape[0]):
                    for x0 in range(z.shape[1]):
                        if np.isfinite(z[y,x0]):ax.text(x0,y,f'{z[y,x0]:.2f}',ha='center',va='center',fontsize=6,color='white' if z[y,x0]<.75 else '#26343c')
            for j,kf in enumerate(KS):
                for i,ks in enumerate(KS):
                    if lookup[(ks,kf,cc['r'])]['cutoff_degenerate_any_fold'] and np.isfinite(fixed[j,i]):axes[1].add_patch(Rectangle((i-.5,j-.5),1,1,fill=False,hatch='///',edgecolor='#aaaaaa',lw=0))
            axes[0].set(xlabel='k_s = k_f',ylabel='Final residual r',title='Equal main spaces: CV AUROC')
            axes[1].set(xlabel='Success k_s',ylabel='Failure k_f',title=f'Fixed residual r={cc["r"]}: CV AUROC')
            fig.colorbar(im,ax=axes.ravel().tolist(),fraction=.024,pad=.02);fig.suptitle(f'{route} | {center} | {cell}',fontsize=10)
            save(fig,f'{route}_{center}_surface','探索会话交叉验证响应面：左为等维主空间主比较，右在同一最终r下比较ks/kf。灰色为秩不足；斜线表示残差截断落在重复奇异值平台，不能作为唯一基方向的稳定证据。')
            fig,axes=plt.subplots(1,3,figsize=(12,3.5));settings=[[(k,cc['kf'],cc['r']) for k in KS],[(cc['ks'],k,cc['r']) for k in KS],[(cc['ks'],cc['kf'],r) for r in RS]]
            for ax,points,labels,title in zip(axes,settings,[KS,KS,RS],[f'Fixed k_f={cc["kf"]}, r={cc["r"]}',f'Fixed k_s={cc["ks"]}, r={cc["r"]}',f'Fixed main {cc["ks"]}/{cc["kf"]}']):
                for g,color in [('P0','#167d8d'),('P1','#d17a36')]:
                    if g=='P1' and route=='r1':continue
                    vals=[area(*v,g) for v in points];ax.plot(range(len(points)),[np.nan if v is None else v for v in vals],'-o',ms=3,c=color,label=('Natural S0' if route=='r1' else g))
                lows=[];highs=[]
                for v in points:
                    r=lookup[v];a=[f['P0']['auc'] for f in r['folds'] if f.get('P0')] if r['status']=='VALID' else []
                    lows.append(min(a) if a else np.nan);highs.append(max(a) if a else np.nan)
                ax.fill_between(range(len(points)),lows,highs,color='#167d8d',alpha=.13,label=('Natural S0 fold range' if route=='r1' else 'P0 fold range'))
                ax.axhline(.5,c='grey',lw=.7);ax.set(xticks=range(len(labels)),xticklabels=labels,ylabel='CV AUROC',title=title);ax.tick_params(axis='x',rotation=45);ax.set_ylim(.35,1.03)
            axes[0].set_xlabel('Success k_s');axes[1].set_xlabel('Failure k_f');axes[2].set_xlabel('Residual r');axes[0].legend(fontsize=7)
            save(fig,f'{route}_{center}_curves','分别固定kf/r、ks/r及主空间查看维数曲线。阴影是五折范围，不是置信区间；路线二P0/P1使用相同的P0训练空间。')
    non_equal_images=''
    for region in regions:
        if region['route']!='r2' or region['equal_main'] or region['leader']['config']['r']<=32:continue
        cell=region['cell'];center=region['centering'];cc=region['leader']['config'];task=cell_index[cell]['task'];data=read(base/'results'/(task['id']+'.json'));rows=[r for r in data['search'] if r['centering']==center]
        lookup={(r['config']['ks'],r['config']['kf'],r['config']['r']):r for r in rows if r['config']['kind']=='residual'}
        fig,axes=plt.subplots(1,2,figsize=(11,4.6),constrained_layout=True);z=np.full((9,9),np.nan)
        for j,kf in enumerate(KS):
            for i,ks in enumerate(KS):
                row=lookup[(ks,kf,cc['r'])]
                if row['status']=='VALID':z[j,i]=m(row,'auc')
        cmap=plt.get_cmap('viridis').copy();cmap.set_bad('#e4e7e9');im=axes[0].imshow(z,origin='lower',aspect='auto',vmin=.4,vmax=1.,cmap=cmap)
        for j,kf in enumerate(KS):
            for i,ks in enumerate(KS):
                row=lookup[(ks,kf,cc['r'])]
                if np.isfinite(z[j,i]):
                    axes[0].text(i,j,f'{z[j,i]:.2f}',ha='center',va='center',fontsize=6,color='white' if z[j,i]<.75 else '#26343c')
                    if row['cutoff_degenerate_any_fold']:axes[0].add_patch(Rectangle((i-.5,j-.5),1,1,fill=False,hatch='///',edgecolor='#aaa',lw=0))
        axes[0].add_patch(Rectangle((KS.index(cc['ks'])-.5,KS.index(cc['kf'])-.5),1,1,fill=False,edgecolor='#d17a36',lw=2))
        axes[0].set(xticks=range(9),xticklabels=KS,yticks=range(9),yticklabels=KS,xlabel='Success k_s',ylabel='Failure k_f',title=f'Non-equal candidate: fixed r={cc["r"]}');axes[0].tick_params(axis='x',rotation=45);fig.colorbar(im,ax=axes[0],fraction=.035,pad=.02)
        for g,color in [('P0','#167d8d'),('P1','#d17a36')]:
            v=[lookup[(cc['ks'],cc['kf'],r)] for r in RS];y=[m(a,'auc',g) if a['status']=='VALID' else np.nan for a in v];axes[1].plot(range(8),y,'--o',ms=4,c=color,label=('Natural S0' if route=='r1' else g))
            deg=[i for i,a in enumerate(v) if a['status']=='VALID' and a['cutoff_degenerate_any_fold']];axes[1].scatter(deg,[y[i] for i in deg],marker='x',s=50,c='black',zorder=5)
        axes[1].axhline(.5,c='grey',lw=.7);axes[1].set(xticks=range(8),xticklabels=RS,xlabel='Residual r',ylabel='CV AUROC',title=f'Fixed main {cc["ks"]}/{cc["kf"]}');axes[1].set_ylim(.35,1.0);axes[1].legend(fontsize=8)
        key='non_equal_'+region['region_id'];save(fig,key,'超32维非等维候选的独立对照：左在同一最终r下比较主空间，橙框为冻结候选；右固定主空间改变r。灰区为秩不足，斜线/黑叉为截断不唯一的诊断值，不能据这些截断值直接证明维数优劣。');non_equal_images+=images[key]
    point_proofs=[];distribution_images='' 
    for route in ['r1','r2']:
        pool=[r for r in representatives if r['route']==route]
        if route=='r2':
            wider=[r for r in regions if r['route']==route and not r['equal_main'] and r['stable_region_confirmed'] and r['leader']['config']['r']>32]
            if wider:pool=wider
        if not pool:continue
        region=max(pool,key=lambda r:(r['stable_region_confirmed'],not r['diagnostic_only'],r['cv']['neighbor_median_conservative_auc']));leader=region['leader'];cell=region['cell']
        candidates=[r for r in dist['records'] if r['cell']==cell and r['centering']==region['centering'] and r['index']==leader['index'] and r['status']=='COMPLETE']
        if not candidates:continue
        with np.load(ROOT/candidates[0]['path'],allow_pickle=False) as z:axes2=np.array(z['plot_axes']);center2=np.array(z['plot_center'])
        raw=np.load(OUT/'cache'/(cell+'.npy'),mmap_mode='r');meta=read(OUT/('natural_metadata.json' if route=='r1' else 'paired_metadata.json'));valid=np.array([r['subset']=='validation' for r in meta])
        q=np.load(ROOT/'analysis/natural_route1_v1/scores.npy') if route=='r1' else np.load(OUT/f'cache/r2_a{leader["task"]["start"]}_scores.npy')
        fig,ax=plt.subplots(1,2,figsize=(10,4));rng=np.random.default_rng(20261016)
        for g in ([0] if route=='r1' else [0,1]):
            mask=valid&(((q<.7)|(q>.9)) if route=='r1' else (((q[g,:,0]<.7)&(q[g,:,1]>.9))|((q[g,:,1]<.7)&(q[g,:,0]>.9))))
            indices=np.flatnonzero(mask);values=np.asarray(raw[mask],dtype=np.float64) if route=='r1' else np.asarray(raw[g,mask],dtype=np.float64).reshape(-1,raw.shape[-1]);quality=q[mask] if route=='r1' else q[g,mask].reshape(-1);coord=(values-center2)@axes2
            panel=ax[0] if route=='r1' else ax[g]
            for label,color,tag in [(quality>.9,'#167d8d','High'),(quality<.7,'#d17a36','Failure')]:
                ids=np.flatnonzero(label);chosen=rng.choice(ids,min(len(ids),800),replace=False)
                panel.scatter(coord[chosen,0],coord[chosen,1],s=8,alpha=.3,c=color,label=f'{tag} n={len(ids)}',rasterized=True)
                point_proofs.append(dict(route=route,cell=cell,noise_group=g,label=tag,flat_plot_indices=chosen.tolist(),source_case_indices=indices.tolist()))
                if route=='r1':
                    v=np.sort(coord[ids,0]);ax[1].plot(v,np.arange(1,len(v)+1)/len(v),c=color,label=tag)
            if route=='r2':
                paired_coord=coord.reshape(-1,2,2)
                for j in rng.choice(len(paired_coord),min(len(paired_coord),25),replace=False):panel.plot(paired_coord[j,:,0],paired_coord[j,:,1],c='grey',alpha=.25,lw=.6)
            panel.set(xlabel='Train mean-gap axis (standard units)',ylabel='Remaining variance axis (standard units)',title=f'{route} '+('Natural S0' if route=='r1' else f'P{g}')+f' | {cell}');panel.legend(fontsize=7);panel.grid(alpha=.12)
        if route=='r1':ax[1].set(xlabel='Train mean-gap axis (standard units)',ylabel='All held-out outputs: ECDF',title='Complete one-dimensional distributions');ax[1].legend(fontsize=8);ax[1].grid(alpha=.12)
        key=route+'_heldout_distribution';save(fig,key,'冻结候选的留出分布（路线一为等维区域，路线二展示已确认的48维非等维区域），坐标仅用探索数据拟合；每类最多显示800点，曲线和数值统计包含全体样本。路线二灰线连接同场景的两条候选，展示边际分布重叠与配对质量排序可以同时存在。该图不是行为语义解释或修复效果。');distribution_images+=images[key]
    atomic(figures/'PLOTTED_POINTS.json',point_proofs)
    paired_meta=read(OUT/'paired_metadata.json');exploration=np.array([r['subset']=='exploration' for r in paired_meta]);pair_scope=[]
    for start in TIMES:
        q=np.load(OUT/f'cache/r2_a{start}_scores.npy');counts=[]
        for g in [0,1]:
            endpoint=((q[g,:,0]<.7)&(q[g,:,1]>.9))|((q[g,:,1]<.7)&(q[g,:,0]>.9));counts.append((int((endpoint&exploration).sum()),int((endpoint&~exploration).sum())))
        pair_scope.append([start,5-TIMES.index(start),f'{counts[0][0]}/{counts[0][1]}',f'{counts[1][0]}/{counts[1][1]}'])
    dimension_rows=[]
    for row in read(OUT/'DIMENSION_EFFECTS.json')['records']:
        a=row['auc_P0'];b=row['ap_P0']
        dimension_rows.append([row['route'],row['centering'],row['axis'],f'{row["start"]}→{row["end"]}',row['matched_valid_combinations'],n(a['median']),n(b['median']),('—' if a['improved_fraction'] is None else f'{100*a["improved_fraction"]:.1f}%')])
    region_rows=[]
    for r in regions:
        a=r['leader'];c=a['config'];p0=a.get('P0');p1=a.get('P1');in0=a.get('inference_P0');noise=a.get('noise_consistency',{})
        region_rows.append([esc(r['region_id']),esc(r['cell']),esc(r['centering']),f'{c["ks"]}/{c["kf"]}/{c["r"]}',
            n(r['cv']['cv']['P0']['auc']),n(m(a,'auc'))+'<br>'+ci(in0,'auc_ci95'),n(m(a,'ap')),n(m(a,'standardized_gap')),
            n(m(a,'pair_ordering'))+'/'+n(m(a,'pair_ordering','P1')) if r['route']=='r2' else '—',
            n(noise.get('common_branch_order_agreement')),n(a.get('holm_P0'),4)+'/'+n(a.get('holm_P1'),4),
            f'{r["positive_neighbors"]}/{r["neighboring_points"]}',('确认' if r['stable_region_confirmed'] else '未确认')+('（探索诊断）' if r['diagnostic_only'] else '')])
    controls=[]
    for r in control['records']:
        if r['metric']!='AUROC':continue
        controls.append([esc(r['region_id']),('自然S0' if r['route']=='r1' else r['noise']),esc(r['control']),n(r['estimate']), '['+', '.join(n(v) for v in r['simultaneous_ci95'])+']'])
    distributions=[]
    for region in regions:
        a=region['leader'];matches=[r for r in dist['records'] if r['cell']==region['cell'] and r['centering']==region['centering'] and r['index']==a['index']]
        if not matches:continue
        row=matches[0]
        if row['status']!='COMPLETE':distributions.append([esc(region['region_id']),esc(row['status']),'—','—','—']);continue
        for group,stats in row['statistics'].items():
            if group=='training':continue
            distributions.append([esc(region['region_id']),('自然S0留出' if region['route']=='r1' else group),f'{stats["n_high"]}/{stats["n_failure"]}',n(stats['within_group_standardized_mean_distance']),n(stats['whitened_covariance_difference_per_sqrt_dimension'])])
    scope=[]
    for route,e in doc['effective_scope'].items():scope.append([route,e['requested'],e['valid'],e['rank_ineligible'],e['constant_or_insufficient'],e['cutoff_degenerate']])
    bullets=''.join('<p>'+esc(v)+'</p>' for v in narrative['conclusions']);surfaces='';curves=''
    for route in ['r1','r2']:
        surfaces+=f'<details><summary>{"路线一" if route=="r1" else "路线二"}：两套中心化的主空间／残差响应面</summary>'+''.join(images.get(f'{route}_{center}_surface','') for center in ['uncentered','pooled_centered'])+'</details>'
        curves+=f'<details><summary>{"路线一" if route=="r1" else "路线二"}：固定变量的维数曲线</summary>'+''.join(images.get(f'{route}_{center}_curves','') for center in ['uncentered','pooled_centered'])+'</details>'
    section=f'''<h3>扩大主空间与最终残差维数后的观察</h3><div class="lead">{bullets}</div><p>复用原始表征与完整float64充分统计，无模型重采集。ks、kf分别扫描4/8/16/24/32/48/64/128/256，r扫描2/4/8/16/24/32/48/64；两种中心化、路线一760及路线二2,280位置，共{accepted['requested_variants']:,}个请求配置。每个配置采用五折探索会话交叉拟合；等维主空间作为主比较，非等维单列。秩不足不填零、不偷偷改小维数。</p><p>质量读出按失败方向定义，AUROC/AP以&lt;70为正类；配对排序是风险读出把最终失败分支排在高质分支之前的比例，不能当作修复成功率。读出固定为投影后的类别均值差，标准化仅用训练折；这样可比较维数本身。AUROC/AP、标准化差异、会话方向一致性及邻域支持共同筛选；路线二还要求P0/P1配对排序和共同病例的分支排序一致。路线一只复用自然S0表征，未增加自然采样种子的采集，跨噪声确认限于路线二。随机同r空间为三个Gaussian-QR构造种子，另有全维、同r最小等维主空间及可行旧8/8/8锚点。</p>{distribution_images}<details><summary>超32维非等维候选：固定最终r的比较</summary>{non_equal_images}</details>{surfaces}{curves}<details><summary>固定其余变量后，完整网格的维数变化统计</summary><p>每个差值固定位置、中心化及其余维数，只比较两端均有效且截断不退化的CV配置。equal_main同时增加ks=kf且固定r；ks、kf分别固定另一主空间与r；r固定主空间。配置对数不是独立场景数，表内为描述性汇总，不作额外显著性宣称。</p>{table(["路线","中心化","变化轴","维数","有效配对配置数","ΔAUC中位数","ΔAP中位数","AUC改善占比"],dimension_rows)}</details>
<details><summary>路线二最终高低质量配对的实际覆盖</summary>{table(["加噪起点","已有原生去噪位置数","P0探索/留出配对","P1探索/留出配对"],pair_scope)}<p>起点80/60没有最终&lt;70与&gt;90端点配对，40/20只有少量对照；全部冻结路线二区域来自起点0。早期位置的配对样本不足，关于这些位置的质量结构保留结论。原始候选已完整采集，没有用原GT分数预筛，也没有为增加配对重跑模型。</p></details><p>探索后冻结{len(regions)}个区域、{len(lock['cells'])}个位置中的{sum(len(v) for v in lock['cells'].values())}个读出配置，仅对这些配置及其已登记邻点/对照进行原训练留出集确认。主关联检验按路线分别Holm校正，家族大小为{esc(doc['holm_family_sizes'])}；“区域确认”还要求至少两个邻点同样成立。未据留出结果重新调参或替换候选。</p>
<details><summary>冻结区域：完整探索与留出结果</summary><div class="scroll">{table(['区域','位置','中心化','ks/kf/r','CV AUC','留出AUC [95% CI]（自然S0/配对P0）','AP','标准化差异','配对排序P0/P1','噪声排序一致','Holm P0/P1','确认邻点','结论'],region_rows,left=(0,1))}</div><p>AP基率两路线不同，不能直接跨路线比较。路线一为自然S0成功/失败总体，路线二为最终高低端点配对；后者每对两类各一个，AP基率0.5。95% CI为会话bootstrap描述性区间，正式关联判断使用另列的Holm p。</p></details>
<details><summary>与同维随机／全维／同r主空间对照的配对比较</summary><p>表内差值为区域读出减对照；随机对照先分别计算三组成绩再平均，未将其当作新增病例或合成更高维预测器。全部已登记AUROC/AP及P0/P1比较按路线用共同会话bootstrap maxT校正，给出近似同时95%区间；完整AP对比和不可评价项保存在CONTROL_COMPARISONS.json。</p>{table(['区域','噪声','对照','ΔAUC','同时95% CI'],controls,left=(0,2))}</details>
<details><summary>冻结候选的完整r维分布</summary><p>下表补充完整r维均值与协方差差异。标准化均值距离采用正则化的合并类内协方差；协方差差异白化后按√r归一。另保存固定探索参考白化的结果、实际有效秩、均值和协方差矩阵。这些为冻结候选的描述性分析，没有据此扩大候选或进行仅协方差读出的完整搜索。区域可以在相邻层、token和维数上重叠，不能当作互相独立的失败机制。</p>{table(['区域','留出组','高质/失败输出','多维标准化均值距离','标准化协方差差异'],distributions,left=(0,))}</details>
<p>{esc(narrative['interpretation'])}</p><details><summary>完整范围、校正、执行与复核</summary>{table(['路线','请求数','五折有效','秩不足','常数/不足','有效中截断不唯一'],scope)}<p>请求数包含同r随机与全维对照、两种中心化；五折是交叉拟合，不扩大独立场景数。路线二覆盖5种加噪起点对应的15个原生去噪位置组合，而非只看t0。探索完整有效残差家族BH只作探索记录，交叉拟合间相关性限制其确认解释；留出小家族Holm与对照maxT承担确认。该留出是既有navtrain会话留出，并非新采集数据；扩展未使用navtest数据。</p><p>全维类别基由完整矩重新求解，解除旧32维存储限制；残差重SVD后QR重正交，保留各前缀空间。单元ID中a为加噪起点（路线一a=-1），s为原生[80,60,40,20,0]的index，l=0/1对应动作编码/条件融合，l=2–17对应DiT0–15，l=18为512维最终输出；末尾t为action token index 0–7，对应0.5–4.0秒。主探针固定，未把更换读出算法的增益归因于扩大维数。该线性读出和已冻结分布分析尚未穷尽协方差或非线性质量信息。</p><p>来源与复核：<code>analysis/subspace_scan_v2/PROTOCOL.json</code>、<code>CV_SEARCH_LEDGER.npy</code>、<code>FROZEN_CONFIRMATION.json</code>、<code>CONFIRMATION_RESULTS.json</code>、<code>CONTROL_COMPARISONS.json</code>、<code>FROZEN_DISTRIBUTIONS.json</code>。全部3,040原始缓存来源SHA、计算结果与覆盖核对；路线一每格五折全维矩重建吻合原充分统计。独立直接居中Gram+直接残差SVD路径复核通过，另保留完整split与执行审计。两节点各16卡实际数值冒烟及五分钟语义检查通过，运行代码冻结、所有旧队列保持开放。</p></details>'''
    archive=OUT/'report_versions'/args.version;archive.mkdir(parents=True,exist_ok=False)
    if (OUT/'REPORT_SECTION.html').exists():(archive/'previous_section.html').write_text((OUT/'REPORT_SECTION.html').read_text())
    (archive/'REPORT_SECTION.html').write_text(section);(OUT/'REPORT_SECTION.html').write_text(section)
    import shutil
    shutil.copy2(OUT/'REPORT_NARRATIVE.json',archive/'REPORT_NARRATIVE.json');shutil.copy2(Path(__file__),archive/'report_generator.py')
    if (OUT/'REPORT_BUILD.json').exists():(archive/'previous_build.json').write_text((OUT/'REPORT_BUILD.json').read_text())
    atomic(OUT/'REPORT_BUILD.json',dict(status='COMPLETE',time=stamp(),section_sha256=sha(OUT/'REPORT_SECTION.html'),narrative_sha256=sha(OUT/'REPORT_NARRATIVE.json'),figures=proofs,
        controls_sha256=sha(OUT/'CONTROL_COMPARISONS.json'),distributions_sha256=sha(OUT/'FROZEN_DISTRIBUTIONS.json'),browser_render_verified=False))
    print(json.dumps(dict(status='COMPLETE',figures=len(proofs),regions=len(regions))),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--version',default='v2');main(p.parse_args())
