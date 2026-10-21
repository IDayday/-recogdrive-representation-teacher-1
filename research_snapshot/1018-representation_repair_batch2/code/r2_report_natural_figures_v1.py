"""Standalone figures from fully accepted locked natural evaluations only."""
from r2_common import *


def main():
    setup('report_natural_figures',threads=2)
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':9,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
    data={};sources=[]
    def get(path):
        p=ROOT/path;sources.append(dict(path=path,sha256=sha(p)));return read(p)
    pack=get('provenance/final_confirmation/PACK.json');configs=[p for p in pack['policies'] if p['kind']!='Base']
    for mode in ['validation','test']:
        proof=get('runs/frozen_natural_'+mode+'_batch2_three_roles_v1/AGENT_FINAL_ACCEPTANCE_V1.json')
        assert proof['status']=='PASS_COMPLETE_FROZEN_NATURAL_'+mode.upper()
        data[mode]=(get(proof['assessment']['path']),get(proof['statistics']['path']))
    folder=ROOT/'analysis/report_natural_figures'/stamp().replace(':','');folder.mkdir(parents=True,exist_ok=False)
    figures=[]
    def save(fig,name,caption):
        fig.tight_layout()
        for ext in ['png','svg']:fig.savefig(folder/(name+'.'+ext),dpi=170,bbox_inches='tight')
        plt.close(fig);figures.append(dict(name=name,png=str((folder/(name+'.png')).relative_to(ROOT)),svg=str((folder/(name+'.svg')).relative_to(ROOT)),caption=caption))
    labels=[('safe' if c['selection_role']=='Safety' else 'PDMS' if c['selection_role']=='PDMS' else 'robust')+' f'+str(c['fit_replicate']) for c in configs]
    x=np.array([i+i//3 for i in range(len(configs))]);colors=['#577f99','#bd7650','#67957a']
    fig,axes=plt.subplots(1,2,figsize=(12,4.3))
    for ax,(mode,title) in zip(axes,[('validation','Natural validation'),('test','Whole navtest')]):
        a,stats=data[mode];lookup={r['id']:r for r in stats['results']}
        for i,c in enumerate(configs):
            r=lookup[c['id']];mean=r['mean_PDMS_gain'];lo,hi=r['session_bootstrap_95']
            ax.plot([x[i],x[i]],[lo,hi],color=colors[i//3],lw=1.8)
            ax.scatter(x[i],mean,color=colors[i//3],s=30,zorder=3)
        ax.axhline(0,color='black',lw=.8);ax.set_xticks(x,labels,rotation=35,ha='right');ax.set_ylabel('PDMS change (points)');ax.set_title(title)
    save(fig,'natural_actual_gains','冻结三类策略的三次独立拟合均保留。点为实际自然总体PDMS变化，线为10,000次会话bootstrap的逐项95%区间；是否通过冻结12项Holm比较另列。不是把独立拟合平均成部署集成。')
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    styles=[('actual','Actual policy','#555f69','o'),('actual_candidate_oracle','Own-K + Base Oracle','#3a7bab','o'),('S0_fixed_candidate_cross_noise','S0-fixed expert','#609971','s'),('matched','Matched Base resampling','#bf8a35','^')]
    for ax,(mode,title) in zip(axes,[('validation','Natural validation'),('test','Whole navtest')]):
        a,_=data[mode]
        for index,(name,label,color,marker) in enumerate(styles):
            values=[]
            for config in configs:
                ident=config['id'];d=a['privileged_diagnostics'][ident]
                result=a['results'][ident] if name=='actual' else next(v for k,v in d.items() if k.startswith('matched_')) if name=='matched' else d[name]
                values.append(result['mean_PDMS_gain'])
            ax.scatter(x+(index-1.5)*.12,values,label=label,color=color,marker=marker,s=26)
        ax.axhline(0,color='black',lw=.8);ax.set_xticks(x,labels,rotation=35,ha='right');ax.set_ylabel('PDMS change (points)');ax.set_title(title)
    axes[0].legend(frameon=False,fontsize=8,ncol=2,loc='upper left')
    save(fig,'natural_oracle_controls','每位策略使用自身实际K个专家及Base，S0选定专家在后续噪声固定，另列K+1次Base候选机会控制；不将不同拟合或角色候选合并。Oracle点均含真实评分特权，未画置信区间，不能当作可部署或学生成绩。')
    record=dict(status='ACCEPTED_FROZEN_NATURAL_FIGURES',time=stamp(),figures=figures,sources=sources,source_sha256=sha(Path(__file__)))
    atomic(folder/'MANIFEST.json',record);atomic(ROOT/'analysis/report_natural_figures/LATEST.json',dict(time=stamp(),path=str((folder/'MANIFEST.json').relative_to(ROOT)),sha256=sha(folder/'MANIFEST.json')))
    print(json.dumps(dict(path=str((folder/'MANIFEST.json').relative_to(ROOT)),figures=2)))


if __name__=='__main__':main()
