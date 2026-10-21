"""Compact scientific sections for frozen repetition and natural confirmation."""
from r2_common import *
from r2_report_batch2 import esc,table


def compact(value,depth=0):
    if isinstance(value,list):
        if len(value)>12:
            return dict(items=len(value),first=[compact(v,depth+1) for v in value[:3]],
                last=[compact(v,depth+1) for v in value[-2:]],
                note='此处仅显示首尾摘要；完整原始数据保留在所列来源文件中。')
        return [compact(v,depth+1) for v in value]
    if isinstance(value,dict):return {k:compact(v,depth+1) for k,v in value.items()}
    return value


def sections(source):
    n=lambda x:format(x,'+.4f')
    seq=lambda x:' / '.join(n(v) for v in x)
    detail=lambda title,body:'<details><summary>'+esc(title)+'</summary>'+body+'</details>'
    output=[]
    teacher=source('analysis/frozen_privileged_repair_envelope/TEACHER_POTENTIAL_REPORT_ROWS.json',True)
    if teacher:
        output+=['<h3>路由较差，是否仍有离线教师潜力</h3>',
            '<p>对冻结探索家族全部4,549条完整五折策略，仅归约已有真实评分，分别计算完美失败触发、有益才替换及S0固定Base／策略分支。原实际收益全部复现至10⁻¹⁰分，未新增模型、轨迹或评分，也未改变确认方案。下表按538个完整三拟合家族中“有益才替换的最差拟合均值”排列，只作事后潜力诊断。</p>',
            table(['家族／策略','实际路由Δ（三拟合）','只改Base失败Δ','有益才替换Δ','S0固定策略分支Δ','有益替换探索净安全'],[
                (' / '.join(r['key']),seq(r['actual']['fit_mean_gains']),
                 seq(r['perfect_failure_trigger']['fit_mean_gains']),seq(r['beneficial_only']['fit_mean_gains']),
                 seq(r['S0_fixed_Base_or_policy_branch']['fit_mean_gains']),
                 ' / '.join('通过' if v else '未通过' for v in r['protected_event_nonincrease_every_noise_by_fit']['beneficial_only']))
                for r in teacher['rows'][:5]],long=(0,)),
            '<p>最强的一组已知反事实中，实际路由约−1.04至−1.22分，完美失败触发约+0.45至+0.51分，有益才替换约+0.62至+0.66分，三次均通过探索标准化净碰撞／出界／零分约束。这支持把在线选择失败与候选修复潜力分开讨论；净安全通过仍不代表逐样本无新增损伤。</p>',
            '<p>“有益才替换”只是在Base和一条既定策略输出之间事后选优，并非把4,549条策略合并成巨大候选库。“S0固定策略分支”只固定采用Base还是该策略，该策略在新噪声仍可能换专家／力度，因此不能称固定专家或固定内部表征。这些是失败富集探索面板的类别标准化结果，不能当作完整自然总体、独立测试或蒸馏学生成绩。</p>']
    selection=source('provenance/final_confirmation/SELECTION.json',True)
    if selection:
        output+=['<h3>最后空间候选与冻结规则</h3>',
            '<p>最后三个竞争区域分别完成原22配方、三次独立完整拟合。完整探索快照在自然确认前冻结；538个配方具有完整三拟合复验，15个三次均值均正，0个在全部拟合及开发噪声均正，0个全部正且满足探索安全约束。所有零／负结果保留。</p>',
            table(['冻结角色','系统／方法／信息','三次独立拟合ΔPDMS','三次探索安全','正式含义'],[
                (r['role'],' / '.join(r['key']),seq(r['fit_mean_gains']),' / '.join('通过' if v else '未通过' for v in r['fit_safety']),
                 '非零诊断候选；未建立稳定提升') for r in selection['selected_families']],long=(0,1,4)),
            '<p>安全角色按每次拟合、每个开发噪声的净碰撞／出界／零分约束筛选；PDMS角色按三次平均收益，稳健性对照按最差一次拟合的平均收益排序。全部三次拟合保留，Base始终保留。稳健性对照并不代表对未见噪声有最坏情况保证。相同10策略家族在自然验证前已经同时冻结为最终测试家族，验证和测试均不重选。</p>']
        for stem in ['response_spatial_K2','representation_spatial_K6','response_spatial_K6']:
            d=source('analysis/selected_spatial_final_replication/'+stem+'_ALL66_REVIEW.json',True)
            if d:
                output.append(detail(stem+'：完整22配方三拟合复验',table(
                    ['方法／信息','三次ΔPDMS','全部拟合×噪声正','三次探索安全'],
                    [(r['method']+' / '+r['policy'],seq(r['fit_mean_gains']),r['allfit_allnoise_positive'],
                      ' / '.join(str(v) for v in r['fit_safety'])) for r in d['recipes']],long=(0,))))
    precision=source('provenance/final_confirmation/EXPLORATORY_PRECISION_ACCEPTANCE.json',True)
    if precision:
        output+=['<h3>探索统计的分辨率与可复现性</h3>',
            '<p>4,549个完整五折配方统一进行1,819,599次、130会话的符号翻转近似检验。Holm点估计有1条正向、253条负向通过；正向是correction-K3联合软修复／安全／轨迹，首拟合+0.09920点，另两次−0.09335、−0.06605点。其校正p点估计约0.04494，原始Monte Carlo标准误约2.40×10⁻⁶，位于判定边界附近；不能把它写成强而稳定的证据。</p>',
            '<p>原1,000次符号重采样的最小p值高于本家族首个Holm门槛，旧“未显著”本身不能支持负结论。增加重采样只解决数值精度，不消除探索选择或创造独立数据。</p>']
    output.append('<h3>冻结后的完整自然总体评价</h3>')
    for mode,label in [('validation','自然验证'),('test','最终测试')]:
        path='analysis/frozen_natural_assessment/batch2_'+mode+'_v1_assessment/SUMMARY.json'
        d=source(path,True)
        if d is None:
            output.append('<p>'+label+'尚未完成；不以探索结果替代。</p>');continue
        assert d['mode']==mode
        final_audit=source('runs/frozen_natural_'+mode+'_batch2_three_roles_v1/AGENT_FINAL_ACCEPTANCE_V1.json')
        stats=source('analysis/confirmation_statistics/batch2_'+mode+'_v1_statistics/SUMMARY.json',True)
        stability=source('analysis/frozen_stability_diagnostics/batch2_'+mode+'_v1_stability/SUMMARY.json',True)
        base=next(iter(d['results'].values()))['Base_PDMS_by_noise']
        output+=['<h4>'+label+'</h4>',
            '<p>'+str(d['cases'])+'场景、'+str(d['sessions'])+'会话，配对S'+('/S'.join(str(v) for v in d['noise_indices']))+'。Base各噪声PDMS：'+seq(base)+'。下表PDMS及区间单位为分；事件为各噪声输出的计数，噪声重复不增加独立场景数。</p>',
            table(['策略／拟合','ΔPDMS','各噪声Δ','95%会话区间','安全约束','失败→≥70 / >90','高质→≤90 / <70'],[
                (ident,n(r['mean_PDMS_gain']),seq(r['PDMS_gain_by_noise']),seq(r['session_bootstrap_95']),
                 '通过' if r['safety_all_noise'] else '未通过',
                 str(sum(r['repaired70_by_noise']))+' / '+str(sum(r['repaired90_by_noise'])),
                 str(sum(r['lost_high_by_noise']))+' / '+str(sum(final_audit['additional_high_to_failure'][ident]['high_to_failure_by_noise']))) for ident,r in d['results'].items()],long=(0,)),
            '<p>“Safety”是冻结候选的筛选角色，不代表自然验证或测试已通过安全约束。冻结安全判据要求每个噪声分别满足净碰撞／出界／零分不增加：五噪声合计减少，仍可能因某一个噪声增加而未通过。TTC与总失败另列。原高质量损伤与失败修复的分母不同，不能直接当作同一比例比较。</p>']
        safety_rows=[]
        for ident,r in d['results'].items():
            new=[sum(v[i] for v in r['newly_bad_by_noise']) for i in range(5)]
            resolved=[sum(v[i] for v in r['resolved_bad_by_noise']) for i in range(5)]
            safety_rows.append((ident,*[f'{a} / {b} / {a-b:+d}' for a,b in zip(new,resolved)]))
        output.append(detail(label+'：安全事件新增／消除／净变',table(
            ['策略','碰撞','出界','零分','TTC','总失败'],safety_rows,long=(0,))))
        per_noise=[]
        for ident,result in d['results'].items():
            for noise,net in zip(d['noise_indices'],result['net_bad_by_noise']):
                per_noise.append((ident,'S'+str(noise),*net))
        output.append(detail(label+'：每个噪声的净事件，复核安全判据',table(
            ['策略','噪声','碰撞','出界','零分','TTC','总失败'],per_noise,long=(0,))))
        if stats:
            output.append(detail(label+'：冻结比较家族的会话不确定性及Holm',
                '<pre>'+esc(json.dumps(compact(stats),ensure_ascii=False,indent=2))+'</pre>'))
        if stability:
            output.append(detail(label+'：观察到的稳定失败／稳定高质量及反转样本',
                '<pre>'+esc(json.dumps(compact(stability),ensure_ascii=False,indent=2))+'</pre>'))
        pack=source(d['pack']);part_counts={}
        for entry in pack['policies']:
            if entry['kind']=='Base':continue
            policy=source(entry['policy'])
            own=policy['configuration']['model']['parts'] if entry['kind'] in ['joint','finite'] else policy['parts']
            part_counts[entry['id']]=len(own)
        oracle=[]
        for ident,diagnostic in d['privileged_diagnostics'].items():
            matched=next((v for k,v in diagnostic.items() if k.startswith('matched_')),None)
            gain=lambda key:n(diagnostic[key]['mean_PDMS_gain'])
            oracle.append((ident+' (K='+str(part_counts[ident])+')',n(d['results'][ident]['mean_PDMS_gain']),gain('perfect_failure_trigger'),
                gain('beneficial_replacement_only'),gain('actual_candidate_oracle'),
                gain('per_case_safety_constrained_oracle'),gain('S0_fixed_candidate_cross_noise'),
                gain('all_noise_privileged_scene_fixed_oracle'),n(matched['mean_PDMS_gain']) if matched else '未计算'))
        output+=['<h4>'+label+'：事后选择与精准触发的上限诊断</h4>',
            table(['固定策略','实际Δ','仅改Base失败','有益才替换','自身K＋Base Oracle',
                   '安全约束Oracle','S0选定跨噪声固定','全噪声共同选固定分支','同候选数Base重采样'],oracle,long=(0,)),
            '<p>每项都来自真实完整轨迹与真实评分；各策略只用自己的专家集合，不能把缓存中的角色／拟合／K的合集冒充它自身的候选数。仅改失败知道Base是否低于70，仍可能修坏；有益才替换还知道候选真实收益。逐输出Oracle在每个噪声重新选，S0固定选择检验后续噪声迁移，全噪声共同选固定分支则同时看了全部噪声结果，三者特权程度不同。</p>',
            '<p>匹配Base重采样只匹配候选机会数，不能替代真实部署选择器；Oracle增益也不等于蒸馏后学生收益。下一阶段是否能通过轨迹＋内部表征联合监督优于仅轨迹监督，本批未做实验。</p>']
        repair_rows=[]
        for ident,diagnostic in d['privileged_diagnostics'].items():
            for name,value in diagnostic.items():
                net=[sum(v[i] for v in value['net_bad_by_noise']) for i in range(3)]
                repair_rows.append((ident,name,
                    str(sum(value['repaired70_by_noise']))+' / '+str(sum(value['repaired90_by_noise'])),
                    sum(value['lost_high_by_noise']),' / '.join(str(v) for v in net),
                    '通过' if value['safety_all_noise'] else '未通过',seq(value['PDMS_gain_by_noise'])))
        output.append(detail(label+'：全部特权规则的修复数量、损伤、安全与噪声明细',
            table(['策略','特权规则','失败→≥70 / >90','原高质→≤90',
                   '净NC / DAC / 零分','每个噪声安全','各噪声ΔPDMS'],repair_rows,long=(0,1))))
    natural_figures=source('analysis/report_natural_figures/LATEST.json',True)
    if natural_figures:
        import base64
        assert sha(ROOT/natural_figures['path'])==natural_figures['sha256']
        manifest=source(natural_figures['path'])
        for figure in manifest['figures']:
            data=base64.b64encode((ROOT/figure['png']).read_bytes()).decode()
            output.append('<figure><img src="data:image/png;base64,'+data+'" alt="'+esc(figure['name'])+'"><figcaption>'+esc(figure['caption'])+'</figcaption></figure>')
    output+=['<h3>结论适用范围</h3>',
        '<p>本批把实际可控性、候选库的特权选择潜力、可观察路由及新场景泛化分别验证。路由不稳定不能单独证明离线教师没有价值；强特权优化也不能证明相同能力已经由通用修复器或学生获得。本批未训练蒸馏学生，未检验联合蒸馏相对仅轨迹监督的增量。</p>']
    return output
