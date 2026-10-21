"""Plot frozen exploration-selected readouts and their session-held-out confirmation."""
from common import *
import numpy as np
from vlm_core import VOUT
from vlm_semantic import SEM
from vlm_scan import metadata
from vlm_selection import score
from repair_queue_v2 import atomic_unique as atomic

def component(block):
    return next((s for s in ['vision','bridge','interface'] if block.startswith(s)),'language')

def main():
    setup('vlm_repair/readout_report')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from threadpoolctl import threadpool_limits
    threadpool_limits(2)
    dest=VOUT/'readout_snapshots'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S');dest.mkdir(parents=True,exist_ok=False)
    fits={}
    for folder in [VOUT/'development/completed_fits',VOUT/'residual_development/fits',SEM/'repair/fits']:
        for p in folder.glob('*.json'):
            obj=read(p);fit=obj['fit'];confirmation=obj['confirmation'];assert confirmation['fit_sha256']==fit['sha256']
            fits[fit['id']]=dict(fit=fit,confirmation=confirmation,source=str(p.relative_to(ROOT)))
    plan=read(VOUT/'PIVOT_PLAN.json')['blocks'];order=[b['name'] for b in plan];figures=[]
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    def save(fig,name,caption):
        fig.tight_layout();path=dest/(name+'.png');fig.savefig(path,dpi=150,bbox_inches='tight');fig.savefig(path.with_suffix('.svg'),bbox_inches='tight');plt.close(fig)
        figures.append(dict(path=str(path.relative_to(ROOT)),sha256=sha(path),caption=caption))
    families=[('Low r',lambda f:f['config']['kind'] not in ['full','success_pca128_shrink_qda'] and f['r']<=16,'#177b8b'),
              ('Middle r',lambda f:f['config']['kind'] not in ['full','success_pca128_shrink_qda'] and 16<f['r']<=128,'#5175ad'),
              ('High r',lambda f:f['config']['kind'] not in ['full','success_pca128_shrink_qda'] and f['r']>128,'#855aa2'),
              ('QDA128',lambda f:f['config']['kind']=='success_pca128_shrink_qda','#ce7638'),
              ('Full mean gap',lambda f:f['config']['kind']=='full','#555555')]
    selected=[];fig,axes=plt.subplots(4,1,figsize=(14,12),gridspec_kw={'height_ratios':[2,1.2,2.2,1.2]})
    for ax,c in zip(axes,['vision','bridge','language','interface']):
        blocks=[b for b in order if component(b)==c]
        for label,predicate,color in families:
            cv=[];held=[]
            for block in blocks:
                available=[o for o in fits.values() if o['fit']['block']==block and predicate(o['fit'])]
                best=max(available,key=lambda o:score(o['fit']['spec'])) if available else None
                cv.append(best['fit']['spec']['metrics']['auc'] if best else np.nan);held.append(best['confirmation']['metrics']['auc'] if best else np.nan)
                if best:selected.append(dict(component=c,block=block,family=label,fit_id=best['fit']['id'],cv_auc=cv[-1],heldout_auc=held[-1],source=best['source']))
            ax.plot(range(len(blocks)),cv,color=color,lw=1.2,label=label+' CV');ax.plot(range(len(blocks)),held,color=color,lw=1.,ls='--',alpha=.85)
        ax.axhline(.5,color='#999999',lw=.6);ax.set(xticks=range(len(blocks)),xticklabels=blocks,ylabel='AUROC',title=c+' | solid: session CV; dashed: frozen hold-out');ax.tick_params(axis='x',labelrotation=65);ax.set_ylim(.45,.85)
    axes[0].legend(ncol=5,fontsize=8,loc='upper left')
    save(fig,'layer_readouts','按层比较探索会话交叉验证（实线）和冻结后会话留出（虚线）。每个层/维数段代表按探索CV选择，不在留出集选最优；QDA为方差读出诊断，不能当作已获相邻r支持的残差区域。')
    rows,q,exp,fold,sessions,high=metadata();summaries=[];fig,axes=plt.subplots(1,4,figsize=(15,3.6))
    for ax,c in zip(axes,['vision','bridge','language','interface']):
        candidates=[o for o in fits.values() if component(o['fit']['block'])==c and o['fit']['config']['kind']!='success_pca128_shrink_qda']
        if not candidates:continue
        chosen=max(candidates,key=lambda o:(o['fit']['spec']['stable_cv_region'],score(o['fit']['spec'])));f=chosen['fit'];spec=f['spec'];proof=read(ROOT/f['cell_proof_path']);x=np.load(ROOT/proof['path'],mmap_mode='r')
        with np.load(ROOT/f['path']) as a:
            w=np.asarray(a['basis'],dtype=np.float64)@(np.asarray(a['mf'],dtype=np.float64)-a['mh']);mid=np.asarray(a['center'],dtype=np.float64)+np.asarray(a['basis'],dtype=np.float64)@((a['mh']+a['mf'])*.5)
        with np.load(ROOT/spec['moment']['path']) as m:
            cov=.5*(m['gs']/m['ns']-np.outer(m['ss']/m['ns'],m['ss']/m['ns'])+m['gf']/m['nf']-np.outer(m['sf']/m['nf'],m['sf']/m['nf']));scale=np.sqrt(max(float(w@cov@w),1e-24))
        use=(~exp)&np.isfinite(x[:,0])&((q<.7)|(q>.9));idx=np.flatnonzero(use);pred=(np.asarray(x[idx],dtype=np.float64)-mid)@w/scale
        lo,hi=np.quantile(pred,[.005,.995]);bins=np.linspace(lo,hi,45)
        for mask,label,color in [(q[idx]>.9,'PDMS >90','#177b8b'),(q[idx]<.7,'PDMS <70','#bb4c59')]:ax.hist(pred[mask],bins=bins,density=True,histtype='step',lw=1.6,color=color,label=label)
        ax.set(title=c+' | '+f['block']+' / r'+str(f['r']),xlabel='Frozen mean-gap readout (training units)',ylabel='Density')
        summaries.append(dict(component=c,fit_id=f['id'],cell=f['cell'],cv=spec['metrics'],heldout=chosen['confirmation']['metrics'],training_standardizer=True,displayed_quantile_range=[.005,.995],cases=len(idx)))
    axes[0].legend(fontsize=8)
    save(fig,'heldout_distributions','各组件探索CV选出的均值差代表在独立会话留出集的分布；标准化只由探索充分统计确定。为可读性仅绘0.5%–99.5%分位区间，指标仍计算全体留出样本。这种差异不证明可修复因果机制。')
    # Explicitly expose pooled discrimination versus within-session stability.
    hypotheses=sorted(fits.values(),key=lambda o:o['confirmation']['metrics']['session_p'] if o['confirmation']['metrics']['session_p'] is not None else 1.)
    assert len(hypotheses)<=1000;adjusted={};maximum=0.
    for i,o in enumerate(hypotheses):
        p=o['confirmation']['metrics']['session_p'];maximum=max(maximum,min(1.,(1. if p is None else p)*(1000-i)));adjusted[o['fit']['id']]=maximum
    diagnostics=[]
    for c in ['vision','bridge','language','interface']:
        for label,is_qda in [('Mean gap',False),('QDA128',True)]:
            group=[o for o in fits.values() if component(o['fit']['block'])==c and (o['fit']['config']['kind']=='success_pca128_shrink_qda')==is_qda]
            if not group:continue
            o=max(group,key=lambda x:score(x['fit']['spec']));f=o['fit'];v=o['confirmation']['metrics'];diagnostics.append(dict(label=c+' / '+label,fit_id=f['id'],cell=f['cell'],cv=f['spec']['metrics'],heldout=v,heldout_session_p_holm_planned1000=adjusted[f['id']]))
    fig,axes=plt.subplots(1,3,figsize=(13,4.4));ys=np.arange(len(diagnostics))
    axes[0].barh(ys,[r['heldout']['auc'] for r in diagnostics],color='#5175ad');axes[0].set(yticks=ys,yticklabels=[r['label'] for r in diagnostics],xlim=(.45,.85),xlabel='Pooled held-out AUROC')
    axes[1].barh(ys,[r['heldout']['session_positive_fraction'] for r in diagnostics],color='#177b8b');axes[1].axvline(.65,color='#bb4c59',ls='--',lw=1);axes[1].set(yticks=ys,yticklabels=[],xlim=(0,1),xlabel='Sessions with positive quality gap')
    ps=[max(r['heldout_session_p_holm_planned1000'],1e-12) for r in diagnostics]
    axes[2].barh(ys,[-np.log10(p) for p in ps],color='#ce7638');axes[2].axvline(-np.log10(.05),color='#bb4c59',ls='--',lw=1);axes[2].set(yticks=ys,yticklabels=[],xlabel='-log10(Holm p), planned family 1000')
    for ax in axes:ax.invert_yaxis()
    save(fig,'session_stability','总体可分与会话内稳定分开检查。各组件的均值差/QDA代表只按探索CV选择；第二图红线为65%会话方向一致，第三图按预设最多1000个冻结读出作保守Holm（未算项视p=1）。总体AUROC较高不保证会话内方向稳定，也不保证可修复。')
    atomic(dest/'SUMMARY.json',dict(status='PLOTTED_NOT_VISUALLY_ACCEPTED',time=stamp(),fits=len(fits),selected=selected,distribution_representatives=summaries,figures=figures,
        pooled_vs_session_diagnostics=diagnostics,confirmation_multiplicity='Holm with planned family 1000 and uncomputed p=1',
        actual_full_grid_cells=len(list((VOUT/'scan/receipts').glob('*.json'))),planned_full_grid_cells=2272,
        missing_corrected_semantic_cells=not (SEM/'CACHE_COMPLETE.json').exists(),no_test_access=True,
        canonical_report_not_modified=True))
    atomic(VOUT/'READOUT_REPORT_LATEST.json',dict(path=str((dest/'SUMMARY.json').relative_to(ROOT))))
    print('READOUT_FIGURES_READY',str(dest.relative_to(ROOT)),flush=True)

if __name__=='__main__':main()
