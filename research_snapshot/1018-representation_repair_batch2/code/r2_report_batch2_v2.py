"""Coherent Chinese scientific report; final status requires frozen evidence.

Reads scored summaries only. Never runs a model, changes selection or accesses
validation/test assets. Draft and final builds both retain source fingerprints.
"""
from r2_common import *
from r2_report_batch2 import esc,table
import argparse
import base64


def number(v):return format(v,'+.4f')
def sequence(values):return ' / '.join(number(v) for v in values)


def build(output):
    sources=[]
    def source(rel,optional=False):
        p=ROOT/rel
        if optional and not p.exists():return None
        x=read(p);sources.append(dict(path=rel,sha256=sha(p)));return x
    def pointer(rel,optional=False):
        x=source(rel,optional)
        if x is None:return None
        assert sha(ROOT/x['path'])==x['sha256'];return source(x['path'])
    def detail(title,body):return '<details><summary>'+esc(title)+'</summary>'+body+'</details>'
    def evidence(title,value):return detail(title,'<pre>'+esc(json.dumps(value,ensure_ascii=False,indent=2))+'</pre>')
    cv=pointer('analysis/extended_cv_reviews/LATEST.json');rep=pointer('analysis/repetition_cv_reviews/LATEST.json');coverage=source('analysis/variant_wave_coverage_flags/LIVE.json');cloud=source('resources/CLOUD_LATEST.json')
    correction=source('analysis/correction_diagnostics/SUMMARY.json');control=pointer('analysis/space_control_summary/LATEST.json');capacity=source('analysis/expert_capacity_control/SUMMARY.json');transfer=source('analysis/expert_capacity_control/FIXED_CANDIDATE_TRANSFER.json')
    observable=source('analysis/expert_capacity_observable/SUMMARY.json',True);acceptance=source('provenance/FINAL_SCIENTIFIC_ACCEPTANCE.json',True)
    feedback=pointer('analysis/expert_feedback_distribution/LATEST.json',True)
    duplicate=source('analysis/variant_wave_coverage_flags/BCS_CORRECTION_K2_SOURCE_AND_OUTCOME_IDENTITY.json',True)
    formal=bool(acceptance and acceptance.get('status')=='PASS' and acceptance.get('locked_validation_complete') and acceptance.get('locked_test_complete'))
    figures=pointer('analysis/report_figures_v2/LATEST.json',True)
    def figure(name):
        if figures is None:return ''
        f=next((f for f in figures['figures'] if f['name']==name),None)
        if f is None:return ''
        p=ROOT/f['png'];sources.append(dict(path=f['png'],sha256=sha(p)));data=base64.b64encode(p.read_bytes()).decode()
        return '<figure><img alt="'+esc(name)+'" src="data:image/png;base64,'+data+'"><figcaption>'+esc(f['caption'])+' 图数据快照 UTC '+esc(figures['time'])+'。</figcaption></figure>'
    full=[r for r in cv['recipes'] if r['complete_five_folds']]
    repeated=[r for r in rep['recipes'] if r['all_three_fits_complete']]
    stable=[r for r in repeated if r['descriptive_threefit_positive_and_approx_safe']]
    sections=['<h1>表征修复第二批实验：专家化能否兑现可控性</h1>',
        '<p class="status">'+('正式验收报告' if formal else '进行中的证据快照：预定宽扫及正式自然确认／测试尚未全部完成')+' · 构建时间 UTC '+esc(stamp())+'</p>']
    sections+=['<p>本批冻结同一个RL Base，让不同失败形成自己的修复位置、子空间、算子与力度，比较硬选择、真正联合软干预和独立轨迹候选选择。每个系统含K=2–8个非零专家及严格恒等的零专家。主要修复VLM／接口，复用第一批动作头结果作参考。</p>']
    sections+=['<h2>目前能回答什么</h2>',table(['问题','证据与判断'],[
        ['内部状态是否有可控自由度','有。GT代理逐场景受限优化可大量改善失败，并能固定扰动迁移至其他采样。它含特权信息，不能作为部署成绩。'],
        ['少量专家是否形成有用候选','部分候选有真实且互补的特权收益；本策略自身K个专家＋Base的Oracle与可观察路由必须分开。'],
        ['是否已经找到稳定整体提分的修复','当前完整三拟合配方 '+str(len(repeated))+' 个，其中三拟合×三噪声均正且满足探索近似安全约束的为 '+str(len(stable))+' 个；正式结论还需冻结自然确认和测试。'],
        ['此前最好的K=3信号是否复现','初始联合软修复的正收益未在另外两次独立完整拟合中复现。不能挑最优种子，也不能用跨拟合均值冒充新模型。'],
        ['负结果能否否定全部表征修复','不能。它约束已测位置、状态参数化、候选、训练信号和搜索预算；强特权可控性与弱部署泛化可以同时成立。']
    ],long=(0,1))]
    sections+=['<h2>数据、定义与独立性</h2>',
        '<p>navtrain共103,288场景，按会话分为85,813探索场景和17,475自然留出场景；探索含1,850个S0失败和74,900个高质量输出。失败定义为未舍入PDMS&lt;70，高质量为&gt;90，70与90归中间质量。完整会话交叉验证中，分组、空间、专家、路由和内部校准均排除该外层留出会话。</p>',
        '<p>开发使用配对S0/S1/S2，最终测试计划使用S0–S4。场景种子由SHA256(token|20261008|j)前8位生成，与节点、rank和恢复顺序无关。三采样属于同一场景，会话用于聚类不确定性。不同拟合随机流改变分组、专家与路由；三份读出续训的集成不能替代三次完整拟合。</p>',
        '<p>VLM的同一观测在动作采样前表征相同，因此本批上游比较来自跨场景自然输出质量分布，不构造伪造的同输入成功／失败差分。GT只参与训练代理和明确标记的诊断，部署路由不读取GT或真实PDMS。</p>']
    sections+=['<h2>实际探索了哪些方法</h2>',table(['部分','本批比较','证据范围'],[
        ['自然形成专家','表征残差、实际干预响应、有效扰动三种初始化；K=2至8各自重新分组／拟合','先按子群重估空间，再按真实完整轨迹反馈更新；不按人工失败标签强制分组。'],
        ['专家形式','组内解析平移／抑制／运输、行为目标低秩修正、有效扰动条件回归、反馈重估、异质库','每位专家有自己的位置／空间／算子／力度，不只改变共享方向的系数。'],
        ['部署决策','固定硬策略、硬选择＋连续力度、真正联合软混合、独立候选收益／风险选择','包含零专家，软混合实际共同前向和评分；不将单专家收益线性相加。'],
        ['信息与目标','观测、Base完整轨迹、动作生成状态；完整token与匹配均匀读出；实际有限动作收益','增加推理成本不作为主要淘汰标准；所有可观察信息层级仍须泛化验证。'],
        ['根因对照','扩大成功反馈、匹配训练预算、状态／零token、读出续训集成、质量／随机／受限全维控制','部分为有界单折诊断，不能写成所有系统的五折／三拟合对照。'],
        ['容量与收敛','专家rank32/128/256，原／4／8倍训练；五库×22种可观察路由匹配初筛','共18个新专家模型，原rank32预算前缀与旧权重逐数组精确复现；可观察初筛共享固定分组。']
    ],long=(0,1,2)),
        '<p>质量空间保留共同中心化与未中心化、等维与非等维主空间、不同残差秩；实际有效秩及分层粗筛决定可运行配置。候选范围不等于每个K／子群均运行完整笛卡尔积。后续按实际候选清单报告，不能声称穷尽所有4096维组合。</p>',
        detail('全部协议文件及指纹',table(['协议','SHA256'],[(p.name,sha(p)) for p in sorted((ROOT/'config').glob('*PROTOCOL*.json'))],long=(0,1)))]
    sections+=['<h2>专家化的完整会话外表现</h2>',
        '<p>当前完整五折配方 '+str(len(full))+' 个，部分折配方 '+str(cv['partial_recipes'])+' 个。结果是失败富集面板的类别标准化、会话平衡开发估计；不等于完整自然总体成绩。探索中的最大值经多次选择，不能独立充当可复现收益。</p>',figure('breadth_by_route')]
    if 1/(cv['bootstrap_samples']+1)>.05/max(len(full),1):
        sections+=['<p class="status">实时快照的符号重采样精度限制：'+str(cv['bootstrap_samples'])+'次重采样的最小p值高于当前Holm首项阈值，因而旧表中的“未显著”不能作为额外负证据。最终冻结全家族另按高精度协议重算；跨拟合符号、安全和效应量证据不受这一数值分辨率问题影响。</p>']
    def cvtable(rows):return table(['系统','方法／角色／信息','PDMS变化','S0 / S1 / S2','95%会话区间','探索安全','Holm p'],[(r['system'],r['method']+' / '+r['policy'],number(r['standardized_pdms_gain']),sequence(r['standardized_pdms_gain_by_noise']),sequence(r['session_bootstrap_95']),'通过' if r['approximate_safety_all_noise'] else '未通过',format(r['holm_p'],'.4g')) for r in rows],long=(0,1))
    selected=[r for r in repeated if r['system_stem']=='correction_K3' and r['method'] in ['joint_soft_joint','joint_hard_continuous'] and r['policy'] in ['safety_trajectory','safety_observation']]
    sections+=[figure('whole_fit_repetition'),table(['完整方法','三次拟合均值变化','每次拟合均正','全部噪声均正','全部拟合探索安全'],[(r['method']+' / '+r['policy'],sequence(r['fit_mean_gains']),r['every_included_fit_mean_positive'],r['every_included_fit_every_noise_positive'],r['every_included_fit_approx_safety']) for r in selected],long=(0,)),
        '<p>均值差异不能只归因于门控。完整拟合会改变分组、专家本身和路由，当前证据只说明早期方法收益对拟合不稳定；若要定位来源，需固定其他环节的匹配对照。</p>',
        detail('所有完整五折配方，包括零／负结果',cvtable(sorted(full,key=lambda r:(r['system'],r['method'],r['policy'])))),
        detail('全波次实际覆盖，未完成项不当作零收益',evidence('机械覆盖快照',coverage))]
    sections+=['<h2>特权修复与部署之间的距离</h2>',
        '<p>逐场景优化使用GT代理，允许真实S0评分在7个检查点／Base中选择。下表以失败为条件，不能与类别标准化总体变化直接比较。每个有效token共享同一个通道修正向量，不是每token各自任意改动。</p>',
        table(['配置','S0失败条件均分','修至>90','S1 / S2增益'],[(c['configuration'],format(c['selected_S0_pdms'],'.3f'),str(c['repair90'])+'/1850',sequence([c['gains_S1'],c['gains_S2']])) for c in correction['configurations']],long=(0,)),
        '<p>受限全维有效说明这些接口在该参数化与预算下可控；它没有证明可观察状态足以预测场景最优修正，更没有把逐场景GT目标变成通用修复器。</p>',figure('quality_random_full_control'),
        '<p>同预算24场景／20会话的质量、随机、通道全维控制中，质量空间未表现出可靠的普遍优势；144组质量—随机迁移比较经Holm校正没有正／负方向显著项。它只覆盖固定主空间切片、若干残差秩及通道共享扰动。统计上的质量差异与行为上的控制效率是不同问题。</p>',figure('capacity_and_fixed_choice'),
        '<p>容量诊断在同一correction-K3、探索fold0的1,135场景／23会话上评估。更高rank或更长训练有时提高逐输出Oracle，但强制非零专家仍可能造成更大整体损伤。S0固定具体选择迁移后，部分延长训练优势反转；不能用每噪声重新选最优的结果声称固定修复跨噪声成立。</p>']
    if observable:
        sections+=[evidence('五库×22可观察路由匹配初筛：完整结果与统计',observable),'<p>这项初筛固定同一原始分组与单个探索折，不是五套独立分组，也不是完整自然确认；所有方法对Base及同方法rank32参照均进入预设比较家族。是否扩展按实际收益、风险、邻近设置和跨噪声表现判断。</p>']
    else:sections+=['<p class="status">五库×22种可观察路由初筛仍在执行；本快照不对尚未完成的结果作结论。</p>']
    sections+=['<h2>怎样解释目前的困难</h2>',table(['可能瓶颈','现有证据','仍不能推出'],[
        ['统计空间与控制空间不一致','局部受限优化很强，质量空间在匹配预算控制中未稳定胜过随机空间。','不能推出所有质量表征都无用，或任意行为敏感空间都有效。'],
        ['可控修正难以跨场景共享','逐场景特权优化很强，但专家及联合路由的会话外整体收益弱或不稳定。','不能只凭向量／梯度夹角证明失败需求存在功能冲突。'],
        ['选择／拒绝与安全代价','自有专家Oracle明显优于可观察路由；成功损伤抵消部分修复。','Oracle也使用不可部署的信息，差距不等价于只要完美识别失败就能兑现全部收益。'],
        ['训练目标与真实评分不一致','代理行为目标、有限实际收益标签及不同信息读出均作了比较，收益仍需真实评分复核。','负结果不证明条件信息不存在，也不证明更长训练必然能解决。'],
        ['拟合和采样状态兼容性','K3早期收益跨完整拟合翻转；固定S0选择的噪声迁移弱于逐输出Oracle。','不能将三次采样当三个独立场景，不能把一份最佳拟合称稳定能力修复。']
    ],long=(0,1,2))]
    if feedback:
        rows=[]
        for system in ['representation_K2_seed0','correction_K3_seed0','correction_causal_K2_seed0','correction_spatial_K2_seed0']:
            gains=[];costs=[]
            for dataset in ['fitting_pool_S0','outer_held_S0S1S2']:
                own=[r for r in feedback['own_K_Oracle_summaries'] if r['system']==system and r['role']=='PDMS' and r['dataset']==dataset and r['quality_class']=='S0_failure' and r['seed_index']==0 and r['complete_fivefold']]
                gains.append(own[0]['mean_PDMS_gain'] if len(own)==1 else None)
                high=[r for r in feedback['records'] if r['system']==system and r['role']=='PDMS' and r['dataset']==dataset and r['quality_class']=='S0_high' and r['seed_index']==0 and r['expert']!='own_K_Oracle']
                if {r['heldout_fold'] for r in high}==set(range(5)):
                    mass=sum(r['cases'] for r in high);costs.append(sum(r['mean_PDMS_gain']*r['cases'] for r in high)/mass)
                else:costs.append(None)
            if all(x is not None for x in gains+costs):rows.append((system,sequence(gains),sequence(costs)))
        sections+=['<h3>训练反馈和留出反馈是否不同</h3>',table(['专家库（PDMS参数）','失败条件Oracle：训练池 / 留出','原高质量强制随机单专家：训练池 / 留出'],rows,long=(0,)),
            '<p>表中为S0、完整五折的条件PDMS变化，不能与自然总体提分混用。训练失败共7,400个跨折视图，来自1,850个场景在四个外层训练折中重复出现；留出失败为1,850个场景。训练池不保证每一行都实际参与梯度更新。高质量列是均匀随机选择一个非零专家的期望，分别来自真实完整轨迹；没有混合轨迹或hidden。</p>',
            '<p>不能笼统说所有专家都只记住训练样本：行为目标库的失败条件Oracle相近，有效扰动回归库则下降明显。后者的训练侧选参偏好未必能在新会话保持，但不同场景／数据量也会造成差异，这个描述性对照不能单独证明过拟合的因果作用。路由内部校准排除打分器拟合样本，不代表这些场景也被排除于专家拟合；真正的专家反馈交叉拟合控制尚未完成。</p>',
            detail('全部已有反馈对照与实际覆盖（含缺失及部分折）',evidence('逐专家／类别／噪声描述性统计',feedback))]
    if duplicate:
        sections+=['<h3>异质候选库不保证最终使用异质专家</h3>',
            '<p>correction-unified-bcs K2在五折及全探索版、两种角色中，最终均选择了相同的两个有效扰动回归专家。它的候选池包含多个算子族，最终bank没有形成算子族混用。'+str(duplicate['identical_policy_count'])+'/22个核心配方在全部五折上的实际轨迹和评分与原因果别名库完全相同；硬策略与候选打分器的随机流还依赖system别名，因此其余策略不能假定相同。该结果不能重复算成一组独立专家能力证据，也不能外推到其他异质配置。</p>',
            evidence('已验证来源、实际矩阵和重复策略',duplicate)]
    sections+=['<h2>安全、强度与特权口径</h2>',
        '<p>安全优先约束为净碰撞、净出界、净零分不增加；TTC和总失败另报，不自动升级为新硬约束。净不增加不意味着没有新增损伤，新增与消除须分列。PDMS优先候选即使违约也可作为明确标记的诊断，不能称安全达标。</p>',
        '<p>独立专家本身范数上限与联合路由的最终半径分开：专家上限0.1乘已选力度；联合amount可至2，半径按非零专家权重×amount×实际修正量求和，同位置最坏归一化半径可至0.2。多位置按实际执行顺序分别报告。零专家权重保留，不丢弃后重归一化；范数小也不替代真实安全评价。</p>',
        '<p>完美失败触发、仅有益才替换、自有K专家＋Base逐输出Oracle、固定场景专家及逐场景GT优化是不同特权诊断。物理上共享候选计算不允许把不同K／角色／库的候选并起来冒充一个可部署系统。</p>']
    sections+=['<h2>自然确认与最终测试</h2>']
    if formal:sections+=[evidence('冻结方案、自然确认、测试与验收',acceptance)]
    else:sections+=['<p>尚未完成正式冻结自然确认与最终测试。本页只读取探索期已评分产出；未通过探索稳定性筛选不等于已经在独立测试证明无效。后续在全部预定广筛及入围拟合重复完成后冻结安全／PDMS两组方案，完整自然留出确认，再锁定最终测试；不根据测试结果重选或改阈值。</p>']
    sections+=['<h2>计算与复核边界</h2>',
        '<p>已接入6个DLC节点、每节点16张PPU-ZW810E，共96张物理卡；另24条流水与既有设备共享，不是额外24张卡。CPU统计、拟合、推理、评分按依赖弹性供给，冻结代码和结果保留，节点不自动释放。共享读取／缓存／合批只在真实轨迹、种子、评分与决策等价验收后接入未来任务。合批投影中的seconds=0仅指投影成本，物理推理耗时在源产出计一次。</p>',
        detail('资源实时快照与72小时时限',evidence('云端状态',cloud)),
        '<p>当前尚未形成可信开放环整体净收益，因此没有声称完成闭环能力修复。历史测试集预实验只作为方法参考，本批数据、实现、配置、搜索过程及最终确认边界独立记录。</p>']
    used=list(sources);sections+=[detail('本报告实际读取来源与SHA256',table(['路径','SHA256'],[(p['path'],p['sha256']) for p in used],long=(0,1)))]
    css='body{font:16px/1.65 system-ui,sans-serif;color:#202c35;max-width:1180px;margin:32px auto;padding:0 22px;background:#fff}h1{font-size:28px}h2{font-size:22px;margin-top:32px}.status{padding:12px;background:#fff4da;color:#6b4e17}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:8px;border-bottom:1px solid #dce3e8;text-align:center;overflow-wrap:anywhere}th{background:#edf2f5}.long{text-align:left}.scroll{overflow:auto}details{margin:14px 0;border:1px solid #dce3e8;padding:10px}summary{cursor:pointer}pre{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}figure{margin:22px 0}figure img{width:100%;height:auto}figcaption{font-size:13px;color:#52616c;margin-top:7px}'
    page='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>表征修复第二批实验</title><style>'+css+'</style></head><body>'+''.join(sections)+'</body></html>'
    output=Path(output);assert output.is_relative_to(ROOT) or output.is_relative_to(ROOT.parent/'doc/work-output/1018-representation_repair_batch2')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(page)
    proof=ROOT/'provenance/report_builds'/('scientific_v2_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json')
    atomic(proof,dict(time=stamp(),report=str(output),report_sha256=sha(output),formal=formal,sources=used,validation_or_test_assets_opened=False,unfinished_is_explicitly_marked=True))
    print(json.dumps(dict(report=str(output),formal=formal,source_count=len(used),full_cv=len(full))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);main_args=p.parse_args();build(main_args.output)
