"""One coherent standalone report: representation evidence, causal edits, independent behavior evaluation."""
from common import *
import argparse
import base64
import html
import shutil
import numpy as np

def esc(x):return html.escape(str(x))
def num(x,d=3):return f'{x:.{d}f}'
def table(headers,rows,left=()):
    def cell(tag,x,i):return f'<{tag}'+(' class="long"' if i in left else '')+f'>{x}</{tag}>'
    return '<table><thead><tr>'+''.join(cell('th',x,i) for i,x in enumerate(headers))+'</tr></thead><tbody>'+''.join('<tr>'+''.join(cell('td',v,i) for i,v in enumerate(row))+'</tr>' for row in rows)+'</tbody></table>'

def build(args):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    root=ROOT/'repair_v1';lock=read(root/'TEST_LOCK.json');ready=read(root/'FINAL_TEST_READY.json')
    run=ROOT/'runs'/ready['run'];accepted=read(run/'FINAL_ACCEPTANCE.json');assert accepted['status']=='PASS'
    rescore=read(run/'independent_rescore/ACCEPTANCE.json');assert rescore['maximum_component_difference']==0
    final=read(root/'analysis/final_test/SUMMARY.json');safety=read(root/'analysis/final_test/SAFETY.json')
    details=read(root/'analysis/final_test/DETAILS.json');rows=read(root/'analysis/final_test/rows.json')
    scores={r['arm']['id']:r for r in final['summaries']};safe={r['arm_id']:r for r in safety['records']}
    detail={r['arm_id']:r for r in details['records']};n=len(rows);narrative=read(root/'REPORT_NARRATIVE.json')
    figures=root/'figures'/args.version;assert not figures.exists();figures.mkdir(parents=True)
    images={};roles=[('safety_priority','安全优先','Safety priority'),('pdms_priority','PDMS优先','PDMS priority'),('action_control','尺度对照：PDMS优先','Scale PDMS'),('action_safety_control','尺度对照：安全准则优先','Scale safety')]
    role_id={role:lock['choices'][role]['summary']['arm']['id'] for role,_,_ in roles}
    colors=['#167d8d','#d17a36','#7756a2','#6b819a']
    def save(fig,name,caption):
        path=figures/(name+'.png');fig.canvas.draw();fig.savefig(path,dpi=155,bbox_inches='tight');fig.savefig(figures/(name+'.svg'),bbox_inches='tight');plt.close(fig)
        images[name]=f'<figure><img src="data:image/png;base64,{base64.b64encode(path.read_bytes()).decode()}" alt="{esc(caption)}"><figcaption>{esc(caption)}</figcaption></figure>'
    fig,ax=plt.subplots(figsize=(8.6,4.6))
    source_color={'n':'#167d8d','p':'#d17a36','fs':'#8a969c','ls':'#7756a2','action_space_control':'#c34d56'}
    for r in lock['all_development_candidates']:
        s=r['summary'];a=s['arm'];ax.scatter(100*s['high_damage_to_failure_rate'],s['mean_delta_pdms'],
            c=source_color.get(a['source'],'#7d8990'),marker={'none':'o','hard':'x','benefit':'^'}.get(a.get('gate','none'),'o'),s=30,alpha=.7)
    for role,_,label in roles:
        s=lock['choices'][role]['summary'];ax.annotate(label,(100*s['high_damage_to_failure_rate'],s['mean_delta_pdms']),xytext=(5,5),textcoords='offset points',fontsize=8)
    ax.axhline(0,color='grey',lw=.7);ax.scatter([0],[0],c='black',s=20)
    ax.set(xlabel='Original high-quality outputs becoming failures (%)',ylabel='Full development PDMS change (points)')
    fig.tight_layout();save(fig,'development_frontier','完整留出验证的修复—损伤分布；颜色区分自然/配对/固定与可学习空间/输出对照，形状区分无门控、风险门控和收益门控。此图用于开发选参。')
    fig,axes=plt.subplots(1,2,figsize=(10,4.1));x=np.arange(5)
    for i,(role,_,label) in enumerate(roles):
        s=scores[role_id[role]];values=[v['delta_pdms'] for v in s['by_seed']]
        width=.8/len(roles)
        axes[0].bar(x+(i-(len(roles)-1)/2)*width,values,width=width,label=label,color=colors[i])
        ledger=safe[role_id[role]]['by_seed'];new=np.mean([v['collision']['new'] for v in ledger])*10000/n
        removed=np.mean([v['collision']['removed'] for v in ledger])*10000/n
        axes[1].bar(i,new,color='#c34d56');axes[1].bar(i,-removed,color='#167d8d')
    axes[0].axhline(0,color='grey',lw=.7);axes[0].set(xticks=x,xticklabels=[f'S{j}' for j in range(5)],ylabel='Independent test PDMS change');axes[0].legend(fontsize=7)
    axes[1].axhline(0,color='grey',lw=.7);axes[1].set(xticks=range(len(roles)),xticklabels=[r[2] for r in roles],ylabel='NC penalty events per 10,000 cases / seed')
    axes[1].tick_params(axis='x',labelrotation=18)
    fig.tight_layout();save(fig,'independent_test','独立测试：左侧为五组配对自然采样的PDMS变化；右侧向上为新增碰撞项扣分事件，向下为消除事件。各采样共享相同病例，不能当成五倍独立病例。')
    matrix=np.load(root/'analysis/final_test/scores.npy',mmap_mode='r');ordered=read(root/'analysis/final_test/arms.json')
    arm_index={a['id']:i+1 for i,a in enumerate(ordered)};baseline=matrix[:,:,0]
    stable=(baseline[:,:,0]<.7).all(0);used=set();examples=[];tasks=read(run/'tasks.json')
    fig,axes=plt.subplots(2,2,figsize=(9,8))
    criteria=[('safety_priority','Stable failure repair','stable_repair'),('pdms_priority','Stable failure repair','stable_repair'),
        ('pdms_priority','Original success damage','damage'),('pdms_priority','New NC penalty','collision')]
    for ax,(role,label,kind) in zip(axes.flat,criteria):
        index=arm_index[role_id[role]];pred=matrix[:,:,index];delta=pred[:,:,0]-baseline[:,:,0]
        if kind=='stable_repair':
            mask=stable&(pred[0,:,0]>.9)
            if not mask.any():
                mask=(baseline[0,:,0]<.7)&(pred[0,:,0]>.9);label='S0 failure repair (no stable case)'
            ranking=delta.mean(0)
        elif kind=='damage':mask=(baseline[0,:,0]>.9)&(pred[0,:,0]<.7);ranking=-delta[0]
        else:mask=(baseline[0,:,1]==1)&(pred[0,:,1]<1);ranking=-delta[0]
        for i in used:mask[i]=False
        if not mask.any():ax.text(.5,.5,'Safety priority\nNo S0 complete failure repair\nStable-failure complete repair: 0',ha='center',va='center',transform=ax.transAxes);ax.axis('off');continue
        i=int(np.argmax(np.where(mask,ranking,-np.inf)));used.add(i)
        task=next(t for t in tasks if t['seed_index']==0 and t['start']<=i<t['end'])
        file=run/'results'/(task['id']+'.json');doc=read(file)
        b=next(r for r in doc['records'] if r['token']==rows[i]['token'] and r['arm']=='baseline')
        p=next(r for r in doc['records'] if r['token']==rows[i]['token'] and r['arm']==role_id[role])
        before=np.asarray(b['trajectory']);after=np.asarray(p['trajectory'])
        ax.plot(before[:,0],before[:,1],'-o',c='#26343c',ms=3,label='Base');ax.plot(after[:,0],after[:,1],'-o',c='#d17a36',ms=3,label='Edit')
        ax.scatter([0],[0],marker='^',c='black',s=20);ax.set_aspect('equal',adjustable='datalim');ax.grid(alpha=.2)
        ax.set(xlabel='Forward x (m)',ylabel='Lateral y (m)',title=f'{label}\nPDMS {100*b["score"]["score"]:.1f} -> {100*p["score"]["score"]:.1f}')
        ax.legend(fontsize=7)
        inset=ax.inset_axes([.57,.11,.38,.22]);inset.plot(np.arange(1,9)*.5,np.linalg.norm(after[:,:2]-before[:,:2],axis=1),c='#d17a36',lw=1)
        inset.set(xlabel='t (s)',ylabel='delta m');inset.tick_params(labelsize=6);inset.xaxis.label.set_size(6);inset.yaxis.label.set_size(6)
        examples.append(dict(role=role,criterion=kind,token=rows[i]['token'],base=b['score'],edited=p['score'],source=str(file.relative_to(ROOT)),sha256=sha(file)))
    fig.tight_layout();save(fig,'case_examples','病例仅作轨迹对照：按固定类型规则选取S0稳定失败修复、原高质退化及新增碰撞项扣分例子，后两类按最大PDMS损失展示；未绘制道路边界，不能仅由曲线外观判断碰撞原因。完整分布以全量统计为准。')
    atomic(figures/'CASE_EXAMPLES.json',examples)
    test_rows=[];safety_rows=[];seed_rows=[];parameter_rows=[]
    for role,label,_ in roles:
        s=scores[role_id[role]];ss=s['by_seed'];a=s['arm'];ledger=safe[a['id']]['by_seed']
        ci=s['session_bootstrap_delta_ci95'];base=np.mean([v['baseline_mean_pdms'] for v in ss]);mean=base+s['mean_delta_pdms']
        def total(key):return sum(v[key] for v in ss)
        def net(kind):return sum(v[kind]['net'] for v in ledger)
        test_rows.append([label,num(mean),f'{s["mean_delta_pdms"]:+.3f}<br>[{ci[0]:+.3f}, {ci[1]:+.3f}]',
            f'{total("repaired_ge70")}/{total("failures")}',f'{total("repaired_gt90")}/{total("failures")}',
            f'{total("high_to_le90")}/{total("high_quality")}',f'{total("high_to_failure")}/{total("high_quality")}'])
        safety_rows.append([label,f'{total("new_failure_from_nonfailure")}/{total("new_failure_from_nonfailure")-total("repaired_ge70"):+d}']+[f'{sum(v[k]["new"] for v in ledger)}/{net(k):+d}' for k in ['collision','offroad','ttc','zero']])
        for v,led in zip(ss,ledger):seed_rows.append([label,f'S{v["seed_index"]}',num(v['baseline_mean_pdms']),num(v['mean_pdms']),f'{v["delta_pdms"]:+.3f}',v['repaired_gt90'],v['high_to_failure'],led['collision']['new'],f'{led["collision"]["net"]:+d}'])
        parameter_rows.append([label,esc(a['id']),esc(a['method']),esc(a.get('source')),esc(a.get('layer','—')),esc(a.get('steps','—')),
            esc(a.get('k','—')),esc(a.get('alpha',a.get('factor','—'))),esc(a.get('gate','—')),esc(a.get('cap',0))])
    groups=[]
    for role,label,_ in roles:
        d=detail[role_id[role]];stable=d['by_mode']['stable_failure_all_sampling_seeds'];h=d['stable_success_damage']
        groups.append([label,stable['stochastic_outputs']//5,f'{stable["repair_gt90"]}/{stable["stochastic_outputs"]}',h['cases'],f'{h["to_failure"]}/{h["sampling_outputs"]}'])
    precision=[]
    for role,label,_ in roles:
        r=scores[role_id[role]]
        precision.append([label,f'{100*r["activation_rate"]:.3f}%',f'{100*r["failure_precision_of_activation"]:.3f}%',f'{100*r["positive_pdms_fraction_of_activation"]:.2f}%',f'{100*r["negative_pdms_fraction_of_activation"]:.2f}%',f'{r["displacement_max_m"]:.4f}'])
    methods=[]
    candidates=[r for r in lock['all_development_candidates'] if r['summary']['arm']['method']!='trajectory_scale']
    for method in ['mean','contract','soft_clip','ot','local','linear','mlp','quality']:
        pool=[r for r in candidates if r['summary']['arm']['method']==method]
        if not pool:continue
        s=max(pool,key=lambda r:r['summary']['mean_delta_pdms'])['summary']
        methods.append([method,esc(s['arm']['id']),f'{s["mean_delta_pdms"]:+.3f}',f'{100*s["complete_repair_rate"]:.2f}%',f'{100*s["high_damage_to_failure_rate"]:.3f}%'])
    matched=read(root/'analysis/validation_matched/SUMMARY.json');control=[];learned=[]
    for r in matched['summaries']:
        a=r['arm'];item=[esc(a['method']+'/'+a['source']),esc(a['alpha']),f'{r["mean_delta_pdms"]:+.3f}',f'{100*r["complete_repair_rate"]:.2f}%',f'{100*r["high_damage_to_failure_rate"]:.3f}%']
        (learned if a.get('matched_subspace_control') else control).append(item)
    parent=next(r for r in read(root/'analysis/validation_repair/SUMMARY.json')['summaries'] if r['arm']['id']==read(root/'MATCHED_VALIDATION_ENQUEUED.json')['parent']['id'])
    control.insert(0,['mean/p（匹配父配置）',esc(parent['arm']['alpha']),f'{parent["mean_delta_pdms"]:+.3f}',f'{100*parent["complete_repair_rate"]:.2f}%',f'{100*parent["high_damage_to_failure_rate"]:.3f}%'])
    null=read(root/'analysis/validation_true_random/SUMMARY.json');true_controls=[]
    null_run=ROOT/'runs'/read(root/'TRUE_RANDOM_READY.json')['run'];null_accepted=read(null_run/'FINAL_ACCEPTANCE.json');assert null_accepted['status']=='PASS'
    for item in null['summaries']:
        a=item['arm'];ci=item['session_bootstrap_delta_ci95']
        true_controls.append([esc(a['gaussian_null']),a['control_seed'],f'{item["mean_delta_pdms"]:+.3f} [{ci[0]:+.3f}, {ci[1]:+.3f}]',f'{100*item["complete_repair_rate"]:.2f}%',f'{100*item["high_damage_to_failure_rate"]:.3f}%'])
    comparisons=read(root/'analysis/final_test/FINAL_COMPARISONS.json');contrast_rows=[]
    for item in comparisons['records']:
        ci=item['session_bootstrap_ci95'];contrast_rows.append([esc(item['name']),f'{item["delta_pdms"]:+.4f}',f'[{ci[0]:+.4f}, {ci[1]:+.4f}]',f'{item["p_holm"]:.4g}'])
    parent_comparisons=read(root/'analysis/validation_true_random/PARENT_COMPARISONS.json');parent_rows=[]
    for item in parent_comparisons['comparisons']:
        ci=item['session_bootstrap_ci95'];parent_rows.append([esc(item['control']),f'{item["parent_minus_control_pdms"]:+.3f}',f'[{ci[0]:+.3f}, {ci[1]:+.3f}]'])
    devbase=ROOT/'runs'/lock['source_run'];stages=[]
    for folder in sorted((devbase/'stages').iterdir()):
        p=read(folder/'PROTOCOL.json');stages.append([esc(folder.name),p['scenes'],p['arms'],esc(p['seeds']),p['tasks']])
    for folder in sorted((null_run/'stages').iterdir()):
        p=read(folder/'PROTOCOL.json');stages.append([esc(folder.name),p['scenes'],p['arms'],esc(p['seeds']),p['tasks']])
    observation=read(ROOT/'analysis/two_route_conclusions.json');obs_tables=[]
    for scope,label in [('route1','路线一'),('route2','路线二')]:
        for item in observation['completion_checklist'][scope]:obs_tables.append([label,esc(item[0]),esc(item[1])])
    obs_fig=ROOT/'analysis/two_route_figures/route1_shared_distribution.png'
    obs_image=f'<figure><img src="data:image/png;base64,{base64.b64encode(obs_fig.read_bytes()).decode()}" alt="自然输出的共同坐标分布"><figcaption>原8维表征对照：自然成功与失败可检出结构差异，但分布仍明显重叠。</figcaption></figure>'
    extension=ROOT/'analysis/subspace_scan_v2/REPORT_SECTION.html';extended=extension.read_text() if extension.exists() else ''
    source=read(ROOT/'configs/baseline.json');development=read(devbase/'FINAL_ACCEPTANCE.json')
    paragraphs=''.join('<p>'+esc(p)+'</p>' for p in narrative['conclusions'])
    content=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RL Base表征与能力修复实验</title>
<style>body{{max-width:1180px;margin:32px auto;padding:0 20px;font:15px/1.8 system-ui,"Microsoft YaHei",sans-serif;color:#26343c}}h1{{font-size:27px}}h2{{font-size:21px;margin-top:32px}}.lead{{background:#edf6f5;border-left:4px solid #167d8d;padding:12px 18px}}.note{{background:#fff5e6;padding:12px 18px}}.muted,figcaption{{font-size:13px;color:#62717a}}table{{width:100%;border-collapse:collapse;font-size:12px;margin:16px 0}}td,th{{text-align:center;padding:8px;border-bottom:1px solid #dce4e8}}th{{background:#f2f6f7}}.long{{text-align:left}}figure{{margin:24px 0}}img{{max-width:100%;height:auto}}details{{border:1px solid #dce4e8;padding:12px 16px;margin:16px 0}}summary{{font-weight:600;cursor:pointer}}code{{font-size:12px;word-break:break-all}}.scroll{{overflow-x:auto}}</style>
<body><h1>RL Base内部表征与长尾能力修复</h1><p class="muted">ReCogDrive-2B-RL · NAVSIM PDM · 训练会话开发、冻结后独立测试 · {stamp()}</p><div class="lead">{paragraphs}</div>
<h2>表征中存在怎样的质量信息</h2><p>路线一为103,288条模型自然S0输出：90,153条&gt;90、2,288条&lt;70、10,847条中间质量。路线二为全部2,288个自然失败场景的模型失败—GT配对加噪续采，共45,760条最终候选；原GT不按90分预筛，质量标签在完整去噪后重评分确定。两种生成过程分开分析。</p><p>{esc(observation['conclusions'][1])}</p>{obs_image}{extended}
<details><summary>两路线观察覆盖与依据</summary>{table(['路线','项目','已完成范围'],obs_tables,left=(1,2))}<p>路线二的P0/P1固定投影支持部分可重复质量关联；碰撞/TTC与出界的结构不同。自然跨场景结构同时含场景/状态差异；配对结构也包含轨迹几何和初始化来源差异，不能单凭可分性认定失败原因。</p></details>
<h2>从结构差异到实际干预</h2><p>Base参数全程冻结。在自然类别残差空间、同场景配对差分空间中比较平移、收缩、软裁剪、Gaussian OT、局部映射、线性/MLP修正及质量探针梯度；另有固定/可学习子空间、真实自然成功回放、单token/窗口、多层/多步、强度和维数对照。所有输出完整去噪后重新PDM评分。干预索引0/1分别为动作编码/条件融合，2–17为DiT block0–15（384维）；最终512维输出另用于观察。</p>
<p>探索广筛使用全部1,850个探索失败、6,000个高质量与2,000个中间场景，选参时按真实类别分布重加权；配对映射仅用716组探索P0最终高/低配对。完整留出验证为17,475个新会话场景×S0/S1/S2。风险门控从自然探索高质样本校准，收益门控从探索实际干预结果拟合，推理输入不含GT或真实PDMS。</p>{images['development_frontier']}
<details><summary>不同机制的完整开发验证结果（各机制最高均分配置，非独立测试成绩）</summary>{table(['机制','配置ID','PDMS变化','&lt;70→&gt;90','&gt;90→&lt;70'],methods,left=(1,))}<p>未入选配置的完整探索结果保存在analysis/screen等阶段账本。</p></details>
<h2>锁定两种取舍后的独立测试</h2><p>安全优先和PDMS优先分别在开发集锁定；前者按已记录的非增净碰撞/出界/零分且均分非负准则选取，后者按最高均分选取，另分别保留按两种准则选择的简单输出尺度对照。安全合格开发候选数为{lock['eligible_repairs']}；若为0，安全端仅作最低损伤诊断，不能称为满足安全准则。配置、门控、拟合文件均在读取本轮测试数据前锁定。</p>
<p>独立测试覆盖{n:,}个场景、{details['sessions']}个采集会话，五组S0–S4自然采样。Base为同一RL权重新生成，与各修复逐场景逐种子共享初始和逐步噪声。下表事件数为五组输出合计，分母为对应输出数；统计置信区间按采集会话重采样，并在病例内平均采样种子。</p><div class="scroll">{table(['候选','平均PDMS','ΔPDMS [95% CI]','失败→≥70','失败→&gt;90','高质→≤90','高质→失败'],test_rows)}</div><p>安全项均列新增/净变化：碰撞、出界与TTC事件分别指NC、DAC与TTC评分项低于1；零分事件指PDMS=0。</p>{table(['候选','PDMS失败','碰撞NC','出界DAC','TTC','零分'],safety_rows)}{images['independent_test']}
<details><summary>预设配对比较：相对Base及同取舍尺度对照</summary><p>四个差值在正式独立测试计算前预先登记；先在每场景内平均五种子，再按采集会话bootstrap，并对四个单侧会话sign-flip检验作Holm校正。CI为描述性95%区间，校正后的p另列。</p>{table(['比较','ΔPDMS','会话95% CI','Holm p'],contrast_rows,left=(0,))}</details><details><summary>逐种子成绩与固定候选配置</summary>{table(['候选','采样','Base','候选','ΔPDMS','完整修复','高质→失败','新增碰撞','净碰撞'],seed_rows)}<div class="scroll">{table(['候选','配置ID','方法','空间','层','采样步index','编辑维数','α/scale','门控','单位置cap'],parameter_rows,left=(1,))}</div></details>
<details><summary>持续失败与持续成功病例（描述性分析）</summary>{table(['候选','五种子均失败病例','其&gt;90输出/总输出','五种子均高质病例','其失败输出/总输出'],groups)}<p>稳定组由Base五组输出定义；修复与损伤仍逐种子和对应Base配对，不把换种子后Base自己变好的病例算成干预修复。固定S0失败组的Base/候选覆盖与新增/损失高质量数另见DETAILS.json。</p></details>
<h2>干预精准性与对照</h2><p>激活失败精度指被编辑输出中、对应Base本来&lt;70的比例；Base总体失败占比为7.028%。微小分数波动也计入加/扣分比例，不能只据变化次数判断净收益。</p>{table(['候选','激活比例','激活失败精度','激活后加分','激活后扣分','最大轨迹位移m'],precision)}<details open><summary>固定与可学习子空间、匹配随机和反向对照</summary><p>rank16可学习空间与固定空间使用同样716组探索配对、相同初始化、MLP和400更新，仅空间是否学习不同；配对高质量分支加恒等约束，未宣称包含真实自然成功回放。训练损失下降与自然输出修复分别核查。</p>{table(['方法/空间','α','完整验证ΔPDMS','失败→&gt;90','高质→失败'],learned)}{table(['匹配方向对照','α','完整验证ΔPDMS','失败→&gt;90','高质→失败'],control)}<p>上表原random/random_subspace是固定sin方向及sin矩阵QR，明确保留为非任务构造，不能据此概括一般随机空间。下表是另外三个构造种子的高斯方向及Gaussian-QR同维空间，与父配置匹配层、步、强度和每token编辑范数；三个构造重复分别报告，不作为独立病例扩大样本量。该父配置为α0.25无门控平移；最终PDMS候选为α0.5收益门控，随机结果不冒充最终配置的严格匹配对照。</p>{table(['真正随机构造','构造种子','完整验证ΔPDMS [95% CI]','失败→&gt;90','高质→失败'],true_controls)}{table(['父平移减随机对照（完整开发集配对）','ΔPDMS','会话95% CI'],parent_rows,left=(0,))}<p>随机对照中发生修复不等于正向方法具备精准性。简单轨迹scale对照检验部分收益是否仅来自统一进度偏移。</p></details>
<p>{esc(narrative['interpretation'])}</p>{images['case_examples']}<p>{esc(narrative['decision'])}</p>
<details><summary>强度、诊断和实验覆盖</summary><p>主r8，r4/16/32及α、cap扫描；单位置按当前token hidden范数截断。严格多点预算是跨位置相对编辑范数的L2合成≤0.05，并非L1累加≤0.05。几何位移和二阶差分变化已保存，不把hidden范数上限当作行为安全保证。</p><p>同场景高质量参考表征注入只作特权诊断，不参与可部署方法选模；无可用参考的病例保持恒等，同时单列参考可用子集。候选Oracle只覆盖本次明确评估的候选集合，不能视为所有表征修复的上界。</p>{table(['阶段','场景','干预配置','自然采样index','任务分块'],stages,left=(0,))}<p>训练广筛含均值/paired等效别名与限幅后相同输出，不把配置数当成互相独立的能力。完整搜索与全部未选结果保留。</p></details>
<details><summary>复现、验收与适用范围</summary><p>权重SHA256：<code>{source['checkpoint_sha256']}</code>。FP32、batch1、eval/no_grad；347个active tensor严格加载，排除347个训练old_policy tensor。原DDIM五步[80,60,40,20,0]、eta=1、原裁剪。自然根种子20261008，逐场景<code>int(sha256(f"{{token}}|20261008|{{j}}").hexdigest()[:8],16)</code>；P0/P1参考噪声另用根种子20261016。</p><p>开发验收{development['tasks']:,}分块/{development['records']:,}输出，测试验收{accepted['tasks']:,}分块/{accepted['records']:,}输出；全部轨迹/评分/输入覆盖和SHA已核查。600条分层保存轨迹经共享只读原始评分入口重算，各分项最大差异0。两节点各16卡实际冒烟与DSW精确一致，α0、完整/缓存前缀采样及重复采样一致。</p><p>旧调度版本出现共享queue临时文件重命名ENOENT，原异常保留；新版本移除全局计数器依赖及跨容器重复PID临时命名，使用UUID临时文件和mkdir领取任务，逐hash复用5612个已完成分块，不把恢复任务当新增独立样本。代码与输入/参数来源位于<code>1016-rl_representation_analysis/code/repair_*.py</code>、<code>repair_v1/</code>，开发run为<code>{lock['source_run']}</code>，测试run为<code>{ready['run']}</code>。选择锁为<code>repair_v1/TEST_LOCK.json</code>，评分与分病例账本在<code>repair_v1/analysis/</code>。</p><p>按用户新指令，计算验收后原2×16卡保持运行与队列等待，未以退出/释放作为成功条件；12小时总运行时限继续计时，延长尚未验证。资源状态与保留验收记录独立于实验结论。PDM为离线候选仿真评价，本轮尚未完成真实交互闭环验证。</p><p>置信区间为会话cluster bootstrap500；开发大网格属探索选择，独立测试不再调参。未观察到的损伤不能解释为真实发生概率为零。HTML结构、核心数字、图片与来源核查另留验收；未宣称浏览器视觉验收。</p></details></body></html>'''
    report=ROOT.parent/'doc/work-output/1016-rl_representation_analysis/representation_observation.html'
    archive=ROOT/'provenance/report_versions'/args.version;archive.mkdir(parents=True,exist_ok=False)
    shutil.copy2(report,archive/'previous.html');old=sha(report)
    shutil.copy2(root/'REPORT_NARRATIVE.json',archive/'REPORT_NARRATIVE.json')
    shutil.copy2(Path(__file__),archive/'report_generator.py')
    staging=archive/'new.html';staging.write_text(content);shutil.copyfile(staging,report)
    atomic(archive/'BUILD.json',dict(status='COMPLETE',time=stamp(),report=str(report),previous_sha256=old,report_sha256=sha(report),
        figures=str(figures.relative_to(ROOT)),test_lock_sha256=sha(root/'TEST_LOCK.json'),narrative_sha256=sha(root/'REPORT_NARRATIVE.json'),
        browser_render_verified=False,extension_included=extension.exists()))
    print(json.dumps(dict(status='COMPLETE',report=str(report),bytes=report.stat().st_size,sha256=sha(report))),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--version',required=True);args=p.parse_args();setup('repair/report');build(args)
