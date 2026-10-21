"""Standalone reproducible research figures from verified stored summaries.

Missing family/K cells remain missing. These figures do not select final models.
"""
from r2_common import *


def main():
    setup('report_figures')
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from collections import defaultdict
    plt.rcParams.update({'font.size':10,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
    sources=[]
    def source(path):
        value=read(ROOT/path);sources.append(dict(path=path,sha256=sha(ROOT/path)));return value
    pointer=source('analysis/extended_cv_reviews/LATEST.json');assert sha(ROOT/pointer['path'])==pointer['sha256'];review=source(pointer['path']);full=[v for v in review['recipes'] if v['complete_five_folds']]
    directory=ROOT/'analysis/report_figures'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%f');directory.mkdir(parents=True,exist_ok=False);figures=[]
    def save(fig,name,caption):
        fig.tight_layout();fig.savefig(directory/(name+'.svg'),bbox_inches='tight');fig.savefig(directory/(name+'.png'),dpi=180,bbox_inches='tight');plt.close(fig)
        figures.append(dict(name=name,svg=str((directory/(name+'.svg')).relative_to(ROOT)),png=str((directory/(name+'.png')).relative_to(ROOT)),caption=caption))
    # Completion is shown separately from effect size: absent values are never zero.
    families=['representation','response','correction'];image=np.full((3,7),np.nan);counts=np.zeros((3,7),int)
    for f,family in enumerate(families):
        for k in range(2,9):
            candidates=[v for v in full if v['system']==f'{family}_K{k}_seed0' and v['method'] in ['candidate_selector','warm_hard']]
            counts[f,k-2]=len(candidates)
            if candidates:image[f,k-2]=max(v['standardized_pdms_gain'] for v in candidates)
    fig,ax=plt.subplots(figsize=(9,3.1));limit=max(.1,float(np.nanmax(np.abs(image)))) if np.isfinite(image).any() else .1
    plot=ax.imshow(np.ma.masked_invalid(image),cmap='RdBu_r',vmin=-limit,vmax=limit,aspect='auto')
    for f in range(3):
        for j in range(7):ax.text(j,f,'pending' if not counts[f,j] else f'{image[f,j]:+.3f}\nn={counts[f,j]}',ha='center',va='center',fontsize=9)
    ax.set_xticks(range(7),list(range(2,9)));ax.set_yticks(range(3),families);ax.set_xlabel('Number of nonzero experts K (identity is additional)');ax.set_title('Complete five-fold hard/candidate recipes: exploratory maximum');fig.colorbar(plot,ax=ax,label='Class-standardized PDMS change (points)')
    save(fig,'primary_K_completion_and_effect','只显示已经齐五折的硬路由／完整候选选择；格内为探索最大值及配方数，尚未完成为空白。不同K和方法覆盖不齐时，不能将此图用作公平优劣或稳定提分结论。')
    # One fixed per-policy candidate set, never an Oracle over different roles.
    banks=[]
    for path in sorted((ROOT/'analysis/held_fivefold_potential').glob('*/SUMMARY.json')):
        d=source(str(path.relative_to(ROOT)));assert d['folds']==[0,1,2,3,4]
        if 'PDMS_denoising' in d['roles']:banks.append(d)
    if banks:
        fig,axes=plt.subplots(1,2,figsize=(11,4.2));positions=np.arange(len(banks));width=.22
        for n in range(3):
            overall=[b['roles']['PDMS_denoising']['candidate_oracle_standardized_gain_by_noise'][n] for b in banks]
            stable=[b['roles']['PDMS_denoising']['observed_all3_failure']['conditional_gain_by_draw'][n] for b in banks]
            for ax,values in zip(axes,[overall,stable]):ax.bar(positions+(n-1)*width,values,width,label=f'S{n}',alpha=.82)
        labels=[b['system'].replace('_K2_seed0','').replace('correction_','corr_') for b in banks]
        for ax in axes:ax.set_xticks(positions,labels,rotation=18,ha='right');ax.axhline(0,color='black',lw=.8);ax.set_ylabel('PDMS change (points)');ax.legend(frameon=False,ncol=3)
        axes[0].set_title('Privileged own-K Oracle: standardized panel');axes[1].set_title('Same Oracle: observed all-three-draw failures')
        save(fig,'own_K_oracle_and_stable_failures','逐场景真实评分选择本策略K个专家或Base，仅为特权诊断；左侧按自然质量比例标准化，右侧为观察三次均失败的条件子集，量纲相同而总体不同。三个采样噪声属于同一场景，不能当独立样本。')
    # Plot every completed auxiliary pilot, including identity and negative results.
    acceptance=ROOT/'provenance/AUXILIARY_COMPLETED_PANELS_ACCEPTANCE.json'
    if acceptance.exists():
        proof=source(str(acceptance.relative_to(ROOT)));assert sha(ROOT/proof['path'])==proof['sha256'];aux=source(proof['path']);groups=[('Success data / training budget',[v['metrics']['weighted_pdms_gain'] for v in aux['large_success_policies']]),('Ego-history / zero tokens',[v['metrics']['weighted_pdms_gain'] for v in aux['state_policies']]),('Stored-prediction ensembles',[v['mean_gain'] for v in aux['ensemble_policies']])]
        fig,ax=plt.subplots(figsize=(9,3.8));rng=np.random.default_rng(2026101818)
        for j,(label,values) in enumerate(groups):
            ax.scatter(j+rng.uniform(-.15,.15,len(values)),values,s=23,alpha=.68,color=['#4779aa','#a17036','#448873'][j],edgecolors='none')
            ax.plot([j-.2,j+.2],[np.median(values)]*2,color='black',lw=2);ax.text(j,max(values)+.012,f'n={len(values)}',ha='center')
        ax.axhline(0,color='black',lw=.8,ls='--');ax.set_xticks(range(3),[a[0] for a in groups]);ax.set_ylabel('Class-standardized PDMS change (points)');ax.set_title('All completed one-fold mechanism pilots (shared scenes / expert bank)')
        save(fig,'all_auxiliary_pilot_outcomes','所有已完成的辅助对照均展示，包含零干预与负结果。共享同一探索留出折、专家库和部分暖启动，点数是策略数量，不是独立实验或独立拟合次数。')
    manifest=dict(time=stamp(),status='REPRODUCIBLE_FIGURES_FROM_CURRENT_VERIFIED_SNAPSHOT',figures=figures,sources=sources,full_cv_recipes=len(full),partial_cv_recipes=review['partial_recipes'],formal_final_acceptance=False)
    atomic(directory/'MANIFEST.json',manifest);atomic(ROOT/'analysis/report_figures/LATEST.json',dict(time=stamp(),path=str((directory/'MANIFEST.json').relative_to(ROOT)),sha256=sha(directory/'MANIFEST.json')));print(json.dumps(dict(path=str((directory/'MANIFEST.json').relative_to(ROOT)),figures=len(figures)),ensure_ascii=False))


if __name__=='__main__':main()
