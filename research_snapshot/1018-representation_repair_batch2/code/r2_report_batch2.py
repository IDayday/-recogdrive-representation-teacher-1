"""Evidence-driven Chinese batch-two HTML; no model, selection or cloud actions.

An unfinished report is explicitly marked interim. Formal status requires the
final acceptance marker and completed locked validation and test summaries.
"""
from r2_common import *
import argparse
import html


def esc(x):return html.escape(str(x))


def table(headers,rows,long=()):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th class="'+('long' if j in long else '')+'">'+esc(v)+'</th>' for j,v in enumerate(headers))+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td class="'+('long' if j in long else '')+'">'+esc(v)+'</td>' for j,v in enumerate(row))+'</tr>' for row in rows)+'</tbody></table></div>'


def bars(values,title):
    width=760;left=245;right=40;row=32;scale=(width-left-right)/100
    lines=['<svg viewBox="0 0 '+str(width)+' '+str(45+row*len(values))+'" role="img" aria-label="'+esc(title)+'"><title>'+esc(title)+'</title>']
    for j,(label,value) in enumerate(values):
        y=20+j*row;lines+=['<text x="235" y="'+str(y+15)+'" text-anchor="end">'+esc(label)+'</text>','<rect x="245" y="'+str(y)+'" width="'+str(max(0,value)*scale)+'" height="22" fill="#346c9d"/>','<text x="'+str(253+max(0,value)*scale)+'" y="'+str(y+15)+'">'+format(value,'.2f')+'</text>']
    return ''.join(lines)+'</svg>'


def build(output):
    used=[]
    def source(path):
        p=ROOT/path
        if not p.exists():return None
        d=read(p);used.append(dict(path=path,sha256=sha(p)));return d
    def detail(title,value):return '<details><summary>'+esc(title)+'</summary><pre>'+esc(json.dumps(value,ensure_ascii=False,indent=2))+'</pre></details>'
    status=source('STATUS.json');cloud=source('resources/CLOUD_LATEST.json');correction=source('analysis/correction_diagnostics/SUMMARY.json');latest=source('analysis/extended_cv_reviews/LATEST.json');cv=source(latest['path']) if latest else None
    acceptance=source('provenance/FINAL_SCIENTIFIC_ACCEPTANCE.json');formal=bool(acceptance and acceptance.get('status')=='PASS' and acceptance.get('locked_validation_complete') and acceptance.get('locked_test_complete'))
    sections=['<h1>自然形成的多样化表征修复专家：第二批实验</h1><p class="note">'+('正式验收报告' if formal else '阶段性快照：计算与确认尚未完成，不能据此宣称稳定提分或最终否定该方向。')+' · UTC '+esc(stamp())+'</p>']
    sections+=['<p>冻结RL Base，比较不同失败能否形成自己的位置、子空间、算子和力度，并以部署可得信息选择干预。零专家为严格恒等；非零专家K=2至8。分别报告安全优先与PDMS优先。失败为PDMS&lt;70，高质量为PDMS&gt;90，等号归入中间质量。</p>']
    sections+=['<h2>证据回答什么</h2>'+table(['问题','当前判据'],[['能不能改变失败行为','逐场景优化与专家完整轨迹重新评分；特权选择单列。'],['能不能将局部能力组织成专家','完整系统会话交叉验证；分组、空间和模型均在训练折拟合。'],['能不能可靠触发和选择','硬路由、真正联合软干预、完整候选选择；预测收益与原能力损伤并报。'],['能不能泛化','冻结后的自然留出与最终测试，多个拟合初始化和采样噪声；不只报告最优点。']],long=(1,))]
    if correction:
        configs=correction['configurations'];sections+=['<h2>接口可控性：特权逐场景诊断</h2><p>1850个探索失败，单场景使用GT代理优化并用真实S0评分选择，保持同一扰动检验S1/S2。全维指每个有效token共享的通道向量，不是每token独立自由修改。下图是失败条件均分，不能与自然总体提分混用。</p>',bars([('原失败Base',configs[0]['base_pdms'])]+[(c['configuration'],c['selected_S0_pdms']) for c in configs],'逐场景受限优化的失败条件PDMS'),table(['位置/相对范数上限','S0均分','修至>90','S1增益','S2增益'],[(c['configuration'],format(c['selected_S0_pdms'],'.3f'),str(c['repair90'])+'/1850',format(c['gains_S1'],'.3f'),format(c['gains_S2'],'.3f')) for c in configs],long=(0,)),'<p>这些结果支持所测接口存在可控行为自由度；GT、逐场景搜索与真实评分选择属于特权信息，不能作为可部署修复成绩。</p>']
    sections+=['<h2>专家化与实际路由的会话外结果</h2>']
    if cv:
        full=[r for r in cv['recipes'] if r['complete_five_folds']];partial=len(cv['recipes'])-len(full)
        sections+=['<p>完整五折配方 '+str(len(full))+' 个；未齐五折配方 '+str(partial)+' 个。未完成项不与完整配方一起排名。富集面板按原质量类别标准化，仍需自然分布确认。</p>']
        if full:
            ordered=sorted(full,key=lambda x:x['standardized_pdms_gain'],reverse=True)
            sections+=[table(['系统','路由/角色','PDMS变化','S0/S1/S2','95%会话区间','安全约束'],[(r['system'],r['method']+' / '+r['policy'],format(r['standardized_pdms_gain'],'.4f'),' / '.join(format(v,'.4f') for v in r['standardized_pdms_gain_by_noise']),' / '.join(format(v,'.4f') for v in r['session_bootstrap_95']),r['approximate_safety_all_noise']) for r in ordered[:30]],long=(0,1)),detail('完整配方与负结果：完整搜索统计',cv)]
        else:sections+=['<p>目前尚无完整五折配方，不能把已完成的少数折当作整体泛化结论。</p>']
    sections+=['<h2>根因与匹配对照</h2><p>区分实际修复能力、路由信息与训练分布校准。已安排完整token读出对照、均匀读出对照、原/扩大成功数据且训练预算匹配、自车状态编码/同维零token、真实评分路由目标，以及同预算质量空间/随机空间/通道全维的逐场景控制。各项是否完成以对应验收与结果文件为准。</p>']
    for label,path in [('共享读取预测的实际科学流验收','provenance/CRITIC_SHARED_INPUT_REAL_STREAM_ACCEPTANCE.json'),('受控空间工程验收','provenance/SPACE_CONTROLLABILITY_ENGINEERING_PASS.json'),('同权重校准数据量对照','analysis/calibration_size_control/FIRST_POINT_DIAGNOSTIC.json')]:
        d=source(path)
        if d:sections+=[detail(label,d)]
    sections+=['<h2>自然分布确认与最终测试</h2>']
    if not formal:sections+=['<p>本快照未完成最终验收。自然验证、冻结测试、全部拟合重复及多重比较结论必须在最终证据中分别确认；本页不以运行存活替代科学完成。</p>']
    if acceptance:sections+=[detail('最终科学验收清单',acceptance)]
    sections+=['<h2>方法、范围与运行证据</h2><p>碰撞、出界、零分净不增加为安全优先约束；新增与消除分开统计，TTC与总失败另列。噪声保留在场景内，会话为重采样单位。所有冻结比较含负结果进入多重比较，不以单个最佳种子或单一p值判断稳定收益。</p>',detail('运行状态（可能包含未完成项）',status),detail('资源与72小时时限：未经授权不释放',cloud),detail('本页实际读取来源及SHA256',used)]
    css='body{font:16px/1.65 system-ui,sans-serif;color:#202b35;max-width:1150px;margin:32px auto;padding:0 20px;background:#fff}h1{font-size:27px}h2{font-size:21px;margin-top:30px}p{max-width:1050px}.note{color:#6d4d11;background:#fff5d8;padding:12px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:8px;border-bottom:1px solid #dce3e8;text-align:center}th{background:#edf2f5}.long{text-align:left}.scroll{overflow:auto}details{margin:14px 0;border:1px solid #dce3e8;padding:10px}summary{cursor:pointer}pre{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}svg{width:100%;max-width:900px;font:13px system-ui,sans-serif}'
    page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>表征修复第二批实验</title><style>'+css+'</style><body>'+''.join(sections)+'</body></html>'
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(page)
    proof=ROOT/'provenance/report_builds'/('report_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json');atomic(proof,dict(time=stamp(),report=str(output),report_sha256=sha(output),formal=formal,sources=used))
    print(json.dumps(dict(report=str(output),formal=formal,sources=len(used)),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();build(a.output)
