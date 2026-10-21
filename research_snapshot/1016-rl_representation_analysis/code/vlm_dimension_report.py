"""Descriptive dimension slices of already scanned, frozen repair candidates.

No model collection, fitting, held-out selection or repair selection occurs.
CV maxima on unequal grids are exploratory and have a larger search budget.
"""
from common import *
import argparse
import numpy as np
from vlm_core import VOUT
from vlm_semantic import SEM
from vlm_selection import score
from vlm_space import METRICS
from repair_queue_v2 import atomic_unique as atomic

COMPONENTS=['vision','bridge','language','interface']
def component(block):return next(k for k in COMPONENTS if block.startswith(k))
def clean(values):return [float(x) if np.isfinite(x) else None for x in values]

def gather():
    found={};sources=[]
    for directory in [VOUT/'fits',SEM/'repair/fits']:
        for path in directory.glob('*.json'):
            value=read(path);fit=value.get('fit',value)
            if fit.get('status')!='PASS' or fit['config']['kind'] not in ['basis_residual','variance_residual']:continue
            spec=fit['spec'];confirmation=VOUT/'confirmation'/(fit['id']+'.json')
            if not confirmation.exists():continue
            record=dict(fit_id=fit['id'],component=component(fit['block']),spec=spec,
                confirmation=read(confirmation),fit_metadata_path=str(path.relative_to(ROOT)),
                fit_metadata_sha256=sha(path),semantic=str(SEM.relative_to(ROOT)) in fit['cell_proof_path'])
            if fit['id'] in found:assert found[fit['id']]['spec']==spec
            found[fit['id']]=record
    return list(found.values())

def grid(record):
    spec=record['spec'];source=(ROOT/spec['cell_proof_path']).parent.parent
    path=source/'scan/results'/(spec['cell']+'.json');result=read(path)
    assert sha(path)==spec['source_result_sha256']
    assert sha(ROOT/result['array_path'])==result['array_sha256']
    entries=read(source/'scan/CONFIGS.json');cc=int(spec['centering']=='pooled_centered')
    with np.load(ROOT/result['array_path']) as z:
        matrix=np.array(z['metrics'][cc]);valid=(z['status'][cc]==0).all(0)&~z['cutoff_degenerate'][cc].any(0)&np.isfinite(matrix[5,:,0])
    index=spec['config_index'];assert entries[index]==spec['config'] and valid[index]
    assert abs(matrix[5,index,0]-spec['metrics']['auc'])<1e-10
    return entries,matrix,valid,dict(path=str(path.relative_to(ROOT)),sha256=sha(path),array_path=result['array_path'],array_sha256=result['array_sha256'])

def main(a):
    setup('vlm_repair/dimension_report')
    records=gather();assert records
    canonical=read(VOUT/'FULL_GRID_SCHEDULE.json')['canonical'];complete=all((VOUT/'scan/receipts'/(t['id']+'.json')).exists() for t in canonical) and len(list((SEM/'scan/receipts').glob('*.json')))==64
    if a.require_complete:assert complete,'Canonical/corrected full grids are not all committed.'
    dest=VOUT/'dimension_snapshots'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S');dest.mkdir(parents=True,exist_ok=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':8,'axes.spines.top':False,'axes.spines.right':False})
    selected=[]
    for comp in COMPONENTS:
        eligible=[r for r in records if r['component']==comp]
        assert eligible,comp
        # Only the already frozen exploration spec is used to choose figures.
        selected.append(max(eligible,key=lambda r:(r['spec']['stable_cv_region'],score(r['spec']),r['spec'].get('neighbor_supported',0))))
    figures=[];source_proofs=[];all_slices=[];same_r=[]
    fig1,axes1=plt.subplots(4,3,figsize=(12,11),constrained_layout=True)
    fig2,axes2=plt.subplots(1,4,figsize=(14,4),constrained_layout=True)
    fig3,axes3=plt.subplots(1,4,figsize=(14,4),constrained_layout=True)
    heatmaps=[]
    for row,record in enumerate(selected):
        spec=record['spec'];cfg=spec['config'];entries,matrix,valid,proof=grid(record);source_proofs.append(proof)
        for col,field in enumerate(['ks','kf','r']):
            indices=[i for i,c in enumerate(entries) if c['kind']==cfg['kind'] and all(c[f]==cfg[f] for f in ['ks','kf','r'] if f!=field)]
            indices.sort(key=lambda i:entries[i][field]);xs=[entries[i][field] for i in indices]
            ys=[matrix[5,i,0] if valid[i] else np.nan for i in indices];ax=axes1[row,col]
            ax.plot(xs,ys,'o-',ms=3,color='#167d8d');ax.plot(cfg[field],spec['metrics']['auc'],'*',ms=10,color='#ce7638')
            equal=[(entries[i][field],matrix[5,i,0]) for i in indices if valid[i] and entries[i]['ks']==entries[i]['kf']]
            if equal:ax.scatter(*zip(*equal),s=42,facecolors='none',edgecolors='#333333',marker='s',zorder=4)
            ax.set_xscale('log',base=2);ax.set_xlabel(field+' (other dimensions fixed)');ax.set_ylabel('Session-CV AUROC')
            ax.set_title(record['component']+' / '+cfg['kind']+'\n'+','.join(f+'='+str(cfg[f]) for f in ['ks','kf','r'] if f!=field))
            all_slices.append(dict(fit_id=record['fit_id'],field=field,x=xs,auc=clean(np.asarray(ys)),other_dimensions={f:cfg[f] for f in ['ks','kf','r'] if f!=field},eligible=[bool(valid[i]) for i in indices]))
        vals=sorted({c['ks'] for c in entries if c['kind']==cfg['kind']});lookup={v:i for i,v in enumerate(vals)};heat=np.full((len(vals),len(vals)),np.nan)
        for i,c in enumerate(entries):
            if c['kind']==cfg['kind'] and c['r']==cfg['r'] and valid[i]:heat[lookup[c['kf']],lookup[c['ks']]]=matrix[5,i,0]
        ax=axes2[row];cm=plt.get_cmap('viridis').copy();cm.set_bad('#eeeeee');im=ax.imshow(heat,origin='lower',aspect='equal',vmin=.5,vmax=.8,cmap=cm);ax.plot(range(len(vals)),range(len(vals)),':',lw=.8,color='white')
        ax.plot(lookup[cfg['ks']],lookup[cfg['kf']],'*',color='#e95c24',ms=9)
        at=list(range(0,len(vals),2));ax.set(xticks=at,yticks=at,xticklabels=[vals[i] for i in at],yticklabels=[vals[i] for i in at],xlabel='ks',ylabel='kf',title=record['component']+' / r='+str(cfg['r']))
        ax.tick_params(axis='x',labelrotation=60);heatmaps.append(dict(fit_id=record['fit_id'],dimension_grid=vals,auc=[clean(v) for v in heat]))
        # Compare requested residual dimensions at fixed cell/family/centering.
        # Equal/unequal each selects CV score on its own valid grid; unequal has
        # more opportunities and cannot be called a controlled superiority test.
        compare=[]
        for r in sorted({c['r'] for c in entries if c['kind']==cfg['kind']}):
            for eq in [True,False]:
                ids=[i for i,c in enumerate(entries) if c['kind']==cfg['kind'] and c['r']==r and c['equal']==eq and valid[i]]
                if not ids:continue
                def value(i):return float(matrix[5,i,0]-.25*np.nanstd(matrix[:5,i,0])-.1*max(0.,.6-np.nanmin(matrix[:5,i,0])))
                i=max(ids,key=value);compare.append(dict(label='Equal' if eq else 'Unequal',r=r,config=entries[i],metrics={k:v for k,v in zip(METRICS,clean(matrix[5,i]))},fold_min=float(np.nanmin(matrix[:5,i,0])),grid_opportunities=len(ids)))
            for label,kind,rep in [('Success PCA','success_pca',None),('Failure PCA','failure_pca',None)]+[(f'Random{j}','random',j) for j in range(3)]:
                ids=[i for i,c in enumerate(entries) if c['kind']==kind and c.get('r')==r and (rep is None or c.get('replicate')==rep) and valid[i]]
                for i in ids:compare.append(dict(label=label,r=r,config=entries[i],metrics={k:v for k,v in zip(METRICS,clean(matrix[5,i]))},grid_opportunities=1))
        for i,c in enumerate(entries):
            if c['kind']=='full' and valid[i]:compare.append(dict(label='Full mean gap',r=None,config=c,metrics={k:v for k,v in zip(METRICS,clean(matrix[5,i]))},grid_opportunities=1))
        same_r.append(dict(fit_id=record['fit_id'],cell=spec['cell'],centering=spec['centering'],family=cfg['kind'],rows=compare))
        ax=axes3[row]
        styles=[('Equal','#167d8d','-'),('Unequal','#ce7638','-'),('Success PCA','#7756a2','--'),('Failure PCA','#789557','--'),('Random0','#888888',':'),('Random1','#aaaaaa',':'),('Random2','#555555',':')]
        for label,color,linestyle in styles:
            values=[v for v in compare if v['label']==label];ax.plot([v['r'] for v in values],[v['metrics']['auc'] for v in values],color=color,ls=linestyle,marker='o',ms=2,label=label)
        for value in compare:
            if value['label']=='Full mean gap':ax.axhline(value['metrics']['auc'],color='black',ls='--',lw=.8,label='Full mean gap')
        ax.set_xscale('log',base=2);ax.set(xlabel='Final residual dimension r',ylabel='Session-CV AUROC',title=record['component']+' / same-r comparison')
        if row==0:ax.legend(fontsize=6)
    fig2.colorbar(im,ax=axes2,shrink=.7,label='Session-CV AUROC (fixed final r)')
    def save(fig,name,caption):
        p=dest/(name+'.png');fig.savefig(p,dpi=150,bbox_inches='tight');fig.savefig(p.with_suffix('.svg'),bbox_inches='tight');plt.close(fig)
        figures.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p),caption=caption))
    save(fig1,'dimension_slices','固定另外两项，分别扫描ks、kf、r。星号是仅按原探索CV选择的已冻结修复候选；空心方框为等维交点；缺失为秩限制、退化或不可评估，不连作有效格点。每个组件各选一个现有残差代表，不追加拟合/修复选择。')
    save(fig2,'main_space_grids','相同最终残差维数r下的ks×kf探索CV格点；白色虚线为等维主空间，星号为冻结代表，灰格为不可评估/退化。四图可有不同r或构造，仅用于各自邻域观察，不直接跨图判优。')
    save(fig3,'matched_final_rank','固定cell、中心化和残差构造，按相同最终r比较等维、非等维网格及PCA/三随机/全维均值差对照。等维/非等维曲线各自按CV分数选点，非等维搜索机会更多；是探索性包络，不是同预算或独立确认的优越性检验。完整AP、标准化差异、会话稳定性与格点机会数另存表。')
    result=dict(status='PLOTTED_NOT_VISUALLY_ACCEPTED',time=stamp(),complete=complete,no_new_model_collection=True,no_new_fit_or_repair_selection=True,
        chosen_for_display_only_by_exploration_cv=True,no_test_access=True,selected=selected,all_frozen_residual_records=records,
        slices=all_slices,heatmaps=heatmaps,same_final_r=same_r,source_proofs=source_proofs,figures=figures,
        canonical_completed=sum((VOUT/'scan/receipts'/(t['id']+'.json')).exists() for t in canonical),canonical_total=len(canonical),
        corrected_full_completed=len(list((SEM/'scan/receipts').glob('*.json'))),corrected_full_total=64,
        scope='Already frozen residual repair candidates; no claim that every token Cartesian grid has completed')
    atomic(dest/'SUMMARY.json',result);atomic(VOUT/'DIMENSION_REPORT_LATEST.json',dict(path=str((dest/'SUMMARY.json').relative_to(ROOT))))
    print('DIMENSION_REPORT_PLOTTED',str(dest.relative_to(ROOT)),len(records),'complete',complete,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--require-complete',action='store_true');main(p.parse_args())
