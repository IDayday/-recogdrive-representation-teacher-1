"""Integrate expanded-candidate repair evidence into the existing standalone scientific report."""
from common import *
import argparse
import base64
import html
import re
import numpy as np
from candidate_repair_fit import OUT

def esc(x):return html.escape(str(x))
def number(x,d=3):return f'{x:+.{d}f}'
def table(headers,rows,left=()):
    def cell(tag,value,i):return '<'+tag+(' class="long"' if i in left else '')+'>'+str(value)+'</'+tag+'>'
    return '<div class="scroll"><table><thead><tr>'+''.join(cell('th',esc(v),i) for i,v in enumerate(headers))+'</tr></thead><tbody>'+''.join('<tr>'+''.join(cell('td',v,i) for i,v in enumerate(row))+'</tr>' for row in rows)+'</tbody></table></div>'
def short(candidate):
    if candidate=='combination':return 'Combination'
    if candidate.startswith(('r1_','r2_')):return candidate[:2].upper()+'-'+candidate.rsplit('region',1)[-1]
    return candidate
def method(a):
    if a['method']=='combination':return ' + '.join(method(c) for c in a['components'])
    return a.get('mechanism',a['method'])+' / '+a.get('calibration','')+' / '+a.get('gate','')
def control_label(a):
    kind=a.get('control_kind','structured');basis=a.get('alternative_basis','')
    return kind+' / seed'+basis.rsplit('__haar',1)[1] if '__haar' in basis else kind
def layer(i):return 'final512' if i==18 else ('DiT'+str(i-2) if i>=2 else ['action','fusion'][i])
def location(a):
    if a['method']=='combination':return ' + '.join(location(c) for c in a['components'])
    return f'{short(a.get("candidate",""))}, t={[80,60,40,20,0][a["step"]]}, {layer(a["layer"])}, token{a["token"]}' if 'step' in a else a['method']

def main(args):
    setup('candidate_repair/report')
    assert read(OUT/'FINAL_ACCEPTANCE.json')['status']=='PASS'
    lock=read(OUT/'FINAL_TEST_LOCK.json');selection=read(OUT/'BEHAVIOR_SELECTION_LOCK.json');stats=read(OUT/'analysis/final_test/FINAL_STATISTICS.json')
    acceptance=read(OUT/'FINAL_ACCEPTANCE.json');test=read(OUT/'analysis/final_test/SUMMARY.json');train=read(OUT/'analysis/navtrain_full_locked/SUMMARY.json')
    from candidate_repair_case_stability import analyze as case_stability
    stability={r['arm']:r for r in case_stability()['records']}
    final={r['arm']['id']:r for r in test['summaries']};full={r['arm']['id']:r for r in train['summaries']};details={r['arm']:r for r in stats['details']}
    primary={r['positive'][0]:r for r in stats['records'] if r['family']=='primary_base'}
    candidates=read(OUT/'CANDIDATES.json')['candidates'];validation=read(OUT/'analysis/validation/SUMMARY.json')['summaries']+read(OUT/'analysis/validation_temporal/SUMMARY.json')['summaries']
    combinations=read(OUT/'analysis/validation_combinations/SUMMARY.json')['summaries']
    val={r['arm']['id']:r for r in validation+combinations}
    archive=OUT/'report_versions'/args.version;archive.mkdir(parents=True,exist_ok=False);figures=OUT/'figures'/args.version;figures.mkdir(parents=True,exist_ok=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    images={};proofs=[]
    def save(fig,key,caption):
        if not fig.get_constrained_layout():fig.tight_layout()
        p=figures/(key+'.png');fig.savefig(p,dpi=150,bbox_inches='tight');fig.savefig(p.with_suffix('.svg'),bbox_inches='tight');plt.close(fig)
        images[key]=f'<figure><img src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}" alt="{esc(caption)}"><figcaption>{esc(caption)}</figcaption></figure>'
        proofs.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p),caption=caption))
    # All new full-validation arms, not only the eventual finalists.
    fig,ax=plt.subplots(figsize=(8.8,4.8))
    for r in validation+combinations:
        a=r['arm']
        if a.get('control'):continue
        ax.scatter(r['high_damage_to_failure_rate']*100,r['mean_delta_pdms'],s=30,
            c={'r1':'#167d8d','r2':'#d17a36','mixed':'#7756a2'}.get(a.get('route'),'#999999'),
            marker='^' if a['method']=='combination' else ('s' if a.get('gate')=='benefit' else 'o'),alpha=.65)
    annotations={}
    for role in ['global_safety','global_pdms']:
        row=selection['choices'][role]['summary'];key=(row['high_damage_to_failure_rate']*100,row['mean_delta_pdms'])
        annotations.setdefault(key,[]).append(role.replace('global_',''))
    for position,roles in annotations.items():
        ax.annotate('Global '+ ' / '.join(roles),position,xytext=(4,6),textcoords='offset points',fontsize=8)
    ax.axhline(0,color='gray',lw=.7);ax.set(xlabel='Original high-quality outputs becoming failures (%)',ylabel='Full validation PDMS change (points)')
    save(fig,'validation_frontier','完整会话留出验证的均分—损伤权衡。蓝色为路线一、橙色为路线二、紫色为跨路线组合；方形为收益门控，三角为组合。所有已验证新方法都显示，不只展示优胜者。')
    selected=selection['arms'];ids=[a['id'] for a in selected];labels=[short(a.get('candidate','combination'))+' / '+a.get('mechanism',a['method']) for a in selected]
    fig,axes=plt.subplots(1,2,figsize=(12,max(3.8,.55*len(ids)+1.2)),constrained_layout=True)
    for j,i in enumerate(ids):
        c=primary[i];lo,hi=c['ci95'];axes[0].hlines(j,lo,hi,color='#167d8d');axes[0].plot(c['delta_pdms'],j,'o',c='#167d8d')
        axes[1].scatter(val[i]['mean_delta_pdms'],j,c='#d17a36',marker='s',label='Validation' if j==0 else None)
        axes[1].scatter(full[i]['mean_delta_pdms'],j,c='#7756a2',marker='^',label='Full navtrain (descriptive)' if j==0 else None)
        axes[1].scatter(c['delta_pdms'],j,c='#167d8d',marker='o',label='Locked test re-evaluation' if j==0 else None)
    for ax in axes:ax.axvline(0,color='gray',lw=.7);ax.set(yticks=range(len(ids)),yticklabels=labels,xlabel='PDMS change (points)');ax.invert_yaxis()
    axes[0].set_title('Locked test: session bootstrap 95% CI');axes[1].set_title('Same frozen candidates across evaluation pools');axes[1].legend(fontsize=7,loc='best')
    save(fig,'locked_results','相同锁定候选的行为结果。左侧为第二轮测试复评及会话95%区间，主检验另经Holm校正；右侧完整训练总体属于拟合/开发数据上的描述性覆盖，不作为独立泛化证据。')
    fig,axes=plt.subplots(1,4,figsize=(13,max(3.7,.48*len(ids)+1.4)),constrained_layout=True)
    for ax,event in zip(axes,['collision','offroad','zero','ttc']):
        for j,i in enumerate(ids):
            e=details[i]['events'][event];ax.barh(j,e['new'],color='#c34d56');ax.barh(j,-e['removed'],color='#167d8d')
        ax.axvline(0,color='gray',lw=.7);ax.set(yticks=range(len(ids)),yticklabels=labels if event=='collision' else [],title=event,xlabel='Added (+) / removed (-) outputs');ax.invert_yaxis()
    save(fig,'safety_events','五种子测试复评的安全事件账本：红色为新增，绿色为消除。单位为配对输出事件；同一病例的五次采样不能当成五个独立病例。TTC与总失败数只报告，不额外加入安全优先筛选约束。')
    coarse=read(OUT/'analysis/coarse/SUMMARY.json')['summaries'];fig,axes=plt.subplots(2,5,figsize=(15,6.1),constrained_layout=True)
    for ax,candidate in zip(axes.ravel(),candidates):
        for m,color in [('mean','#167d8d'),('boundary','#7756a2'),('ot','#d17a36')]:
            values=[]
            for alpha in [.1,.5,1.]:
                found=[r for r in coarse if r['arm']['candidate']==candidate['id'] and r['arm']['space']=='candidate' and r['arm']['method']==m and r['arm']['gate']=='none' and r['arm']['cap']==.05 and r['arm']['alpha']==alpha and r['arm']['calibration']==('n' if candidate['route']=='r1' else 'p')]
                assert len(found)==1;values.append(found[0]['population_weighted_screen_delta'])
            ax.plot([.1,.5,1.],values,'-o',ms=3,c=color,label=m)
        ax.axhline(0,color='gray',lw=.6);ax.set(title=short(candidate['id']),xlabel='alpha',ylabel='Weighted screen PDMS delta')
    axes[0,0].legend(fontsize=7)
    save(fig,'strength_curves','固定候选空间、无门控、cap=.05时的强度响应。路线一采用自然统计、路线二采用配对统计；纵轴按真实自然质量分布对广筛样本重加权，属于探索诊断。')
    role_labels={'route1_safety':'路线一·安全','route1_pdms':'路线一·PDMS','route2_safety':'路线二·安全','route2_pdms':'路线二·PDMS','global_safety':'全局·安全','global_pdms':'全局·PDMS'}
    for role,entry in selection['choices'].items():
        if role.endswith('_safety') and not entry.get('safety_eligible',False):role_labels[role]+='（诊断）'
    role_by={}
    for role,i in lock['roles'].items():role_by.setdefault(i,[]).append(role_labels[role])
    rows=[]
    for a in selected:
        i=a['id'];r=final[i];d=details[i];c=primary[i];e=d['events']
        rows.append(['<br>'.join(role_by[i]),esc(location(a))+'<br>'+esc(method(a))+f'<br>alpha={a["alpha"]:g}, cap={a["cap"]:g}',f'{number(c["delta_pdms"],4)}<br>[{number(c["ci95"][0],4)}, {number(c["ci95"][1],4)}]<br>Holm p={c["p_holm"]:.4g}',
            f'{d["repaired_gt90"]} / {d["high_to_failure"]}',f'{e["collision"]["net"]:+d} / {e["offroad"]["net"]:+d} / {e["zero"]["net"]:+d} / {e["ttc"]["net"]:+d}',
            f'{100*r["activation_rate"]:.2f}% / {100*r["failure_precision_of_activation"]:.2f}%'])
    main_table=table(['锁定角色','空间、位置与干预','测试ΔPDMS / 95%CI','失败→>90 / 原高质量→失败','净NC / DAC / 零分 / TTC','激活率 / 激活失败精度'],rows,left=(1,))
    reference_rows=[]
    reference_labels={'legacy_safety_priority':'前轮安全优先','legacy_pdms_priority':'前轮PDMS优先','scale_1.005':'轨迹缩放1.005','scale_1.02':'轨迹缩放1.02'}
    for arm_id,label in reference_labels.items():
        d=details[arm_id];events=d['events']
        reference_rows.append([label,number(d['delta_pdms'],4),f'{d["repaired_gt90"]} / {d["high_to_failure"]}',f'{events["collision"]["net"]:+d} / {events["offroad"]["net"]:+d} / {events["zero"]["net"]:+d} / {events["ttc"]["net"]:+d}'])
    reference_table=table(['预先登记的参照','测试ΔPDMS','失败→>90 / 原高质量→失败','净NC / DAC / 零分 / TTC'],reference_rows)
    region_rows=[]
    for c in candidates:
        group=[r for r in validation if r['arm'].get('candidate')==c['id'] and not r['arm'].get('control')];best=max(group,key=lambda r:r['mean_delta_pdms']);a=best['arm'];cfg=c['config']
        region_rows.append([short(c['id']),f'{cfg["ks"]}/{cfg["kf"]}/{cfg["r"]}',esc(c['centering']),esc(location(a)),esc(method(a)),number(best['mean_delta_pdms'],4),f'{100*best["complete_repair_rate"]:.2f}%',f'{100*best["high_damage_to_failure_rate"]:.3f}%'])
    region_table=table(['候选','ks/kf/r','中心化','干预位置','该区域最佳验证方法','验证ΔPDMS','失败完整修复率','原高质量→失败'],region_rows,left=(2,3,4))
    primary_success=[r for r in stats['records'] if r['family']=='primary_base' and r['p_holm']<.05 and r['ci95'][0]>0]
    global_safety=lock['roles']['global_safety'];global_pdms=lock['roles']['global_pdms'];s=details[global_safety];p=details[global_pdms]
    statement=('至少一个预先锁定的新候选在本次复评中取得经主检验校正支持的PDMS净收益。' if primary_success else '扩展空间后的修复仍未在本次锁定复评中取得经主检验校正支持的PDMS净收益。')
    conclusion=statement+'表征质量关联、局部失败修复与总体能力修复分开判断；PDM为离线候选仿真评分，真实交互闭环尚未验证。'
    lead='<div class="lead"><p>'+esc(conclusion)+'</p><p>'+f'全局安全优先ΔPDMS {number(s["delta_pdms"],4)}，全局PDMS优先 {number(p["delta_pdms"],4)}。本轮覆盖10个确认区域、580个初始配置，完整训练总体与会话留出分开报告，最终在12,146个场景×五次自然采样上按事先锁定方案复评。'+ '</p><p>测试集已用于前一轮方法评价，本轮如实标记为第二轮锁定复评；选择与拟合均在训练探索/会话验证阶段完成，不据本轮测试结果改参数。</p></div>'
    stage_rows=[[esc(r['stage']),str(r['scenes']),str(r['arms']),esc(r['seeds']),str(r['tasks']),str(r['outputs'])] for r in acceptance['stages']]
    contrast_rows=[[esc(r['name']),esc(r['family']),number(r['delta_pdms'],4),esc([round(v,4) for v in r['ci95']]),f'{r["p_holm"]:.5g}'] for r in stats['records']]
    full_rows=[]
    for a in selected:
        r=full[a['id']];full_rows.append([esc(location(a)),number(r['mean_delta_pdms'],4),str(sum(s['repaired_gt90'] for s in r['by_seed'])),str(sum(s['high_to_failure'] for s in r['by_seed'])),f'{100*r["activation_rate"]:.2f}%'])
    section='<section id="expanded-candidate-repair"><h2>扩展候选的干预能否修复行为</h2><p>路线一4个、路线二6个确认区域全部进入修复筛查。每个区域保留验证代表，并比较配对/自然统计、分布运输、条件映射、自然成功identity replay、连续PDMS梯度、风险与收益门控。初始580配置另加80个连续质量梯度配置；探索中对传播衰减另冻结144个时间对照，全部使用同一批场景和自然噪声。两个主候选的原始位置保留同r等维/全维与真实高斯随机对照；时间变体另作传播实验，不将其解释为纯维数比较。不继续扩大整个维数搜索网格。</p>'+main_table+'<h3>与已有方法和简单几何改动比较</h3><p>以下参照与新候选使用相同场景和五组采样，不参与本轮测试后重选。相对于前轮两方法的预先登记统计比较完整列于附录；不能只因新方法相对Base略有提升，就认为它优于已有修复。</p>'+reference_table+images['locked_results']+images['safety_events']
    section+='<h3>修复与原有能力保留</h3><p>'+f'本轮五种子Base PDMS {stats["baseline"]["mean_pdms"]:.4f}，逐种子和全部分项与前轮同配置Base精确一致。原失败输出{stats["baseline"]["failure_outputs"]}次、原高质量输出{stats["baseline"]["high_outputs"]}次；表中修复与损伤为配对输出计数，原高质量定义为PDMS&gt;90，失败为&lt;70。完整修复须&gt;90，跨过70单独保留。'+ '</p>'+images['validation_frontier']
    section+='<p>安全优先是验证阶段的选择准则，不是安全保证；若无方法同时满足净碰撞/出界/零分不增加且均分不降，按预先规则保留最保守者并在角色名标注“诊断”，不记作满足安全约束。</p>'
    stable_rows=[];mode_rows=[]
    for a in selected:
        d=details[a['id']]
        case=stability[a['id']]
        stable_rows.append([esc(location(a)),str(d['stable_fail_cases']),f'{case["stable_failure_any_gt90"]} / {case["stable_failure_all_gt90"]}',str(d['stable_high_cases']),f'{case["stable_high_any_failure"]} / {case["stable_high_failure_outputs"]}'])
        for name,m in d['failure_modes'].items():mode_rows.append([short(a.get('candidate','combination')),esc(name),str(m['outputs']),str(m['repaired_ge70']),str(m['repaired_gt90']),number(m['mean_delta_pdms'],3) if m['mean_delta_pdms'] is not None else '—'])
    section+='<details><summary>稳定失败／稳定成功与不同原始失败类型</summary><p>稳定组按Base五次采样全部&lt;70或全部&gt;90定义。修复同时报告“至少一次”和“全部五次”达到&gt;90的病例数，区别偶发改善与跨采样保持；持续高质量损伤同时列受影响病例数与五次采样中的事件数。失败类型按碰撞→出界→TTC→进度/其他顺序划分原始失败输出，属于评分项分组，不是根因归因。</p>'+table(['候选','持续失败病例','修复>90病例：至少一次 / 全五次','持续高质量病例','受损病例 / 损伤输出次数'],stable_rows,left=(0,))+table(['候选','原失败类型','输出数','达到≥70','达到>90','该组ΔPDMS'],mode_rows,left=(1,))+'</details>'
    section+='<details><summary>全部10区域的完整会话验证结果</summary><p>每行展示该区域已完成验证配置中最高PDMS者，用于解释筛查范围；跨区域的最终安全/PDMS角色由统一预设规则锁定。单行最高点不替代全部方法的权衡。</p>'+region_table+'</details>'
    sensitivity=read(OUT/'SENSITIVITY.json');sensitivity_rows=[]
    for row in sensitivity['summaries']:
        a=row['arm'];sensitivity_rows.append([short(a['candidate']),esc(control_label(a)),f'{100*row["relative_edit_median"]:.2f}%',
            f'{row["steps"][0]["mean_l2"][1]:.3g}',f'{row["steps"][-1]["mean_l2"][1]:.3g}',f'{1000*row["displacement_median_m"]:.3f}'])
    time_rows=[]
    for row in read(OUT/'analysis/validation_temporal/SUMMARY.json')['summaries']:
        a=row['arm'];time_rows.append([short(a['candidate']),esc(a['timing_type']),esc(location(a)),esc(method(a)),number(row['mean_delta_pdms'],4),f'{100*row["high_damage_to_failure_rate"]:.3f}%'])
    section+='<details><summary>干预信号的传播与路线一时间对照</summary><p>t表示原生DDIM去噪时间[80,60,40,20,0]；token为0起始的动作索引，对应未来0.5–4秒。时间对照移动的是去噪位置，动作token保持不变。</p><p>128个固定探索样本（64失败、48高质量、16中间）上，固定自然均值方向alpha1/cap.05，逐步记录输入、解码和更新均值。原配置的最终轨迹与已保存广筛结果精确一致。下表为样本中位数；第一步/最终步更新差为归一化latent的L2差，位移为轨迹最大平移差，不能把两者的单位混用。这是传播诊断，不用来报告独立总体修复率。</p>'+table(['候选','方向','实际相对编辑','第一步更新差','最终步更新差','最终位移(mm)'],sensitivity_rows,left=(1,))
    section+='<p>时间对照保留原候选投影B：在原步与最终步比较固定源方向及目标步自然统计重新校准；持续干预覆盖原步到最终步，按同token跨位置L2分配总预算。固定范数方向用大alpha=10⁶使限幅生效，实际强度仍仅为cap=.01/.05，绝不是对隐藏状态施加百万倍改动。风险门控在各目标步的自然成功分布标定；无门控固定方向对照用于区分时间变化。新时间变体不是又一次SVD空间搜索，全部只在探索结果上选出验证名单，未据测试成绩调整。</p>'+table(['源候选','时间对照','实际位置','方法/校准/门控','验证ΔPDMS','原高质量→失败'],time_rows,left=(1,2,3))+'</details>'
    control_rows=[]
    control_summary=read(OUT/'analysis/validation_controls/SUMMARY.json')['summaries']
    for r in control_summary:
        a=r['arm'];f=final.get(a['id']);control_rows.append([esc(a.get('parent','')[:15]),esc(control_label(a)),esc(method(a)),number(r['mean_delta_pdms'],4),
            esc([round(v,4) for v in r['session_bootstrap_delta_ci95']]),f'{100*r["high_damage_to_failure_rate"]:.3f}%',number(f['mean_delta_pdms'],4) if f else '父方法未入选测试'])
    for a in read(OUT/'MATCHED_CONTROL_SUPPLEMENT.json')['arms']:
        f=final[a['id']];control_rows.append([esc(a['parent'][:15]),esc(control_label(a)),esc(method(a)),'仅锁定测试','—','—',number(f['mean_delta_pdms'],4)])
    section+='<details><summary>匹配随机／反向／等维与全维方向对照</summary><p>所有父方法均在这些对照计算前锁定，对照结果不改变入选方案。全局父方法和两个原位置主候选有完整验证对照；入选的路线一末步候选另在测试计算前登记反向及3个随机方向，直接随锁定测试复评，不伪称这些补充对照也做了验证。随机种子逐个报告，不能只取最差随机结果比较。</p>'+table(['父方法ID','对照构造','原父方法与门控','验证ΔPDMS','验证95%CI','原高质量→失败','测试ΔPDMS'],control_rows,left=(0,1,2))+'</details>'
    section+='<details><summary>强度响应与全量训练覆盖</summary>'+images['strength_curves']+'<p>锁定后全量navtrain为103288场景×3采样。它覆盖已参与拟合和选模的探索数据，属于总体描述；修复计数采用每次采样下同种子的Base失败输出与干预输出逐一比较，不把后续种子中Base自行成功记作修复；三次采样不当成三倍独立病例。</p>'+table(['候选','训练总体ΔPDMS','同种子失败→>90次数','原高质量→失败次数','激活率'],full_rows,left=(0,))+'</details>'
    section+='<details><summary>冻结协议、完整统计比较和对照的适用范围</summary><p>无GT/PDMS作为推理输入；Base权重冻结，沿原生DDIM噪声完整续采后重新评分。单位置cap为编辑范数/原表征范数；组合按位置分摊，限制同action token跨位置相对范数的L2合成。多点干预可能改变后续位置输入，因此组合随机对照匹配的是同一门控规则与预算，后续实际激活不保证逐输出完全相同。</p><p>单点Haar旋转对照保持父修正的坐标、门控及预cap范数，仅替换空间朝向；3个构造种子不计为新增病例。等维/全维匹配方向对照使用对应类别均值差；连续质量梯度父方法则用替代空间的连续质量ridge梯度。它们保留父方法动态范数与门控，不是在替代空间重新训练整套OT/MLP的纯维数消融。广筛中另保留替代空间自身的均值/收缩/OT结果，全部不参与主候选选择。</p><p>校准标记：p为配对端点统计，n为自然输出统计，q为自然连续PDMS梯度，s为原位置固定源方向。benefit门控只用探索集实测干预收益拟合，推理输入仍只有原表征；none表示不加门控。会话bootstrap2000、会话符号翻转20000；五个采样先在同场景平均，主候选vsBase家族及预设旧方法/匹配随机家族分别Holm校正。下面包含全部已登记比较，不只列显著者。</p>'+table(['比较','家族','ΔPDMS','95%CI','Holm p'],contrast_rows,left=(0,1))+table(['阶段','场景','干预配置','采样索引','分块','输出'],stage_rows,left=(0,))
    section+='<p>证据入口：<code>candidate_repair_v1/PROTOCOL.json</code>、<code>BEHAVIOR_SELECTION_LOCK.json</code>、<code>FINAL_TEST_LOCK.json</code>、<code>FINAL_ACCEPTANCE.json</code>及<code>analysis/</code>；运行<code>candidate_repair_20261016_v1</code>。600条分层保存轨迹经共享只读原评分入口复算，各分项差异0。两节点各16卡实际冒烟、各rank五分钟语义检查、原始失败异常及全部未选结果均保留。</p></details></section>'
    canonical=ROOT.parent/'doc/work-output/1016-rl_representation_analysis/representation_observation.html'
    source=OUT/'report_versions/SOURCE_REPORT.html'
    if not source.exists():source.parent.mkdir(parents=True,exist_ok=True);source.write_bytes(canonical.read_bytes())
    old=source.read_text();assert '<section id="expanded-candidate-repair">' not in old
    result,n=re.subn(r'<div class="lead">.*?</div>',lambda match:lead+section,old,count=1,flags=re.S);assert n==1
    result=result.replace('训练会话开发、冻结后独立测试 · 2026-10-16T13:40:53.808940+00:00','训练会话开发、锁定后的两轮测试评价 · '+stamp())
    result=result.replace('按用户新指令，计算验收后原2×16卡保持运行与队列等待，未以退出/释放作为成功条件；12小时总运行时限继续计时，延长尚未验证。资源状态与保留验收记录独立于实验结论。',
        '原始空间实验使用的两个节点已按用户要求释放；扩展候选修复另申请2×16卡并保持至全部重计算结束。资源状态以任务STATUS与运行记录为准，资源生命周期独立于科学结论。')
    (archive/'report.html').write_text(result);canonical.write_text(result)
    narrative=dict(time=stamp(),conclusion=conclusion,primary_supported_candidates=len(primary_success),global_safety=s,global_pdms=p,
        test_reused=True,closed_loop_verified=False)
    atomic(archive/'NARRATIVE.json',narrative)
    atomic(archive/'BUILD.json',dict(status='BUILT',time=stamp(),version=args.version,report_sha256=sha(canonical),source_report_sha256=sha(source),
        figures=proofs,acceptance_sha256=sha(OUT/'FINAL_ACCEPTANCE.json'),statistics_sha256=sha(OUT/'analysis/final_test/FINAL_STATISTICS.json'),browser_render_verified=False))
    atomic(OUT/'LATEST_REPORT.json',dict(version=args.version,path=str(archive.relative_to(ROOT)),report_sha256=sha(canonical)))
    print(json.dumps(dict(status='BUILT',version=args.version,figures=len(proofs),primary_supported=len(primary_success))),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--version',required=True);main(p.parse_args())
