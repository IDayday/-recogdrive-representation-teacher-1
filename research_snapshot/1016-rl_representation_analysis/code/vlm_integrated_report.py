"""Integrate accepted upstream repairs and all-method bounds into the single report.

Requires actual final inference/independent rescoring, completed ungated
diagnostics and current source snapshots. This file does not run GPU work.
"""
from common import *
import argparse,base64,html,re
import numpy as np
from vlm_core import VOUT
from vlm_semantic import SEM
from repair_queue_v2 import atomic_unique as atomic
from candidate_repair_report import table

def esc(x):return html.escape(str(x))
def num(x,d=4):return '—' if x is None else f'{x:+.{d}f}'
def embedded(path,caption):
    return '<figure><img src="data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()+'" alt="'+esc(caption)+'"><figcaption>'+esc(caption)+'</figcaption></figure>'

def main(a):
    setup('vlm_repair/integrated_report')
    assert read(VOUT/'final/SCIENTIFIC_ACCEPTANCE.json')['status']=='PASS'
    assert read(VOUT/'final/BASE_TRAJECTORY_ACCEPTANCE.json')['status']=='PASS'
    assert read(VOUT/'UNGATED_TEST_DIAGNOSTICS_COMPLETE.json')['status']=='PASS'
    sem_done=(SEM/'repair/SCIENTIFIC_ACCEPTANCE.json').exists();no_sem=(SEM/'repair/NO_COMPETITIVE_CANDIDATES.json').exists();assert sem_done or no_sem
    if sem_done:assert read(SEM/'repair/BASE_TRAJECTORY_ACCEPTANCE.json')['status']=='PASS'
    assert read(SEM/'CACHE_COMPLETE.json')['status']=='PASS'
    assert read(SEM/'CACHE_ACCEPTANCE.json')['status']=='PASS'
    full_accept_pointer=read(SEM/'FULL_ANALYSIS_ACCEPTANCE_LATEST.json')
    full_accept_path=ROOT/full_accept_pointer['path']
    assert sha(full_accept_path)==full_accept_pointer['sha256']
    assert read(full_accept_path)['status']=='PASS' and len(read(full_accept_path)['checks'])==128
    for kind in ['rapid','scan']:assert len(list((SEM/kind/'receipts').glob('*.json')))==64
    canonical=read(VOUT/'FULL_GRID_SCHEDULE.json')['canonical'];assert all((VOUT/'scan/receipts'/(t['id']+'.json')).exists() for t in canonical)
    stats_path=sorted((VOUT/'statistics').glob('*/FINAL_STATISTICS.json'))[-1];stats=read(stats_path)
    assert stats['semantic_complete']==sem_done
    readout_path=ROOT/read(VOUT/'READOUT_REPORT_LATEST.json')['path'];readout=read(readout_path)
    assert not readout['missing_corrected_semantic_cells']
    oracle_path=ROOT/read(VOUT/'ORACLE_POLICY_GROUPS_LATEST.json')['path'];oracle=read(oracle_path)
    pools=[p for p in oracle['compatible_pools'] if p['cases']==12146 and p['seeds']==[0,1,2,3,4]];assert len(pools)==1;pool=pools[0]
    assert 'vlm_ungated_primary__failure_gated' in pool['panels']
    if sem_done:assert 'vlm_ungated_semantic__failure_gated' in pool['panels']
    multipath=sorted((VOUT/'multiplicity').glob('*/SUMMARY.json'))[-1];multiplicity=read(multipath)
    assert multiplicity.get('all_qda_control_sites_complete'), 'Refresh joint correction with vlm_qda_joint.py after the final main snapshot.'
    qda_path=ROOT/read(VOUT/'qda_controls/REPORT_LATEST.json')['path'];qda=read(qda_path)
    dimension_path=ROOT/read(VOUT/'DIMENSION_REPORT_LATEST.json')['path'];dimension=read(dimension_path)
    assert dimension['complete'], 'Refresh dimension slices after canonical and corrected grids finish.'
    prior_path=ROOT/read(VOUT/'PRIOR_REFERENCE_LATEST.json')['path'];prior=read(prior_path)
    source=ROOT/'candidate_repair_v1/report_versions/final_v2/report.html';assert sha(source)==read(ROOT/'candidate_repair_v1/REPORT_ACCEPTANCE.json')['report_sha256']
    dest=VOUT/'report_versions'/a.version;dest.mkdir(parents=True,exist_ok=False);figs=dest/'figures';figs.mkdir();proofs=[];images={}
    for item in readout['figures']:
        path=ROOT/item['path'];assert sha(path)==item['sha256'];images[path.stem]=embedded(path,item['caption']);proofs.append(item)
    for item in qda['figures']:
        path=ROOT/item['path'];assert sha(path)==item['sha256'];images['qda_'+path.stem]=embedded(path,item['caption']);proofs.append(item)
    for item in dimension['figures']:
        path=ROOT/item['path'];assert sha(path)==item['sha256'];images['dim_'+path.stem]=embedded(path,item['caption']);proofs.append(item)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    def save(fig,name,caption):
        fig.tight_layout();path=figs/(name+'.png');fig.savefig(path,dpi=150,bbox_inches='tight');fig.savefig(path.with_suffix('.svg'),bbox_inches='tight');plt.close(fig)
        images[name]=embedded(path,caption);proofs.append(dict(path=str(path.relative_to(ROOT)),sha256=sha(path),caption=caption))
    rows=[];ledger=[];policies=[];supported=[];role_records=[]
    for study in stats['studies']:
        semantic=study['study']=='semantic_correction';lock=read(SEM/'repair/TEST_LOCK.json' if semantic else VOUT/'final/TEST_LOCK.json');roles=lock.get('roles',lock.get('primary_roles',{}));mapping={}
        selection=read(SEM/'repair/FINAL_LOCK.json' if semantic else VOUT/'global_funnel/FINAL_CANDIDATE_LOCK.json')
        for role,ident in roles.items():
            label=role+('（诊断：未满足验证安全约束）' if role=='safety_priority' and not selection['safety_eligible'] else '')
            mapping.setdefault(ident,[]).append(label)
        for role,ident in lock.get('component_diagnostics',{}).items():mapping.setdefault(ident,[]).append(role+' component diagnostic')
        contrast={c['positive'][0]:c for c in study['contrasts'] if c['family'] in ['primary','component_diagnostic']}
        for method in study['methods']:
            arm=method['arm'];ident=arm['id']
            if ident not in mapping:continue
            d=method['actual'];c=contrast[ident];label=('补正语义池' if semantic else '上游主实验')+' / '+', '.join(mapping[ident]);policies.append((label,method,c));role_records.append(dict(label=label,method=method,contrast=c))
            location=' + '.join(p['block']+'/'+p['group'] for p in arm['parts']) if arm['method']=='combination' else arm['block']+'/'+arm['group']
            rows.append([esc(label),esc(location)+'<br>'+esc(arm['method'])+f'<br>alpha={arm.get("alpha","按组件")} / cap={arm["cap"]}',num(c['delta_pdms'])+'<br>'+esc([round(v,4) for v in c['ci95']])+f'<br>Holm p={c["p_holm"]:.4g}',f'{d["repaired_above90"]} / {d["high_to_failure"]}',f'{d["collision_net"]:+d} / {d["offroad_net"]:+d} / {d["delta_zero_count"]:+d} / {d["ttc_net"]:+d}',f'{100*method["policy_change_rate"]:.2f}% / {100*method["failure_precision_of_policy_change"]:.2f}%'])
            ledger.append([esc(label),str(d['stable_fail_cases']),f'{d["stable_fail_repaired90_any"]} / {d["stable_fail_repaired90_all"]}',str(d['stable_high_damage_any']),num(method['oracle_failure_only']['delta_pdms']),num(method['oracle_failure_and_benefit']['delta_pdms'])])
            if c['family']=='primary' and c['ci95'][0]>0 and c['p_holm']<.05:supported.append(ident)
    labels=[p[0].replace(' component diagnostic','') for p in policies];fig,ax=plt.subplots(figsize=(10,max(3.5,len(policies)*.55+1)))
    for i,(_,method,c) in enumerate(policies):ax.hlines(i,*c['ci95'],color='#177b8b');ax.plot(c['delta_pdms'],i,'o',c='#177b8b')
    ax.axvline(0,color='#777777',lw=.7);ax.set(yticks=range(len(labels)),yticklabels=[('Semantic' if '补正' in x else 'Primary')+' / '+x.split(' / ',1)[1] for x in labels],xlabel='Locked test PDMS change (points), session bootstrap 95% CI');ax.invert_yaxis()
    save(fig,'upstream_test','锁定后测试复评的均分变化及会话95%区间；五次采样先在病例内平均，主角色及组件诊断分别按预设家族校正，不能把重复噪声当独立训练。')
    group_names={'action_head_representation':'动作头表征','upstream_representation':'VLM / 接口表征','trajectory_scaling':'简单轨迹缩放','all_representation':'全部表征','all_genuine':'全部实算方法'};bounds=[]
    for name,g in pool['groups'].items():
        failure=g['failure_only'];bounds.append([group_names[name],num(g['all_case']['delta_pdms']),num(failure['delta_pdms']),num(g['case_fixed_method_failure_only']['delta_pdms']),str(failure['repaired_above90']),str(g['stable_failure_cases_with_at_least_one_single_method_above90_all_seeds'])])
    names=[n for n in group_names if n in pool['groups']];fig,ax=plt.subplots(figsize=(8,4));ys=np.arange(len(names));ax.barh(ys-.13,[pool['groups'][n]['all_case']['delta_pdms'] for n in names],height=.24,label='All-case beneficial oracle',color='#ce7638');ax.barh(ys+.13,[pool['groups'][n]['failure_only']['delta_pdms'] for n in names],height=.24,label='Failure-only oracle',color='#177b8b');ax.set(yticks=ys,yticklabels=names,xlabel='Diagnostic PDMS upper bound (points)');ax.invert_yaxis();ax.legend(fontsize=8)
    save(fig,'oracle_bounds','Oracle按完全相同的场景、真实seed和七项Base合并，包含Base，随机/反向/GT补丁不进入主池。只替换失败输出与原成功样本的微小增分分开；逐draw上限可在噪声间换方法，固定病例方法的更严格口径另表列。')
    statement='至少一个预先锁定的上游主角色获得经校正支持的测试均分收益。' if supported else '上游修复本轮尚未在锁定测试中获得经主家族校正支持的均分净收益。'
    section='<section id="upstream-representation-repair"><h2>VLM与接口中的质量结构能否用于修复</h2><p>'+statement+'分类读出、实际失败修复与总体能力提升分别判断；离线PDM评分不等同真实交互闭环。</p>'
    section+='<p>全量103288训练场景覆盖视觉编码器24层及输入、视觉→语言投影输入和4个模块、语言28层及融合输入/末端归一化、VLM→动作头接口两端，共62位置、2272逻辑池化区域。上游由观测决定，同场景换动作轨迹或扩散噪声时表征相同，因此采用跨场景路线一；会话划分和跨噪声检查限制场景混杂，最终仍须靠实际干预验证。上游跨S1/S2检验的是冻结读出与重新采样行为质量的关系能否复现，而非把表征本身不变当作稳定性证据；其指标限定于原S0极端质量队列中S1/S2也为极端者，不冒称全S1/S2自然总体。</p>'
    section+=images['layer_readouts']+images['session_stability']+'<details><summary>留出分布、稳定性与低维空间的解释范围</summary>'+images['heldout_distributions']+'<p>均值差方向的总体AUROC较高，仍可能来自会话之间的难度差异；优先同时查看会话内方向、标准化效应、AP、S1/S2与校正结果。会话留出用于本轮新拟合读出/干预的确认，Base此前已在原训练数据上训练；最终泛化由锁定测试评估。非可解释的结构仍可进入干预，不能将分类可分直接视为失败原因。</p></details>'
    qda_rows=[]
    for r in qda['all_controls']:
        cfg=r['config'];m=r['heldout'];qda_rows.append([esc(r['component']),esc(cfg['kind'])+(' / '+str(cfg['replicate']) if cfg['replicate'] is not None else ''),str(cfg['r'] or 'full'),f'{r["cv"]["auc"]:.4f}',f'{m["auc"]:.4f}',f'{m["weighted_ap"]:.4f}',f'{m["standardized_gap"]:.3f}',f'{m["session_positive_fraction"]:.3f}',f'{r["p_holm_planned1000"]:.4g}'])
    section+='<details><summary>相同QDA读出下的维数邻域、随机空间和全维对照</summary><p>视觉、视觉→语言投影、语言和接口各固定一个原探索CV选出的强QDA地点，比较r=64/96/128/192/256、3个同r随机空间及全维，共84组。各空间均使用相同5%收缩QDA，全体结果公开；这些控制不改变原修复选择。邻近维数下的质量差异并非孤立点，随机同维空间也能接近成功PCA；说明质量信息可由多种投影读出，尚不能确认该PCA基的特异性或真实内在维数，也不证明已定位故障机制。</p>'+images['qda_cv']+images['qda_heldout']+table(['组件','空间','r','CV AUC','留出AUC','留出AP','标准化差异','会话正向比例','Holm p'],qda_rows,left=(0,1))+'</details>'
    dimension_rows=[];confirmed={r['id']:r for r in multiplicity['heldout_confirmation']}
    for r in sorted(dimension['all_frozen_residual_records'],key=lambda r:(r['component'],r['semantic'],r['spec']['cell'],r['fit_id'])):
        s=r['spec'];c=s['config'];m=r['confirmation']['metrics'];check=confirmed[r['fit_id']]
        dimension_rows.append([esc(r['component'])+(' / 补正语义池' if r['semantic'] else ''),esc(s['cell']),esc(c['kind'])+' / '+('等维' if c['equal'] else '非等维'),f'{c["ks"]}/{c["kf"]}/{c["r"]}',esc(s['centering']),f'{s["metrics"]["auc"]:.4f} / {s["auc_fold_min"]:.4f}',f'{m["auc"]:.4f} / {m["weighted_ap"]:.4f}',f'{m["standardized_gap"]:.3f} / {m["session_positive_fraction"]:.3f}',f'{check["p_holm_planned1000"]:.4g}',str(s['neighbor_supported'])+' / '+str(s['neighbor_tested']),('CV稳定区域' if s['stable_cv_region'] else '诊断代表；未满足全部稳定条件')])
    section+='<details><summary>主空间与最终残差维数：固定变量切片、同r比较及全部冻结残差候选</summary><p>以下只读取已完成网格和既有冻结修复候选，不新增模型采集、拟合或修复选择。固定kf/r改变ks，固定ks/r改变kf，以及固定两主空间改变r分别展示；同一热图的最终r固定，白线为等维主空间。相同r的探索包络另加入PCA、三随机及全维对照。非等维组合的搜索机会更多，包络高低不能直接解释为公平预算下的优越性；各自独立确认只使用表中原已冻结候选的留出结果。CV稳定资格不代表已通过留出分布标准或全家族Holm，后两项须结合表中效果、会话方向及校正p分别判断。</p>'+images['dim_dimension_slices']+images['dim_main_space_grids']+images['dim_matched_final_rank']+table(['通道','位置/区域','构造','ks/kf/r','中心化','CV AUC / 最小折','留出AUC / AP','留出标准化差异 / 会话正向比例','留出Holm p','邻域支持 / 可评估','原探索资格'],dimension_rows,left=(0,1,2,10))+'</details>'
    section+='<h3>锁定策略的实际表现</h3>'+table(['角色','位置、算子与力度','测试ΔPDMS / CI / p','失败→>90 / 原高质量→失败','净碰撞 / 出界 / 零分 / TTC','位置变化率 / 原失败比例'],rows,left=(0,1))+images['upstream_test']
    section+='<p>位置变化以最大平移差&gt;10⁻⁸米计，原失败比例指这些输出中Base原本&lt;70的比例；这不是包含纯航向变化的完整行为分类，也和潜变量激活率区分。所有PDMS修复/损伤统计仍使用完整轨迹重新评分。安全优先仅按验证阶段净碰撞、出界、数值零分不增加且均分不降选择；TTC与总失败数单列，不能称为全部安全指标保证。若无合格候选，最保守者仅作诊断，资格见冻结选择记录。</p>'
    reference_rows=[]
    for r in prior['records']:
        e=r['net_events_vs_reference'];reference_rows.append([esc(r['study']),esc(r['parent']),esc(r['reference']),num(r['delta_pdms']),esc([round(v,4) for v in r['ci95']]),f'{r["p_holm"]:.4g}',f'{e["collision"]:+d} / {e["offroad"]:+d} / {e["zero"]:+d} / {e["ttc"]:+d}'])
    section+='<details><summary>与已有修复和简单轨迹缩放的配对比较</summary><p>全部新全局角色与先前固定的安全/PDMS两方法、1.005/1.02两种缩放逐一比较；参考名单在上游测试前冻结，未按测试重选最优参照。差值为新方法减参照，五噪声在病例内平均，全部参照比较联合Holm。这里保留完整比较，即使相对Base的均分有提升。</p>'+table(['研究','新角色ID','固定参照','ΔPDMS','95%CI','Holm p','净碰撞 / 出界 / 零分 / TTC'],reference_rows,left=(0,1,2))+'</details>'
    section+='<details><summary>稳定失败、原高质量损伤及每个方法的上限</summary>'+table(['策略','五次持续失败病例','至少一次 / 全五次>90','持续高质量受损病例','完美失败门控Δ','失败且有益Δ'],ledger,left=(0,))+'<p>表中实际策略保留原内部门控。另对全部带门控最终父项（含组件诊断）补算去门控版本的五种子Base失败输出；非失败按定义保持Base，这不是无条件去门控测试。对应账本见final/ungated与semantic/repair/ungated；不能把原门控漏激活误作算子无效。</p></details>'
    scanrows=[]
    for g in multiplicity['searches']:scanrows.append([esc(g['root']),str(g['completed_cells'])+' / '+str(g['planned_cells']),str(g['configs_per_center']),str(g['finite_hypotheses'])])
    section+='<details><summary>实际搜索覆盖、干预方法和工程复核</summary>'+table(['通道','已完成 / 计划区域','每中心化请求配置','有限统计比较'],scanrows,left=(0,))+'<p>完整残差网格每区域11633请求配置，主空间ks/kf最高4096、最终r最高1024，按维度和每折有效rank排除；未中心化和共同中心化分别保存。全部token快速通道为81配置，包含各r的成功/失败PCA、3个同r高斯空间和全维，另含能量/QDA。快速通道不能代替全部残差Cartesian搜索。62层级代表完整网格与纠正64语义池均须完成；其余token残差网格按上表如实记录，未完成不算覆盖。原64个文本池BPE锚点错误的空结果被排除并独立补正，逻辑区域数不因此增加。</p><p>修复比较均值、收缩、失败方向移除、OT、连续质量梯度、局部成功原型、投影、软截断、成功支撑投影、QDA梯度；高于1024维的全维诊断省去稠密OT等高成本算子。广筛各比较alpha .1/.25/.5/1与cap .005/.01/.025/.05/.1，再用新探索面板精调力度、硬/软风险及收益门控、组件组合、3650场景复放，完整17475会话留出三噪声验证后锁定。BF16以实际选中token组Frobenius相对编辑限幅，缩小后仍超限则保持原值。</p><p>正式测试12146场景×五噪声，锁定全训练覆盖103288×三噪声。每卡真实模型与零干预/缓存复现；每任务断言固定种子Base与既有输出一致；32rank阶段核查；每个最终阶段600条保存轨迹经原只读评分入口重算，所有分项必须精确一致。Base权重冻结，测试无GT或PDMS输入。随机对照含独立反向与3个Haar方向；组件诊断缺少自身随机对照时不能单独证明方向特异因果。</p></details></section>'
    oracle_section='<section id="repair-oracle-bounds"><h2>精准识别后，现有算子能修复多少</h2><p>上帝视角是诊断上限，不能作为可部署分数。按已实际计算的算子库比较：只对Base失败执行、进一步只保留有益替换，以及Base与全部真实方法逐例选优；原成功增分和失败修复分开。</p>'+table(['算子库','全样本有益上限Δ','失败专属上限Δ','病例固定方法+失败识别Δ','失败输出达到>90','单方法全五次修复病例'],bounds,left=(0,))+images['oracle_bounds']+'<p>算子库和搜索规模都会影响Oracle；这些值不是所有可能修复方法的理论极限。去门控诊断只在实际失败输出上推理，禁止臆造其原成功输出。不同面板不混用；富集广筛的原始均值不当作总体PDMS。所有实际已评分面板和逐方法安全账本保存在oracle_all及oracle_policy_groups，具体源sha随快照保留。</p></section>'
    lead='<div class="lead"><p>'+statement+'动作头扩展主候选仍未确认全局净收益；上游QDA质量读出与均值差分开看，是否可修复由实际干预结果判断。</p><p>训练集拟合与探索按采集会话交叉验证，冻结后会话留出确认；各轮测试为预先锁定的复评，不据测试重选参数。同一策略的多次噪声采样在病例内汇总，不算独立训练。</p><p><a href="#upstream-representation-repair">VLM与接口</a> · <a href="#expanded-candidate-repair">动作头候选</a> · <a href="#repair-oracle-bounds">精准修复上限</a></p></div>'
    old=source.read_text();body,n=re.subn(r'<div class="lead">.*?</div>',lambda m:lead+section+oracle_section,old,count=1,flags=re.S);assert n==1
    path=dest/'report.html';path.write_text(body);canonical_path=ROOT.parent/'doc/work-output/1016-rl_representation_analysis/representation_observation.html';canonical_path.write_text(body)
    snapshot_paths=[stats_path,oracle_path,readout_path,multipath,qda_path,prior_path,dimension_path,full_accept_path]
    snapshot_paths += [VOUT/'final/SCIENTIFIC_ACCEPTANCE.json',VOUT/'final/BASE_TRAJECTORY_ACCEPTANCE.json',
        VOUT/'UNGATED_TEST_DIAGNOSTICS_COMPLETE.json',SEM/'CACHE_COMPLETE.json',SEM/'CACHE_ACCEPTANCE.json']
    snapshot_paths += [SEM/'repair/SCIENTIFIC_ACCEPTANCE.json',SEM/'repair/BASE_TRAJECTORY_ACCEPTANCE.json'] if sem_done else [SEM/'repair/NO_COMPETITIVE_CANDIDATES.json']
    atomic(dest/'BUILD.json',dict(status='BUILT_NOT_ACCEPTED',time=stamp(),report_sha256=sha(path),source_report_sha256=sha(source),source_report=str(source.relative_to(ROOT)),figures=proofs,
        snapshot_sha256={str(p.relative_to(ROOT)):sha(p) for p in snapshot_paths},generator_sha256=sha(Path(__file__)),
        statistics_path=str(stats_path.relative_to(ROOT)),statistics_sha256=sha(stats_path),oracle_path=str(oracle_path.relative_to(ROOT)),oracle_sha256=sha(oracle_path),readout_path=str(readout_path.relative_to(ROOT)),multiplicity_path=str(multipath.relative_to(ROOT)),
        qda_report_path=str(qda_path.relative_to(ROOT)),prior_reference_path=str(prior_path.relative_to(ROOT)),dimension_report_path=str(dimension_path.relative_to(ROOT)),role_records=role_records,supported_primary_ids=supported,semantic_complete=sem_done,semantic_no_competitive=no_sem,all_requested_full_grid_complete=all(g['completed_cells']==g['planned_cells'] for g in multiplicity['searches']),browser_render_verified=False))
    atomic(VOUT/'REPORT_LATEST.json',dict(path=str(dest.relative_to(ROOT)),report_sha256=sha(path),status='BUILT_NOT_ACCEPTED'));print('INTEGRATED_REPORT_BUILT_NOT_ACCEPTED',str(dest.relative_to(ROOT)),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--version',required=True);main(p.parse_args())
