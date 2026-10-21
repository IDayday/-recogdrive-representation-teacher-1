"""Figures separating breadth, independent fits, control capacity and routing.

All numbers come from stored scored outputs. No selection, cloud or GPU action.
"""
from r2_common import *


def main():
    setup('report_figures_v2')
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
    sources=[]
    def source(rel):
        value=read(ROOT/rel);sources.append(dict(path=rel,sha256=sha(ROOT/rel)));return value
    def pointer(rel):
        p=source(rel);assert sha(ROOT/p['path'])==p['sha256'];return source(p['path'])
    cv=pointer('analysis/extended_cv_reviews/LATEST.json');full=[r for r in cv['recipes'] if r['complete_five_folds']]
    rep=pointer('analysis/repetition_cv_reviews/LATEST.json')
    directory=ROOT/'analysis/report_figures_v2'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%f');directory.mkdir(parents=True,exist_ok=False)
    figures=[]
    def save(fig,name,caption):
        if not fig.get_constrained_layout():fig.tight_layout()
        for ext in ['svg','png']:fig.savefig(directory/(name+'.'+ext),dpi=160,bbox_inches='tight')
        plt.close(fig);figures.append(dict(name=name,png=str((directory/(name+'.png')).relative_to(ROOT)),svg=str((directory/(name+'.svg')).relative_to(ROOT)),caption=caption))
    families=['representation','response','correction']
    methods=[('warm_hard','Fixed hard route',6),('candidate_selector','Independent candidate selector',4),('joint_soft_joint','Joint soft intervention',6)]
    images=[];counts=[]
    for method,_,_ in methods:
        image=np.full((3,7),np.nan);count=np.zeros((3,7),int)
        for f,family in enumerate(families):
            for j,k in enumerate(range(2,9)):
                rows=[r for r in full if r['system']==f'{family}_K{k}_seed0' and r['method']==method]
                if rows:image[f,j]=max(r['standardized_pdms_gain'] for r in rows);count[f,j]=len(rows)
        images.append(image);counts.append(count)
    bound=max(.1,max(float(np.nanmax(abs(v))) if np.isfinite(v).any() else 0 for v in images))
    fig,axes=plt.subplots(1,3,figsize=(15,3.5),constrained_layout=True)
    for ax,(method,title,expected),values,count in zip(axes,methods,images,counts):
        plot=ax.imshow(np.ma.masked_invalid(values),cmap='RdBu_r',vmin=-bound,vmax=bound,aspect='auto')
        for f in range(3):
            for j in range(7):ax.text(j,f,'pending' if not count[f,j] else f'{values[f,j]:+.3f}\n{count[f,j]}/{expected}',ha='center',va='center',fontsize=7)
        ax.set_title(title);ax.set_xticks(range(7),range(2,9));ax.set_yticks(range(3),families if ax is axes[0] else []);ax.set_xlabel('Nonzero K; identity additional')
    fig.colorbar(plot,ax=axes.ravel().tolist(),label='Exploratory maximum PDMS change (points)',shrink=.8)
    save(fig,'breadth_by_route','每格为初始拟合中已齐五折配置的探索最大值；分母为该路由预设配置数，空白是未完成。最大值包含角色／信息层级选择，不是稳定提升或最终公平排名；完整负结果及多重比较另附。')
    # The chosen early signal is shown together with every whole-fit repeat.
    selected=[('joint_soft_joint','safety_trajectory'),('joint_soft_joint','safety_observation'),('joint_hard_continuous','safety_trajectory'),('finite_outcome_router_finite_outcome','regret_natural_512_safety_trajectory')]
    records=[r for method,policy in selected for r in rep['recipes'] if r['system_stem']=='correction_K3' and r['method']==method and r['policy']==policy and r['all_three_fits_complete']]
    if records:
        fig,ax=plt.subplots(figsize=(10,4.2));colors=['#3c78a8','#d28b35','#5c9974']
        for j,r in enumerate(records):
            for f in range(3):
                ys=r['fit_gain_by_noise'][f];ax.scatter(j+(f-1)*.2+np.array([-.025,0,.025]),ys,s=22,color=colors[f],alpha=.6)
                ax.plot([j+(f-1)*.2-.06,j+(f-1)*.2+.06],[r['fit_mean_gains'][f]]*2,color=colors[f],lw=3,label=f'Whole fit {f}' if j==0 else None)
        labels=[r['method'].replace('joint_','')+'\n'+r['policy'] for r in records]
        ax.set_xticks(range(len(records)),labels,fontsize=8);ax.axhline(0,color='black',lw=.8);ax.legend(frameon=False,ncol=3);ax.set_ylabel('Class-standardized PDMS change (points)');ax.set_title('Early correction-K3 signals and independent whole-pipeline repeats')
        save(fig,'whole_fit_repetition','粗横线是该完整拟合的三噪声均值，散点为S0/S1/S2；同场景、同噪声，不增加独立样本量。跨拟合均值不是部署集成，不选择最好的拟合种子。')
    if (ROOT/'analysis/space_control_summary/LATEST.json').exists():
        control=pointer('analysis/space_control_summary/LATEST.json');fig,axes=plt.subplots(1,2,figsize=(11,4.1))
        specs=[('global_quality_residual','#437da8','Global quality'),('own_group_quality_residual','#bd8535','Own-group quality'),('Haar_random','#777777','Matched random')]
        for ax,block in zip(axes,['interface_pre','interface_post']):
            for kind,color,label in specs:
                for rank in [8,32,128]:
                    values=[r['mean_transfer_gain'] for r in control['results'] if r['block']==block and r['cap']==.1 and r['space']==kind and r['rank']==rank]
                    if values:ax.scatter([rank]*len(values),values,color=color,alpha=.45,s=18);ax.plot([rank-1,rank+1],[np.mean(values)]*2,color=color,lw=3)
                means=[np.mean([r['mean_transfer_gain'] for r in control['results'] if r['block']==block and r['cap']==.1 and r['space']==kind and r['rank']==rank]) for rank in [8,32,128]]
                ax.plot([8,32,128],means,color=color,label=label)
            baseline=next(r for r in control['results'] if r['block']==block and r['cap']==.1 and r['space']=='full');ax.axhline(baseline['mean_transfer_gain'],color='#5b8d68',ls='--',label='Restricted full-channel')
            ax.set_xscale('log',base=2);ax.set_xticks([8,32,128],[8,32,128]);ax.set_title(block);ax.set_xlabel('Intervention rank');ax.set_ylabel('Failure-conditional S1/S2 gain (points)');ax.legend(frameon=False,fontsize=8)
        save(fig,'quality_random_full_control','同24场景／20会话、相同代理优化与真实评分查询预算、相对范数上限0.1；S0选定扰动固定迁移到S1/S2。质量空间点包括中心化／子群构造，随机点为两个固定同维空间；仅限所测主空间与预算，不否定所有质量表征。')
    if (ROOT/'analysis/expert_capacity_control/FIXED_CANDIDATE_TRANSFER.json').exists():
        original=source('analysis/expert_capacity_control/SUMMARY.json');transfer=source('analysis/expert_capacity_control/FIXED_CANDIDATE_TRANSFER.json')
        fig,axes=plt.subplots(1,2,figsize=(11,4));colors=['#3c78a8','#d28b35','#5c9974'];ordered=sorted([r for r in original['results'] if r['role']=='PDMS'],key=lambda r:(r['rank'],r['budget_factor']))
        match={r['id']:r for r in transfer['results']}
        for noise in range(3):
            axes[0].plot(range(len(ordered)),[r['oracle_by_noise'][noise]['standardized_pdms_gain'] for r in ordered],marker='o',color=colors[noise],label=f'S{noise}')
            axes[1].plot(range(len(ordered)),[match[r['id']]['S0_fixed_candidate_by_noise'][noise]['standardized_pdms_gain'] for r in ordered],marker='o',color=colors[noise],label=f'S{noise}')
        labels=[f"r{r['rank']} / {r['budget_factor']}x" for r in ordered]
        for ax in axes:ax.set_xticks(range(len(labels)),labels,rotation=40,ha='right');ax.set_ylabel('Standardized PDMS change (points)');ax.legend(frameon=False,ncol=3);ax.axhline(0,color='black',lw=.8)
        axes[0].set_title('Own-three-expert per-draw privileged Oracle');axes[1].set_title('Choose on S0, keep the same candidate on S1/S2')
        save(fig,'capacity_and_fixed_choice','同一correction-K3分组／fold0，rank与训练预算匹配；每库仅自己的3专家及Base。左右均含真实评分特权，右图固定S0具体选择，不重新挑噪声。延长训练的逐输出Oracle改进不等于固定选择迁移或部署路由改进。')
    manifest=dict(time=stamp(),status='REPRODUCIBLE_SCIENTIFIC_FIGURES_V2',figures=figures,sources=sources,formal_final_acceptance=False)
    atomic(directory/'MANIFEST.json',manifest);atomic(ROOT/'analysis/report_figures_v2/LATEST.json',dict(time=stamp(),path=str((directory/'MANIFEST.json').relative_to(ROOT)),sha256=sha(directory/'MANIFEST.json')))
    print(json.dumps(dict(path=str((directory/'MANIFEST.json').relative_to(ROOT)),figures=len(figures))))


if __name__=='__main__':main()
