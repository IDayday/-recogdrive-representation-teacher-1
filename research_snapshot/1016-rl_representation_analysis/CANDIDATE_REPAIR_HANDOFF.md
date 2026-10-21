# 扩展候选修复测试接续（2026-10-16）

## 当前入口（覆盖下文历史准备项）

- **最终重计算当前入口**：主pipeline53138已正常exit0；开发验收PASS，10阶段39346块/8587650输出。FINAL_TEST_LOCK在2026-10-16T18:48:59Z冻结14干预arms+Base、8对比，含route1末步test-only补充4null。FINAL_TEST_SMOKE通过，navtrain_full_locked103288×3×(2+Base)=929592输出、final_test12146×5×(14+Base)=910950输出已入队。活跃前台最终completion **9678**，简明机械监控 **58280**；旧68837已结束。完整训练排在test之前，两节点32卡连续计算。开发验收后不要改选择、fit、runtime。测试后需要SCIENCE_READY→报告图形验收→资源终端验收→文档收尾。

- **验证后锁定状态**：validation/validation_temporal/validation_combinations全部完成；按预设规则锁两独立候选：route1 cr_774b7ee8eef1ab62，route2及global cr_ece3a3e1d5b3268a，各自安全/PDMS角色重合。当前validation_controls16配置正在32卡计算。最终final.py已在测试前读取MATCHED_CONTROL_SUPPLEMENT：为route1末步额外4个仅测试null（reverse+3Haar），最终应14arms+Base，3.1e5全训练pair只跑2锁候选。次要random家族比较每个独立父方法，避免global双角色重复；见新补充协议。代码修改均aux、原runtime不变。

- 当前run：`candidate_repair_20261016_v1`。新作业：`dlcmi53bf3ah2c2s`、`dlcms4op7agqj50d`，各16卡、32卡真实冒烟通过。截止按创建时刻保守计 **2026-10-17 03:42:10 UTC**，720min/Reserved0。全部重计算结束前保留；不要未经用户新指令主动关闭/释放，完成时报告现场状态与剩余时限，不承诺无限保留。
- **2个活跃前台等待终端**：主pipeline **53138**（candidate_repair_pipeline_v1.log），最终completion **9678**（candidate_repair_completion_v2.log）；时间对照 **17039** 已正常完成，其日志candidate_repair_temporal_v1.log保留。均在provenance/。保持工具等待直到计算/验收结束，不能仅后台写状态就结束对话。
- `MONITOR.json`是实时机械进度；2个监控器会写同一最新指针，完整时间线在各自log。原始异常在run/failures及node*/FAILED。当前无失败。
- 已完成：coarse3650×(580+Base)=2120650输出；quality_screen80配置完成；17,475×3 Base逐分项精确复现前轮，BASELINE_REPRODUCTION PASS；128例×16方向传播诊断SENSITIVITY PASS。replay186配置×9850和temporal_screen144配置均已完整完成。当前普通validation21配置×17475×3正在计算，6组合screen及16时间配置完整验证已排队。validation全部32rank保存结果抽查PASS（stage_audits/validation.json）。新空间来源仍10候选，没有再扩大SVD维数网格。
- 已拟合76个npz（20初始、30匹配Haar、14连续PDMS、12时间校准），所有原npz与模型runtime源保持冻结。运行代码是candidate_repair_engine/queue/fit/launch等，见execution SHA；辅助选择/验收/报告代码有明确探索期补充协议，修正前保留版本/理由。
- 自动链路：主pipeline完成replay→普通validation+6组合screen→组合完整validation；temporal终端完成时间screen→时间验证代表+原步对照→validation_temporal。finalists会等三套完整验证再统一锁最多6角色，之后原位置主候选与全局父方法做匹配null控制，不看测试重选。
- completion自动开发验收→FINAL_TEST_LOCK→训练/真实test-cache冒烟→锁定全训练103288×3诊断+navtest12146×5第二轮复评→600原入口重评分→最终验收→SCIENCE_READY。测试集前轮已用，本轮如实叫第二轮锁定复评；全训练是拟合总体诊断，不是独立泛化。
- `SCIENCE_READY`之后仍要主智能体运行 `candidate_repair_report.py --version final_v1`，查看4张新PNG，再 `candidate_repair_report_accept.py --figures-reviewed`；使用新的版本目录修正图/报告，保留旧版本。最后更新PLAN/STATUS/导航并核查节点时限。正式报告同一canonical HTML，原15图保持，新增4图，总计19嵌入PNG，未做浏览器渲染。
- 阶段观察：初始训练广筛领先为R2两个2维残差+自然校准；最高加权约+.04694 PDMS，部分增碰撞。R2-12自然contract约+.03025，修复48/1850至>90、1200高质量中0转失败，净NC−3/DAC−5/zero−8；这些都不是留出结论。R1原位置收益约+.0006级。不要预设后续验证或测试收益。
- 传播：R1-0隐表征实际改约4%，更新差中位从.00204(t40)到.0000149(t0)，最终约.27mm；R2-9最终位移中位3.37mm，小r2维候选约7–9cm。时间144配置是基于这批探索诊断适配，在新验证前冻结，同一B不重采集；alpha1e6只令实际编辑饱和到cap=.01/.05，总跨步相对L2仍受限。

以下是历史准备及推进记录，未完成项以本节和最新JSON为准。

用户已批准10个确认区域充分修复测试，资源2×16卡，所有重计算完成前保持节点。旧两个节点已释放，本轮是全新的DLC作业：node0 dlcmi53bf3ah2c2s，node1 dlcms4op7agqj50d，创建2026-10-16 15:42:10 UTC，上限720分钟，Reserved0，保守截止2026-10-17 03:42:10 UTC。

- 新run `candidate_repair_20261016_v1`，新工作子目录 `candidate_repair_v1/`。旧代码/配置/结果全部保留。正式报告最终仍更新同一HTML。
- 当前前台pipeline终端session **53138**，日志 `provenance/candidate_repair_pipeline_v1.log`。每分钟监控云状态/剩余时间/任务receipt/原始异常。不要结束对话仅留下后台任务；使用工具等待并继续验收。
- 工程和拟合已经完成。20套拟合（10候选+主候选各等维/全维/3随机）、30个配对随机旋转基。583组真实方法（580广筛+3匹配Haar）×3锚点、spawn评分及63原入口重评分通过；最后参考 `runs/candidate_repair_dsw_v4/smoke/rank000.json`。工程证据 `candidate_repair_v1/ENGINEERING_PASS_v2.json`。
- 新代码 `candidate_repair_engine.py/queue.py/fit.py/launch.sh` 等已冻结在 `configs/candidate_repair_execution_v1.json`，不能直接修改运行版本。队列沿用UUID临时文件/mkdir领取，无跨容器PID临时名冲突。原节点主协调器/16卡模型worker保持open。
- 广筛3650探索场景（1850失败/1200高质量/600中间）×580 arms +Base；1825块，每块2场景。之后已有6555块validation_baseline排队，可在DSW选参时维持有用计算。初始总8380块。
- methods均值/质量方向回退/收缩/OT；路线二另有linear/MLP/local和自然高质量identity replay；路线二对照p配对统计与n自然校准。alpha .1/.5/1，cap .01/.05/.1，风险门控用自然成功分位。所有拟合仅探索集、GT/PDMS不作推理输入。
- 原空间重建与冻结读出cos>1−1e−6；自然坐标已保存用于收益门控。最初DSW发现原始h视图被结果更新影响范数分母，已在冻结前clone修复；失败v1/v2记录及源码保留，不涉及正式云结果。
- FOLLOWUP_RULE.json已在广筛完成前记录后续选择代码SHA。新辅助分析/流程脚本如需修正应保留旧版本和原因；不要改冻结runtime。

## pipeline自动推进的范围

1. coarse完成：new `candidate_repair_analysis.summarize/safety`（写本轮analysis，不写旧repair_v1）。按每区域PDMS/保守/不同机制，以及全局每机制保留parent；仅gate=none父方法拟合探索收益门控。追加replay：9850探索场景，原父+自然risk95/99/995+benefit0/.001。每阶段新方法均先DSW `candidate_repair_probe.py` 全3锚点真推理/评分后append。
2. replay完成：每区域安全/PDMS及每机制代表进入17475留出×3种子validation，附旧安全/PDMS两个方法和scale1.005/1.02对照。探索选3对不同位置组合×强度.5/1，L2预算.05，追加combination_screen。
3. 组合screen完成：6组合和对应同预算单点全部送3种子完整验证，不只挑最高点。
4. 两个validation完成：冻结BEHAVIOR_SELECTION_LOCK，路线一/二/全局各安全和PDMS最多6个不同修复候选。安全为净碰撞/出界/零分不增且PDMS不降，TTC和总失败另报。然后全局两父方法匹配reverse及3 Haar旋转（相同位置/强度/门控/预cap范数）完整验证；不改变已锁候选。
5. validation_controls完成：pipeline写DEVELOPMENT_READY后返回，**尚未追加最终测试**，需要主智能体接续。

## pipeline之后必须完成

- 汇总全部开发与对照验收、基线矩阵一致性和规则/源码SHA；冻结最多6角色+旧方法/匹配对照等最终复评清单与推断家族，再追加 `final_test`。复用旧 `runs/repair_final_test_20261016_v1/stages/final_test/panel.json` 的12146严格已验证输入；本轮用5种子新运行Base+新候选。queue原生支持navtest和原cache adapter，无需换程序或新节点。
- 此前navtest已被前轮使用；本轮如实叫“锁定后的第二轮复评”，不得宣称全新未接触测试。不能据本轮测试结果调参。仍以训练/会话验证选参。
- 新 `candidate_repair_final.py/stats/accept/report` 尚未编写。应先冻结主比较候选vsBase（Holm）、次比较vs旧方法/匹配随机；会话bootstrap，跨seed按同token聚类，稳定失败/稳定成功分层，所有安全项/修复与损伤。
- 测试完整覆盖、FreshBase与旧同配置五种子Base精确比对；600条分层保存轨迹经独立原入口重新评分。所有任务receipt/resultSHA、shape/seed/input/score检查，不仅看进程/卡利用率。
- 按用户要求前台等待完整重计算/验收；最后更新正式报告、PLAN、STATUS、接续。完成所有重负载前不得释放两新节点；结束时按最新用户指令处理资源，留意12小时总上限。


## 当前补充（覆盖上述“尚未编写”清单）

- 两节点32卡已实际SMOKE_PASS；FIVE_MINUTE_NODE0/1各核查37184记录、64场景，全部rank/580配置/输入/种子/预算/评分通过。当前coarse约持续50–60块/分钟，无失败。
- 最终链路代码已经写好：candidate_repair_final.py、statistics.py、accept.py、completion.py、report.py。全部语法检查通过，FINAL_EVALUATION_PROTOCOL_SOURCE保存预先源码SHA；没有重跑原模型采集。
- 当前主pipeline session **53138**；completion已仅重启DSW等待包装器为session **9678**，日志candidate_repair_completion_v2.log（旧85552仅等待时SIGTERM退出，无云进程影响）。完成DEV后它会自动开发验收→锁定测试→真实test-cache冒烟→追加锁定全量训练103288×3及12146×5测试→等待两者→统计→600原入口重评分→最终验收→SCIENCE_READY。
- 全训练覆盖是新增的预先诊断协议LOCKED_FULL_TRAIN_PROTOCOL，不能据结果改选择，也不能冒充独立验证。最终accept会比对完整训练中的验证子集Base与独立validation_baseline，以及前轮三种子Base。
- 主候选完整匹配控制除reverse/3Haar外，另有等维/全维类别均值差方向，保留父方法动态编辑范数和门控；这是匹配方向对照，不是替代空间整套OT/MLP重训的纯维度消融。组合因前点编辑会改变后点输入，只匹配门控规则和预算，不能宣称每点实际激活/范数和父组合逐输出完全相同。
- 等completion SCIENCE_READY后主智能体仍须运行candidate_repair_report.py --version final_v1，检查PNG视觉/HTML/数字/证据、更新报告与PLAN/STATUS。若生成或图形需修正，用新版本目录，保留旧图/报告；旧科学结果不覆盖。最终根据用户最新指令处理资源；重负载未完成前不要关闭/释放。

补充：连续自然PDMS梯度quality_screen80配置已在广筛汇总前冻结（QUALITY_PROTOCOL）；拟合/DSW probe/append进程session63088，日志candidate_repair_quality_v1.log。replay子进程先wait quality_screen，再合并coarse和quality_screen选父方法。新q拟合通过原mean算子调用，不改冻结engine/queue；主候选q对应的等维/全维q拟合也已准备。后续验收包含该stage，所有测试选择仍在验证上锁定。

传播诊断SENSITIVITY已PASS：128例×16配置、原10配置逐轨迹与coarse精确一致。R1主候选更新差中位从.00204到.0000149（最终约.27mm）；并非隐藏编辑没有施加。新增144时间控制原步/末步/持续，共用原4候选投影B，session **17039**，日志candidate_repair_temporal_v1.log；它自动拟合12目标步校准、DSW probe、append temporal_screen，再等待并选validation_temporal。主finalists现在等待validation_temporal，合并三套验证；原runtime不改。Temporal_PROJ、source s动态方向的等维/full控制仅限canonical pnq，防止错误地把不同时间/校准当纯维数消融。报告代码已纳入时间验证与128例传播诊断。
