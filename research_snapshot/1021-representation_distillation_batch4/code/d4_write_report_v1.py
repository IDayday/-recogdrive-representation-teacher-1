"""One concise Chinese report, generated only from accepted full comparisons."""
from d4_common_v2 import *
from html import escape
import base64


def display(value,digits=4):
    return '—' if value is None else f'{value:.{digits}f}'


def table(head,rows,left_columns=()):
    def cells(tag,row):
        return ''.join('<'+tag+(' class="left"' if i in left_columns else '')+'>'+str(x)+'</'+tag+'>' for i,x in enumerate(row))
    return '<div class="scroll"><table><thead><tr>'+cells('th',head)+'</tr></thead><tbody>'+''.join('<tr>'+cells('td',r)+'</tr>' for r in rows)+'</tbody></table></div>'


def main():
    setup('report_v1',threads=4)
    comparison_path=ROOT/'analysis/distillation_comparison_v1/SUMMARY.json';comparison=read(comparison_path)
    assert comparison['status']=='PASS_COMPLETE_PAIRED_H_T_HT_COMPARISON'
    from d4_compare_students_v1 import load
    scopes=['navtrain_S0S4','validation_S5S9','navtest_S0S9'];roles=['primary_final','secondary_development_best']
    models={(g,r,s):load(g,r,s) for g in ['H','T','HT'] for r in roles for s in scopes}
    def group_summary(group,role,scope,subset=None):
        summary=models[group,role,scope]['summary']
        return summary['results'][subset] if subset else next(iter(summary['results'].values()))
    def score(group,scope,noise='S0S4',subset=None,role='primary_final'):
        return group_summary(group,role,scope,subset)['noise_groups'][noise]
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figure,axes=plt.subplots(1,4,figsize=(13,3.2),sharey=True)
    panels=[('navtrain_S0S4','S0S4','validation','Validation S0-S4'),('validation_S5S9','S5S9',None,'Validation S5-S9'),
        ('navtest_S0S9','S0S4',None,'Test S0-S4'),('navtest_S0S9','S5S9',None,'Test S5-S9')]
    for ax,(scope,noise,subset,title) in zip(axes,panels):
        ax.axvline(0,color='#94a3b8',linewidth=1)
        for i,(group,color) in enumerate([('H','#4477aa'),('T','#cc6677'),('HT','#228833')]):
            value=score(group,scope,noise,subset);interval=value['gain_session_bootstrap_CI95']
            ax.hlines(i,interval[0],interval[1],color=color,linewidth=2)
            ax.scatter([value['gain']],[i],color=color,s=35,zorder=3)
        ax.set_title(title,fontsize=11);ax.set_xlabel('PDMS gain vs Base');ax.set_yticks([0,1,2],['H','T','HT']);ax.grid(axis='x',alpha=.2)
    axes[0].invert_yaxis();figure.suptitle('Final epoch; paired session bootstrap 95% intervals',fontsize=12);figure.tight_layout()
    chart=ROOT/'analysis/distillation_comparison_v1/figures/generalization_gain.png';chart.parent.mkdir(parents=True,exist_ok=True)
    figure.savefig(chart,dpi=180,bbox_inches='tight');plt.close(figure)
    contrast=comparison['results']['primary_final']['navtrain_S0S4']['contrasts']['HT_minus_T']['validation']['S0S4']
    ci=contrast['difference_session_bootstrap_CI95'];d=contrast['difference']
    verdict=('联合监督在留出场景上优于仅轨迹监督' if ci[0]>0 else '联合监督在留出场景上弱于仅轨迹监督' if ci[1]<0 else '尚未确认联合监督优于仅轨迹监督')
    validation=score('HT','navtrain_S0S4',subset='validation');vci=validation['gain_session_bootstrap_CI95']
    transfer=('HT相对Base的留出增益为正，且会话置信区间排除零' if vci[0]>0 else
              'HT相对Base的留出退化，且会话置信区间排除零' if vci[1]<0 else 'HT相对Base的留出增益尚不明确')
    body=[f'<h1>首版42候选教师的接口与轨迹蒸馏</h1><p class="meta">第四批首轮 · {escape(stamp())} · 主结果为全训练＋验证；测试单列参考</p>',
        '<div class="finding"><strong>'+verdict+'。</strong> 在固定教师、相同初始化、训练范围和曝光下，HT−T的验证PDMS差为 '+display(d)+' 分，95%会话区间 ['+display(ci[0])+', '+display(ci[1])+']。'+transfer+'。</div>',
        '<p>这是一个初始化种子、自然I/P采样和当前损失配比下的首轮比较。会话区间不包含训练种子的变异；三组尚未各自完成学习率搜索，T不能代表充分调优后的轨迹蒸馏。结果不能推广为所有容量、采样或蒸馏方法的结论。这里的独立验证指本轮学生梯度训练的留出，不表示RL Base历史训练完全未见这些场景。教师事后Oracle与学生单模型成绩分别呈现。</p>',
        '<h2>完整训练＋验证：学生吸收了多少教师收益</h2>',
        '<p>主比较使用最终第5个epoch，三组均6670优化步、426880次场景曝光，包含85339个不同训练场景。总体103288场景包含验证17475场景，整体成绩不能称为独立泛化。</p>']
    rows=[]
    for name,subset in [('完整训练＋验证',None),('探索训练','exploration'),('独立验证','validation')]:
        h,t,ht=[score(g,'navtrain_S0S4',subset=subset) for g in ['H','T','HT']]
        rows.append([name,h['cases'],display(h['Base_PDMS']),display(h.get('fixed_R2_teacher_PDMS')),
            display(h['PDMS']),display(h['gain']),display(t['PDMS']),display(t['gain']),display(ht['PDMS']),display(ht['gain']),
            display(ht.get('teacher_gain_absorption'),3)])
    body.append(table(['范围','场景','Base','固定R2教师','H','H增益','T','T增益','HT','HT增益','HT吸收比'],rows,(0,)))
    body.append('<p>旧噪声S0～S4均为每场景五次实际执行。吸收比=(学生−Base)/(固定教师−Base)，不是理论上界；新噪声没有实算教师分母，不沿用旧分母。</p>')
    body.append('<h2>独立场景与新噪声</h2>')
    rows=[]
    for scope,noise,title,subset in [('navtrain_S0S4','S0S4','验证／原五噪声','validation'),
        ('validation_S5S9','S5S9','验证／新五噪声',None),('navtest_S0S9','S0S4','测试／原五噪声',None),('navtest_S0S9','S5S9','测试／新五噪声',None)]:
        for g in ['H','T','HT']:
            value=score(g,scope,noise,subset);interval=value['gain_session_bootstrap_CI95']
            rows.append([title,g,value['cases'],display(value['Base_PDMS']),display(value['PDMS']),display(value['gain']),
                '['+display(interval[0])+', '+display(interval[1])+']'])
    body.append(table(['范围','组别','场景','配对Base','学生PDMS','增益','95%会话区间'],rows,(0,)))
    body.append('<img alt="H、T、HT在验证和测试两组噪声上的PDMS增益与会话区间" style="width:100%;height:auto" src="data:image/png;base64,'+base64.b64encode(chart.read_bytes()).decode()+'">')
    body.append('<p>所有配置与测试范围在学生测试之前冻结；仅512例固定开发面板的五个epoch端点用于辅助权重选择。S5～S9不进入教师选择、训练或checkpoint选择。</p>')
    body.append('<h2>联合监督相对轨迹监督</h2>')
    rows=[]
    for scope,noise,title,subset in [('navtrain_S0S4','S0S4','完整训练＋验证','all'),('navtrain_S0S4','S0S4','独立验证','validation'),
        ('validation_S5S9','S5S9','验证新噪声','all'),('navtest_S0S9','S0S4','测试原噪声','all'),('navtest_S0S9','S5S9','测试新噪声','all')]:
        for pair in ['HT_minus_T','H_minus_T','HT_minus_H']:
            value=comparison['results']['primary_final'][scope]['contrasts'][pair][subset][noise];interval=value['difference_session_bootstrap_CI95']
            rows.append([title,pair.replace('_minus_',' − '),display(value['difference']), '['+display(interval[0])+', '+display(interval[1])+']'])
    body.append(table(['范围','比较','PDMS差','95%会话区间'],rows,(0,)))
    body.append('<h2>能力保持与安全分项</h2><p>I为教师五次均分有真实提升；P为无提升且Base均分>90；E为其余，仅评价。主学生不接收是否修复、PDMS或专家ID输入。下表为原五噪声中的事件数量变化，不作为结果筛选条件。</p>')
    rows=[]
    for subset,title in [(None,'完整训练＋验证'),('validation','独立验证')]:
        for g in ['H','T','HT']:
            value=score(g,'navtrain_S0S4',subset=subset);safe=value['safety_events']
            rows.append([title,g,value['Base_high_to_not_high'],value['Base_high_to_failure'],value['zero_outputs'],value['failure_outputs_below70'],
                safe['no_at_fault_collisions']['net'],safe['drivable_area_compliance']['net'],safe['time_to_collision_within_bound']['net']])
    body.append(table(['范围','组别','Base>90降至≤90','Base>90降至<70','学生零分','学生<70','净新增碰撞','净新增出界','净新增TTC扣分'],rows,(0,)))
    rows=[]
    for pool in ['I','P','E']:
        for g in ['H','T','HT']:
            value=group_summary(g,'primary_final','navtrain_S0S4','reference_pool_'+pool)['noise_groups']['S0S4']
            rows.append([pool,g,value['cases'],display(value['Base_PDMS']),display(value['PDMS']),display(value['gain'])])
    body.append(table(['池','组别','场景','Base','学生','增益'],rows))
    body.append('<h2>接口拟合与行为迁移</h2>')
    fitting=comparison['results']['primary_final']['navtrain_S0S4']['interface_fitting'];rows=[]
    for name,title in [('exploration','探索训练'),('validation','独立验证'),('hard_I','难例提升池'),('other_I','其余提升池'),('pool_P','保持池')]:
        if name not in fitting:continue
        value=fitting[name]
        rows.append([title,value['cases'],display(value['Base_initial_interface_MSE'],6)]+[display(value['students'][g]['interface_MSE'],6) for g in ['H','T','HT']])
    body.append(table(['范围','场景','原Base接口MSE','H接口MSE','T接口MSE','HT接口MSE'],rows,(0,)))
    rows=[]
    fitting=comparison['results']['primary_final']['navtrain_S0S4']['trajectory_fitting_to_fixed_R2']
    for subset,title in [('all','完整训练＋验证'),('validation','独立验证'),('pool_P','保持池')]:
        for group in ['H','T','HT']:
            value=fitting[group]['metrics'][subset];before=value['Base_errors_to_teacher'];after=value['student_errors_to_teacher']
            rows.append([title,group,display(before['training_proxy'],7),display(after['training_proxy'],7),
                display(before['ADE_metres'],4),display(after['ADE_metres'],4),value['proxy_improved_but_PDMS_worsened_outputs']])
    body.append(table(['范围','组别','Base轨迹代理误差','学生轨迹代理误差','Base ADE/米','学生 ADE/米','代理更好但PDMS更差的输出'],rows,(0,)))
    body.append('<p>轨迹误差只与S0～S4实际固定R2轨迹对齐，独立以float64计算；航向按周期处理。更接近教师轨迹仍可能跨过碰撞、越界、TTC等评分边界，相关计数只用于诊断，不反向选择模型。没有新噪声教师轨迹时不计算对应拟合或吸收指标。</p>')
    body.append('<p>接口MSE覆盖动作头实际使用的完整token，包括padding；不把不可解释性当作失败，也不把MSE下降直接等同于行为提升。1847个Base至少一次低于70的训练提升场景贡献约62.2%教师总增益，仅占约5.55%初始接口损失、11.31%初始轨迹代理损失；这些是损失分布观察，不是梯度贡献或因果结论。该发现未用于改变本轮自然比例配置。</p>')
    body.append('<details><summary>辅助口径：开发集选优checkpoint</summary><p>只在预设五个epoch端点按开发PDMS选优；没有用测试、新噪声或额外安全门槛选择。若与末epoch相同，保留别名而不重复训练。不同组可能选中不同曝光，因此主结论仍使用末epoch。</p>')
    rows=[]
    for g in ['H','T','HT']:
        model=models[g,'secondary_development_best','navtrain_S0S4']['model'];value=score(g,'navtrain_S0S4',subset='validation',role='secondary_development_best')
        rows.append([g,model['checkpoint']['epoch'],model['checkpoint']['global_step'],display(value['PDMS']),display(value['gain']),escape(model['id'])])
    body.append(table(['组别','epoch','步数','完整验证PDMS','增益','模型ID'],rows,(5,))+'</details>')
    body.append('<details><summary>方法、种子与复核来源</summary><p>RL Base epoch24/global_step8325；首版42候选的固定R2教师。全程无GT。视觉24层／语言28层292处LoRA，rank16/alpha32/dropout0；两处投影全参，其他原参数和动作生成网络冻结，梯度穿原生DDIM。34008448个可训练参数。自然I/P采样，global batch64，16卡每卡micro1、累积4；LoRA学习率5e−5、投影1e−4，AdamW，200步warmup后cosine。H为完整接口MSE；T为归一化位置SmoothL1＋0.1航向周期损失；HT权重1与80.21022962075446，由训练侧接口梯度校准，未用测试定权。</p>')
    body.append('<p>初始化种子2026102101；数据顺序2026102102；开发面板2026102105；动作随机流沿用 sha256(token|20261008|j) 前8位十六进制整数，j=0…9。完整随机流含各步追加噪声，不使用rank／GPU编号定种子。五epoch每场景轮换S0～S4。训练5epoch预算相同，185次尾部重复曝光已记录。</p>')
    sources=['PLAN.md','provenance/MAIN_CONFIGS_V4.json','provenance/FROZEN_EVALUATION_PROTOCOL_V1.json',
        'provenance/TRAINING_PROGRAM_ENGINEERING_ACCEPTANCE_V4.json','provenance/STUDENT_FULL_EVALUATION_SMOKE_V1.json',
        'analysis/teacher_geometry_v1/SUMMARY.json','analysis/initial_trajectory_geometry_v1/SUMMARY.json','analysis/distillation_comparison_v1/SUMMARY.json','code/d4_compare_students_v1.py','code/d4_write_report_v1.py']
    body.append('<ul>'+''.join('<li><code>'+escape(str(ROOT/path))+'</code></li>' for path in sources)+'</ul>')
    body.append('<p>所有正式评分由原生实际轨迹独立评分；旧Base五采样逐条核对首42，新噪声现场跑Base并重放S0。固定R2接口目标完整重放103288场景，与旧轨迹、评分、有效token精确一致。工程错误版本和一次性工程权重已隔离，没有继承为正式学生。全参VLM、冻结视觉、仅投影、难例曝光及训练重复尚未纳入本首轮，不能写成已完成。尚未进行策略连续观测并重新决策的闭环验证。</p></details>')
    style='body{max-width:1200px;margin:32px auto;padding:0 22px;font:16px/1.7 system-ui,sans-serif;color:#202936;background:#fff}h1{font-size:29px}h2{margin-top:32px;font-size:22px}.meta{color:#64748b;font-size:14px}.finding{padding:18px;background:#eef4fc;border-left:4px solid #426ca0}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px;margin:16px 0}th,td{text-align:center;padding:9px 11px;border-bottom:1px solid #dce1e8;white-space:nowrap}th{background:#f1f4f8}.left{text-align:left}details{margin:24px 0;padding:16px;background:#f7f9fc}summary{cursor:pointer;font-weight:600}code{font-size:12px;overflow-wrap:anywhere}li{margin:7px 0}'
    html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>首版42候选教师蒸馏实验</title><style>'+style+'</style><body>'+''.join(body)+'</body></html>'
    target=ROOT.parent/'doc/work-output/1021-representation_distillation_batch4/representation_distillation.html'
    assert target.is_relative_to(ROOT.parent/'doc/work-output');target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp');temporary.write_text(html);temporary.replace(target)
    proof=dict(status='GENERATED_REPORT_REQUIRES_FINAL_AGENT_REVIEW',time=stamp(),report=str(target.relative_to(ROOT.parent)),report_sha256=sha(target),
        comparison_sha256=sha(comparison_path),source_sha256=sha(Path(__file__)),formal_results_only=True,
        scientific_plot=dict(path=str(chart.relative_to(ROOT)),sha256=sha(chart)))
    atomic(ROOT/'provenance/REPORT_GENERATION_V1.json',proof);print(json.dumps(proof,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
