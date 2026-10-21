"""Show every quadratic space control, rather than only a selected favorable point."""
from common import *
import numpy as np
from vlm_core import VOUT
from vlm_qda_controls_v2 import OUT
from repair_queue_v2 import atomic_unique as atomic

def main():
    setup('vlm_repair/qda_report')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    protocol=read(OUT/'PROTOCOL.json');sites=[read(OUT/'results'/(s['fit']['cell']+'.json')) for s in protocol['sites']];joint=read(ROOT/read(OUT/'JOINT_LATEST.json')['path']);assert joint['all_qda_control_sites_complete']
    adjusted={r['id']:r['p_holm_planned1000'] for r in joint['heldout_confirmation']};dest=OUT/'report_snapshots'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S');dest.mkdir(parents=True,exist_ok=False);figures=[];rows=[]
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    for phase in ['cv','heldout']:
        fig,axes=plt.subplots(1,4,figsize=(15,3.6))
        for ax,site in zip(axes,sites):
            values=site['records'];rs=[64,96,128,192,256]
            for kind,j,label,color,style in [('success_pca',None,'Success PCA','#177b8b','-'),('random',0,'Random0','#888888','--'),('random',1,'Random1','#aaaaaa',':'),('random',2,'Random2','#555555','-.')]:
                chosen=[next(r for r in values if r['config']==dict(kind=kind,r=n,replicate=j)) for n in rs];ax.plot(rs,[r[phase]['auc'] for r in chosen],style,color=color,marker='o',ms=3,label=label)
                if phase=='cv' and kind=='success_pca':
                    with np.load(ROOT/site['array_path']) as z:m=z['fold_metrics'];indices=[values.index(r) for r in chosen];lo=np.nanmin(m[:,indices,0],axis=0);hi=np.nanmax(m[:,indices,0],axis=0)
                    ax.fill_between(rs,lo,hi,color=color,alpha=.12)
            full=next(r for r in values if r['config']['kind']=='full');ax.axhline(full[phase]['auc'],color='black',ls='--',lw=1,label='Full QDA')
            ax.set(xticks=rs,xlabel='Subspace dimension',ylabel='AUROC',title=site['site']['component']+' / '+phase,ylim=(.45,.95));ax.tick_params(axis='x',labelrotation=40)
        axes[0].legend(fontsize=7);fig.tight_layout();path=dest/(phase+'.png');fig.savefig(path,dpi=150,bbox_inches='tight');fig.savefig(path.with_suffix('.svg'),bbox_inches='tight');plt.close(fig)
        caption=('探索会话CV' if phase=='cv' else '冻结后会话留出')+'：四个地点均按原探索CV冻结。各r均用相同收缩QDA比较成功PCA、3个随机空间及全维；没有按留出结果选最好点。CV浅色带为五折最小—最大，不是置信区间。这些读出对照不改变原修复选择。'
        figures.append(dict(path=str(path.relative_to(ROOT)),sha256=sha(path),caption=caption))
    for site in sites:
        for r in site['records']:
            ident=site['site']['source_existing_confirmation'] if r['config']==dict(kind='success_pca',r=128,replicate=None) else r['id']
            rows.append(dict(component=site['site']['component'],cell=r['cell'],config=r['config'],cv=r['cv'],heldout=r['heldout'],secondary_seeds=r['secondary_seeds'],p_holm_planned1000=adjusted[ident],parent_pca128_original_confirmation=ident!=r['id']))
    atomic(dest/'SUMMARY.json',dict(status='PLOTTED_NOT_VISUALLY_ACCEPTED',time=stamp(),figures=figures,all_controls=rows,joint_correction_path=read(OUT/'JOINT_LATEST.json')['path'],no_policy_selection_change=True))
    atomic(OUT/'REPORT_LATEST.json',dict(path=str((dest/'SUMMARY.json').relative_to(ROOT))));print('QDA_CONTROL_FIGURES_READY',str(dest.relative_to(ROOT)),flush=True)

if __name__=='__main__':main()
