"""Plot every fixed quality/random control basis; never pool best candidates."""
from r2_common import *


def main():
    setup('space_control_figure')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    proof=read(ROOT/'provenance/SPACE_CONTROL_COMPLETE_PANEL_ACCEPTANCE.json');latest=proof['summary'];assert sha(ROOT/latest['path'])==latest['sha256'];d=read(ROOT/latest['path']);assert len(d['results'])==100
    directory=ROOT/'analysis/space_control_summary/figures'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%f');directory.mkdir(parents=True,exist_ok=False)
    fig,axes=plt.subplots(2,2,figsize=(10,7),sharex=True,sharey=True);colors={'global_quality_residual':'#2b64a0','own_group_quality_residual':'#438d86','Haar_random':'#c27b29'}
    for row,cap in enumerate([.02,.1]):
        for col,block in enumerate(['interface_pre','interface_post']):
            ax=axes[row,col];own=[v for v in d['results'] if v['block']==block and v['cap']==cap];families={}
            for v in own:
                if v['space']=='full':
                    ax.axhline(v['mean_transfer_gain'],color='#a94747',ls=':',lw=2);continue
                key=digest(dict(space=v['space'],basis_config=v['basis_config']));families.setdefault(key,[]).append(v)
            for group in families.values():
                values=sorted(group,key=lambda v:v['rank']);assert [v['rank'] for v in values]==[8,32,128];spec=values[0];kind=spec['space'];config=spec['basis_config'];style='--' if config.get('centered',False) or config.get('replicate',0)==1 else '-'
                ax.plot(range(3),[v['mean_transfer_gain'] for v in values],color=colors[kind],ls=style,marker='o',alpha=.6 if kind=='own_group_quality_residual' else .9,lw=1.4)
            ax.set_title(f'{block}: relative norm cap {cap:.2f}');ax.set_xticks(range(3),[8,32,128]);ax.axhline(0,color='black',lw=.6);ax.grid(axis='y',alpha=.15);ax.set_ylim(-2,72)
            if row==1:ax.set_xlabel('Subspace rank r')
    handles=[Line2D([0],[0],color=colors[k],lw=2,label=label) for k,label in [('global_quality_residual','Global quality (2 centers)'),('own_group_quality_residual','Own-group quality (4 bases)'),('Haar_random','Random (2 replicas)')]]+[Line2D([0],[0],color='#a94747',ls=':',lw=2,label='Channel-full finite optimizer')]
    fig.legend(handles=handles,loc='lower center',ncol=2,frameon=False,bbox_to_anchor=(.5,-.005));fig.suptitle('Matched 24-case privileged control: all fixed bases, equal optimization budget');fig.supylabel('Fixed-delta S1/S2 transfer PDMS gain (points)');fig.tight_layout(rect=(.02,.085,1,.965));svg=directory/'matched_space_fixed_noise_transfer.svg';png=svg.with_suffix('.png');fig.savefig(svg,bbox_inches='tight');fig.savefig(png,dpi=180,bbox_inches='tight');plt.close(fig)
    manifest=dict(time=stamp(),svg=str(svg.relative_to(ROOT)),png=str(png.relative_to(ROOT)),summary=latest,code_sha256=sha(Path(__file__)),acceptance_sha256=sha(ROOT/'provenance/SPACE_CONTROL_COMPLETE_PANEL_ACCEPTANCE.json'),caption='24个预先指定、三次观察均失败且实际GT>90的探索场景；每条曲线是固定空间，未将6个质量空间的最优值与2个随机空间的最优值混比。相同24步优化、范数上限和S0真实评分选择机会；展示固定扰动在S1/S2的转移，不是可部署成绩。共同中心化／未中心化与两个随机重复均保留。通道全维也只是有限优化预算下的结果。')
    atomic(directory/'MANIFEST.json',manifest);atomic(ROOT/'analysis/space_control_summary/FIGURE_LATEST.json',dict(time=stamp(),path=str((directory/'MANIFEST.json').relative_to(ROOT)),sha256=sha(directory/'MANIFEST.json')));print(str(png))


if __name__=='__main__':main()
