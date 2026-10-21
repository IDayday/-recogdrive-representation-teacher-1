# 表征修复执行接续（用户已批准，必须继续至计算验收）

当前任务：PLAN末节为用户认可的七类方法、对照、强度/维数、门控、三自然采样种子开发验证、冻结后独立测试。两条旧观察路线保持完成，不能把旧“只观察”当成本轮限制。

- DLC run `repair_20261016_v1`，node0 `dlc1kjeccruor0mn`、node1 `dlc1ktdxqj5472gz`，各16卡。实际32卡冒烟均PASS，与DSW轨迹/评分精确一致；两节点共享原子动态任务队列，正在广筛。
- 源码执行冻结：`configs/repair_execution_v1.json`。**不要改被冻结的runtime源文件**（repair_engine/queue/score/launch等）；若出现真正缺陷，以新版本与新执行身份修复，保留旧结果。新分析/监控文件不在执行hash内，可继续补全。
- 计划/方法协议 `repair_v1/PROTOCOL.json`；拟合均为exploration。配对空间P0拟合，另新增自然S0失败输入->同场景最终>90参考目标的local/linear/MLP，含8000真实自然成功/中间质量保持样本，716合格训练对；输入直接为原自然路径坐标。
- 初始阶段：screen 9850场景×140干预+Base，2463任务；natural_learn_screen 9850×36干预+Base，1232任务；validation_baseline 17475场景×S0/S1/S2，2187任务；reference_diagnostic 1850失败×18参考注入+Base，232任务。另在准备/追加sensitivity_screen(k4/16/32及强度/范数扫描，42干预)，见SENSITIVITY_FROZEN。
- 输出 `runs/repair_20261016_v1/results/*.json`，每任务receipt含hash。动态分配claims保留rank身份；node/status、workers和MONITOR追踪状态。root queue.json当前closed=false是为了追加后续验证，**全部任务入队后必须关闭，再等两云作业Succeeded和全部worker退出**。
- 前台等待监控 `code/repair_monitor.py --until screen,natural_learn_screen`，日志 `provenance/repair_monitor_screen.log`，工具session **55371**。每60秒云/文件轮询，5分钟语义抽查，达到两屏阶段完成返回唤醒智能体；此后基线/诊断/敏感性自动续跑，让CPU选参/拟合期间GPU有活干。不要仅后台挂着就结束本轮。
- `code/repair_analysis.py`已实现逐任务hash/全覆盖核对、矩阵/分种子修复损伤统计、按真实分布重加权训练广筛选择、训练集risk/benefit门控。接下来：分别summary screen和natural_learn_screen，再select（保留7机制及额外有价值候选，约10个基础配置，加门控/随机反向对照）。先做DSW新门控真实推理/评分冒烟，然后用repair_queue.stage追加完整validation三种子。控制器/统计可继续在DSW做，不占DLC GPU。
- 门控：hard阈值来自自然探索成功样本max-token风险的99.5%分位；benefit使用探索干预结果预测增益，输入只有当前natural低维h，不使用GT/PDMS作为推理输入。优先只对单layer/最后一步配置做门控。
- sensitivity_screen结束后summary，挑少数不同维数/力度候选补入相同validation三种子，禁止拿训练广筛当泛化结果。统一按会话聚合，种子不当独立场景。
- 独立navtest尚未读取任何轨迹/评分/特征。只通过资产索引/文件列表定位到`1010-il_baseline/features/navtest`，真正测试须开发选参冻结后另行准备。当前frozen worker只支持navtrain baseline_row，因此最终navtest需要一个新版本test worker/coordinator（保留当前代码和所有结果），按相同RL checkpoint、全新自然Base与修复同噪声对照；旧IL/旧RL成绩不能当本轮Base。
- 最终交付修复HTML报告、所有配置/轨迹/评分/统计和独立原始入口重评分。若无稳定净收益如实报告，不宣称修复成功；闭环仅对有净收益方法再安排，NAVSIM PDM评分不能叫真实闭环验证。

DSW小规模校验：ENGINEERING_PASS(137配置×3锚点)、EXTRA_ENGINEERING_PASS(软收缩+参考注入21配置×3)、NATURAL_ENGINEERING_PASS(自然输入修正36×3)，Identity与完整/缓存前缀采样精确一致，缓存评分反序及独立重评分一致，Base参数不变。唯一工程插曲：敏感性CPU拟合曾遗漏线程限制，已只中断确属任务的PID1551264，保留完成k4后用显式单线程续拟合，不涉及GPU作业或其他进程。

新增准备（09:56 UTC）：
- sensitivity_screen已追加1232任务(42配置)，budget_control已追加616任务(6配置，按active sites数量分摊cap、每action token累计相对预算<=.05)，early_quality_screen已追加1232任务(16配置，早/中步critic梯度及匹配反向，control=true不参与选模)。目前任务总数9194，后续还要追加validation_repair与validation_extra。
- `repair_followup.py initial_validation`：待两个主screen完整后，自动summary、训练集选8类机制+2附加、拟合risk/benefit门控、DSW gate冒烟，再追加17475×3种子完整验证。用OMP/MKL/OPENBLAS_NUM_THREADS=1调用并等待终端结束；此时云上仍有baseline/诊断/敏感性工作，不会因CPU选参而闲置。
- `repair_followup.py extra_validation`：待sensitivity_screen,budget_control,early_quality_screen都完整后，summary并从k4/16/32、严格多点预算、early quality各选1个探索候选，DSW冒烟后追加三种子validation_extra。方法选择不看验证结果，最终仅用完整验证锁定测试。
- 分析代码统计激活率/激活失败精度/改善误伤比例，及“已测试候选集合的Oracle”作为诊断；不能当可部署成绩或所有表征编辑的上界。
- `repair_final_queue.py`/`repair_final_launch.sh`已准备但未运行，保留frozen v1不变，最终测试可对新navtest自然Base与修复同种子评分，不拿历史IL基线代替RL。需冻结开发选择后才能准备真正test清单与缓存。

10:13 UTC执行进展：两个主screen已经全部完成；`analysis/screen/SUMMARY.json`核查1,388,850条记录，natural_learn_screen同样完整。训练广筛正向方法有修复/整体小收益，但存在新增碰撞；反向也有修复而整体降分，不能用修复率单独选模。
- `repair_followup initial_validation`已结束，`SELECTION.json`锁定35个验证配置，DSW SELECTED_GATE_SMOKE通过，validation_repair已追加6555任务(17475场景×3种子×36含Base)。云上仍连续处理初始队列，无节点等待CPU选参。
- preservation_validation正在/已追加，工具session **9937**，日志provenance/repair_preservation_setup.log；保留自然输入local/linear/MLP及低损伤配对基线，最多5配置。
- 主等待监控改为工具session **44607**：`repair_monitor --until sensitivity_screen,budget_control,early_quality_screen`，日志repair_monitor_sensitivity.log。达到阶段就绪后运行repair_followup extra_validation。旧55371已经正常STAGE_READY结束。
- DSW CPU辅助对照`repair_postprocess.py`等待全三种子validation_baseline齐备后，用4CPU进程评分简单输出scale(.99,1.005,1.01,1.02)，检查表征收益是否只是进度偏移。独立run repair_postprocess_v1，工具session **89596**，日志repair_postprocess_v2.log；原仅等待的v1启动已停止，未进行计算，修复了IPC传输效率后重启。辅助协议已正确冻结arms/panel SHA。它不占用DLC 32卡。
- 新增reference_validation_diagnostic 55任务，覆盖438个留出自然失败的18种参考注入，仅诊断不选模型。
- `repair_analysis.safety(stage)`从已验收矩阵另存SAFETY.json，区分新增/移除/净碰撞、出界、TTC和零分，避免只看均分。
- 已通过异步问题询问用户最终安全/PDMS取舍偏好，目前尚未收到答复；不影响所有开发实验。默认建议安全优先，最终可保留Pareto候选作独立对照，不部署任何实际策略。

## 共享队列恢复（最新，覆盖前述run/monitor入口）

旧v1在rank030写queue.json时出现ENOENT，tmp名只有PID24，跨容器PID可重复且旧全局counter依赖flock。node1已Failed，node0已按任务身份核验后StopJob POST停止。旧所有记录/异常保留，未改frozen v1文件。恢复采用`repair_queue_v2.py`/`repair_launch_v2.sh`：跨进程UUID临时文件，mkdir按任务原子领取，不再跨节点改counter。
- **当前run=repair_20261016_v2**，执行`configs/repair_execution_v2.json`；node0=`dlc1whaxhnd8c2zs`，node1=`dlc1whaxhnnaj1nn`。DSW新协调器冒烟与旧数据精确一致；node0已实际16卡PASS，node1调度中（需继续核查两节点都运行）。
- `runs/...v2/REUSE.json`逐文件hash验证并硬链接复用5612个完成任务，无orphan；剩余13471个原任务只补未完成。新加入queue_smoke128个真实小任务检验调度，已提交列表总计19211任务。旧科学阶段protocols/results/receipts只读复用，科学方法不变。
- **主前台监控session=49372**，日志provenance/repair_monitor_recovery_v2.log；调用`repair_monitor --execution configs/repair_execution_v2.json --until sensitivity_screen,budget_control,early_quality_screen`。旧44607已因v1失败退出，旧MONITOR不能代表当前状态。必须每分钟主动等待/核查，监控异常不能只挂后台。
- CPU简单输出scale对照已仅停止尚在等旧baseline的进程并切换v2源，未丢计算；当前session **62279**，日志repair_postprocess_v3.log。CPU源`--source-run repair_20261016_v2`，等待恢复run的完整validation_baseline后评分；目的检查PDMS收益是否只是进度偏移，不占DLC资源。
- preservation_validation已完成DSW实测并追加5配置×3种子3279任务；v2已完整继承这些stage和35主验证6555任务。**下一阶段仍是等训练敏感性/预算/早期quality完成后运行repair_followup extra_validation，使用ACTIVE_RUN自动定位v2。**
- 独立测试worker目前repair_final_queue.py仍从旧v1派生，**最终测试前必须重新从queue_v2派生，保留UUID/mkdir调度修复**，再加入navtest fresh-base与trajectory_scale分支。不要拿旧易冲突counter进入最终测试。尚未读navtest任何数据。
- 已向用户说明调度异常与复用结果恢复，仍持续执行全部批准计划。异步安全/PDMS取舍问题未答复；开发计算继续。

## 10:44 UTC接续补充

用户已明确：安全优先与PDMS优先两候选均保留并独立测试；见repair_v1/USER_DECISIONS.json、FINAL_SELECTION_RULE.json和PLAN。用户确认第二节点因企业节点满载排队，现已分配；v2两节点16卡各自SMOKE_PASS，32卡真实通过，均Running。
- 新补齐固定/可学习同rank16子空间匹配对照：code/repair_subspace.py，layer6、400更新、716探索P0低->高与高identity，同初始化/网络/损失；冻结Base。输出legacy overlay文件natural_learn_l6_k16.npz中的fs/ls前缀，实际数据是配对，**不能标成自然输入replay训练**。自检曾因QR符号不连续失败，未提交此版本；保留failed_v1.log，修正连续QR与按训练目标选最优迭代后全部通过，实际loss与basis梯度/角度保存。
- MATCHED_VALIDATION_SMOKE已通过，validation_matched已追加3279任务，9配置(6个fixed/learned强度+领先pairedmean layer6 alpha.25的3同位置同强度随机/反向对照)，17475×3种子。该stage必须纳入最终开发选参和验收。
- code/repair_select_final.py已经准备，待validation_repair/preservation/extra/matched及CPU postprocess_validation全完成后执行；它按用户两优先目标锁TEST_LOCK.json和final_test_arms.json，所有拟合/门控SHA一并锁。新最终test worker已从v2重建，带UUID/mkdir、fresh navtest RL Base和action_scale，smoke改为实际最终选中方法。尚未执行，尚未读取任何navtest数据。
- code/repair_result_details.py补充分会话bootstrap的净碰撞/出界/TTC/零分区间和分失败类型表；仅派生已有矩阵。
- sensitivity/budget/reference已完成，DSW正在提前分析这三stage（repair_completed_screens_analysis.log），以便extra_validation只需分析最后的early_quality。监控session49372仍正常，CPUscale session62279继续。

预算口径澄清：budget_control按m个位置各cap=.05/sqrt(m)，保证每action token跨位置**相对编辑范数的L2合成≤.05**，并非相对范数的L1累加≤.05。此前hand-off的累计表述不精确；实际配置、结果保持不变，证明及原协议SHA见repair_v1/BUDGET_DEFINITION.json，报告须按L2定义解释。

10:50 UTC：所有探索screen、参考诊断、敏感性均完成。extra_validation已选5配置并通过DSW实测，追加3279任务；validation_matched9配置也已完整提交。**开发队列现已closed=true，合计25769任务，禁止再追加改变本轮选模范围。** 新主前台monitor session **43487**，repair_monitor --execution configs/repair_execution_v2.json（无--until），日志repair_monitor_validation_v2.log，等待两作业Succeeded后唤醒。旧49372正常STAGE_READY退出；extra setup11842已正常结束。后续按完成stage做summary/safety/details，等CPUscale对照完成并执行repair_select_final.py锁定，再独立test。CPUscale62279持续运行。

## 最新用户覆盖（必须优先，10:51 UTC）

用户要求修复验收后保留现有2×16卡，不能关闭队列、停止DLC主进程或主动释放。已立即把v2 queue.closed恢复false（此前仅关闭约1分钟、尚远未完成，没有worker退出），见RESOURCE_RETENTION_OVERRIDE.json。旧10:50关闭队列/worker退出验收要求已失效。12h时限仍计时、Reserved=0；核查延长不能假定。后续final test必须用现有容器终端另启动独立final_queue，**不能停止/重建两现有作业**；原workers等待。扩大两路线子空间ks/kf到256、r到64，要求见PLAN追加节；先完成全部修复+报告再执行新分析，不重采集。

保留节点的当前监控session=**98109**，code/repair_monitor.py --execution configs/repair_execution_v2.json --retain，日志provenance/repair_monitor_retained_v3.log。每60秒读取剩余时限，低于1h写LIMIT_NOTICE并唤醒；开发计算全部落盘且32worker在QUEUE_WAIT后返回，不要求云作业Succeeded。旧43487仅DSW monitor已替换，未停止DLC。原API上限720min，Settings.JobReservedMinutes=0已实测；创建时间保守deadline=2026-10-16 22:20:39 UTC，运行时参考deadline分别22:22:09/22:36:59 UTC。公开UpdateJob无时限参数，延长未验证，不尝试未知字段，不承诺无限。
两个容器terminal已分别实测16卡PASS，code/repair_terminal.py用临时一次URL、只存内存不打日志。最终选参冻结后，通过该terminal调用code/repair_remote_start.py，以start_new_session启动独立final_queue程序并保留原coordinator；独立run/execution/输出，**不再CreateJob、不停两原作业、所有队列保持open**。repair_audit新增--retain支持验收已完成计算与等待状态，禁止沿用旧退出释放断言。

为完整落实用户两优先级，又用仅探索screen结果追加validation_high_pdms（不受旧0.5%原成功损伤率选筛上限的全局最高总体分配置）。setup session见provenance/repair_high_pdms_setup.log；repair_select_final.py已纳入该stage。既有25769任务台账为旧快照，追加后应生成新冻结任务台账，不按旧closed清单判定完成；队列保持open。

11:14 UTC补充：CPUscale三种子全量已完成且summary/safety/details齐备，session62279正常退出。最终test除两种表征候选外，分别保留按PDMS和安全准则选择的简单scale端点（当前开发1.02/1.005，不提前锁最终），共最多4独立干预配置；repair_select_final.py和report已支持action_safety_control，避免只和偏激进的scale比较。最终smoke改为3个原train锚点+锁定后final_test panel前2个test锚点，DSW/每张卡都实际读test缓存并完整推理评分，**仍必须TEST_LOCK后才准备manifest、读取test**。修复报告生成器code/repair_report.py已准备，须final_test SUMMARY/SAFETY/DETAILS、独立600原入口重评分、开发+test FINAL_ACCEPTANCE与人工REPORT_NARRATIVE后才能build；尚未修改原正式HTML。新增稳定失败/稳定成功及固定S0覆盖统计在repair_result_details.py，不能把新采样Base自己变高质算干预修复。

11:31 UTC：已发现原random与random_subspace为固定sin/sin-QR，不能称Haar/一般随机空间统计。保留原数据，加真正Gaussian/QR对照：code/repair_true_random.py、repair_validation_null_queue.py（从v2复制，原frozen不改）。6配置=direction/subspace×3构造种子，父配置仅探索选mean_p_l6_a.25；暂时替换Editor.fit里的B或ml，try/finally恢复，不改Base/文件，不消费原生RNG。DSW v1已PASS；进一步加full/cached、每null alpha0和恢复parent输出精确检查，正在DSW v2 smoke（provenance/repair_true_random_smoke_v2.log）。需要随后冻结单独执行配置/queue，**等原开发27956任务全部完成后**，用retained terminal+repair_remote_start --program新null_queue启动两节点16卡，原主进程不动。完整validation_true_random=17475×3×7输出，3279分块；控制不参与选参，独立summary/safety/details与audit --retain。可从原开发锁定最终候选并准备test清单时并行计算该控制，但最终test另程序需控制计算结束后启动。最终报告增加真实随机对照统计及原构造限制。

用户刚明确回答安全准则：**保留净碰撞/出界/零分不增加，TTC和总失败数仅报告**。已写USER_DECISIONS和FINAL_SELECTION_RULE，不能自作主张收紧或换成全指标约束；安全优先不是保证TTC/总失败不变。两种表征候选+两种按同准则选的scale对照进入最终测试。

11:54 UTC接续：原开发仅validation_high_pdms尚余约647任务，其他13阶段均完成；validation_extra质量梯度early_quality_623ee7f924e8开发Δ+.00336，净NC0/DAC-2/zero-2/TTC0，存在合格但收益极小的安全候选。fixed/learned rank16全强度验证均负收益。还未锁TEST；不提前读test。
- 真随机DSW v2已PASS。repair_null_prepare.py已冻结独立run repair_null_validation_20261016_v1、3279任务、configs/repair_null_execution_v1.json。**自动接续前台session93423**（null_transition.log）等原COMPUTE_DRAINED后通过terminal启动两新辅助coordinator；旧主进程不动。**null监控session32232**已启动（repair_null_monitor.log），可在等待阶段就运行；须后续检查两节点16卡SMOKE_PASS和5min语义，再等drained。
- 原监控98109继续；开发summary76037继续。**自动锁候选session29199**等全部五方法stage DETAILS齐备后运行repair_select_final；**navtest首次清单检查session5999**严格等TEST_LOCK才读取1010-il_baseline两个manifest，输出provenance/NAVTEST_MANIFEST_INSPECTION.json及repair_test_manifest_inspection.log。**开发全量验收session46853**等drained+统计齐备后audit --retain。这些脚本都是工具终端等待，不是挂后台结束本轮。
- null结束执行repair_null_accept.py：全量summary/safety/details、Base矩阵逐元素与主验证相同、父方法对六个null及每类型3构造平均的配对会话CI、audit --retain。
- 新最终test worker尚未冻结/运行，可改。已改为读取**configs/repair_final_baseline.json**（待TEST_LOCK后准备）；这样不会把原baseline.json的历史no_navtest_access=true误当测试身份。新配置复制原模型/采样/评分，另写navtest cohort/样本数/panel来源/锁SHA，不改原配置。最终执行仍走保留终端，先DSW真实test+train锚点，原/随机计算结束后再启动32卡。
- repair_report.py已加入真正Gaussian构造表，keys是arm.gaussian_null字符串与control_seed；要求nullrun FINAL_ACCEPTANCE。还保存每版叙述JSON/生成器与旧新HTML，首版尚未build。不要忘记主方法与随机的配对比较JSON及simple-scale覆盖可在报告补明。
- 为等待期间准备扩展分析代码：subspace_scan_math/prepare/cv/confirm/queue/monitor/freeze/select.py，**尚未冻结/启动任何扩展数据重计算**。已通过合成数学/轴顺序/与sklearn ties AUC/AP/cluster检验冒烟，但需要修复报告验收后做真实DSW工程smoke、backend CPU/device float64吞吐/精度、冻结所有脚本后才容器启动。用户要求先完成修复报告，prepare有provenance/REPAIR_REPORT_ACCEPTANCE.json guard。
  实现两节点各自负责交错native step/start的lossless cell缓存（需400GB空闲内存，节点1.7TB，DSW禁止跑prepare），原hash逐一核验；3040cells=natural760+paired15start/step×152=2280。5折会话hashCV；原全矩复用减留折矩；projected mean gap保持旧探针。648残差+24真随机+1全维/center，共1346variant/cell。扫描有完整rank/退化截断记录；同维主/非同维对照分开按邻域稳定筛，每route/center/family最多2regions，没合格则1diagnostic，不调阈值。CV完整BH ledger，确认前冻结邻近点+同r随机/全维，只小家族留出signflip20000+Holm。代码未正式验证完成，需先审查再freeze，不修改冻结后源文件。

## 12:13 UTC最新（覆盖前述等待状态）

- **原开发已全部完成且FINAL_ACCEPTANCE PASS**：27956任务、5,655,031输出；old primary queues仍open、workers等待。98109/76037/29199/93423/5999/46853均已正常结束。
- TEST_LOCK已于11:57冻结，SHA bdcf9007bb40bc3d9e3e3386a3df3ef1b7b723c0a7f95e11ab2d8de2d30125aa。安全候选early_quality_623ee7f924e8（开发+.003362，NC0/DAC-2/zero-2），PDMS候选benefit_gate_50de88521d78（+.229966，NC+2/DAC31/zero29），scale1.02与1.005分别对应两取舍。最终highPDMS额外强配置没有超过已验证benefit候选。配置锁不再修改，不按test改参数。
- **真随机已完成并验收PASS**（49854结束）：3279任务、366975输出；新随机程序保持QUEUE_WAIT。父平移vs3高斯方向平均+.23374 [+.18809,+.26864]；vs3Haar空间平均+.17127 [+.11494,+.21632]，开发配对会话CI，不能代替独立测试或宣称精准修复。真随机各mean: subspace0+.01021/2+.00672/1-.01029；direction2-.02289/0-.04880/1-.10909。
- **独立test正在现有两节点运行**：run repair_final_test_20261016_v1，execution configs/repair_final_execution_v1.json。12:10:30/34经terminal启动，未Stop/CreateJob，原/真随机两个coordinator均保留。node0/1真实16卡各PASS，与DSW完全一致。**前台监控session86852**（repair_final_monitor.log）；**完成后自动summary/safety/details/4contrast/原入口600重评分/全audit的前台session63658**（repair_final_acceptance.log）。**不要只报告启动，要等完成验收写报告，再真实扩展分析**。
- navtest12146输入全部feature/target/identity/metric SHA已读验；train/test token及粗会话均无交集。旧cache schema仅execution_protocol_sha256/vlm_dtype，和train的protocol/cache_policy schema不同；已验证旧1010冻结code/worker.py、features.py/preprocess和VLM SHA相同，用**repair_test_features.py只读严格adapter**，不伪造/重写metadata。configs/repair_final_baseline.json为新的navtest身份，模型/采样/评分未变。FINAL_TEST_INPUTS_READY为证。未读取任何旧IL/RL测试评分/轨迹。
- DSW最终smoke run repair_final_dsw_v1，含3train+2实际test锚点PASS；FINAL_TEST_READY写run/配置冻结身份。FINAL_STATISTICAL_PROTOCOL在正式计算前另冻结4差值(safe−Base,pdms−Base,safe−safeScale,pdms−pdmsScale)，会话signflip20000/Holm4，CIs500簇重采样，analysis/final_test/FINAL_COMPARISONS自动生成。
- 报告生成器repair_report.py已加入四对比表及父−真随机配对表，并需null FINAL_ACCEPTANCE。仍尚未build。最终计算验收后人工写REPORT_NARRATIVE.json（conclusions list,interpretation,decision），build --version repair_v1，view_image检查三张新PNG，运行repair_report_accept.py --version repair_v1 --figures-reviewed。其生成provenance/REPAIR_REPORT_ACCEPTANCE.json **是扩展真实计算的前置guard**。它核查staticHTML/图片/数字/source/fit SHA，明确browser_render_verified=false，非浏览器渲染。首版接受后才跑后述扩展。

扩展代码准备新进展（仍未真实计算/冻结）：
- 新增subspace_scan_backend.py：报告guard后做DSW float64 CPU2/4/8线程与device吞吐/数值对照，只有device含传输快≥20%且差<1e-9才采用，保存SUBSPACE_BACKEND_SMOKE；freeze --backend相应值。
- CPU backend会选每节点min(64,144//threads)并发分析worker；device backend16/节点。并行度从execution读取；每node仍验证16物理卡，设备映射local%16。不是固定32 analysis workers。代码模板已适配monitor等待2*nworkers。
- **subspace_synthetic_engineering_v1合成完整联调PASS**（session60505正常结束），两路线×两center×5fold×1346请求/格，rank约束、全矩复用、P0/P1、冻结小家族后heldout确认都跑通；SUBSPACE_SYNTHETIC_INTEGRATION.json为证。没有用真实表征或重跑模型。其后只加finite-Spearman稳健保护（常数分支差返回None）。
- CV已改为每cell预计算5折held moments，两套center复用；路线一5折矩**全D汇总核对原全维充分统计**，再做global−held，不只是核8维tile。路线二也sum−held，P0训练。残差Gram求奇异方向后QR重正交，保持所有前缀span。复制raw cache用全部source SHA。
- 选区代码增加每个确认r的“最小可行同维主空间”作为固定r比较控制，以及可行的旧ks=kf=r8锚点；同r Gaussian3和fullD仍保留。候选CV完整BH ledger，最多2非重叠区域/route×center×equal/unequal，没合格则1诊断。源代码未冻结，可在真实工程验收前修正；一旦freeze就不能修改已执行源，另开新版本。
- 扩展还有**后处理/独立验收/报告段生成器未写**：需确认结果汇总、per-route全确认家族Holm（P0/P1都算，controls同列；缺失rank按p=1）、冻结区域效果/邻域/控制表、固定r ks×kf热图+fixedkf/ks/r线图、CODE/原始输入/数据范围/有效rank台账核查，写analysis/subspace_scan_v2/REPORT_SECTION.html后再build新version同一报告并验收。不要把全网格heldout提前评分，只冻结小区+controls。
- 实际重计算启动流程：首修复报告PASS→backend真实工程probe→读审完所有subspace代码→freeze→经retained terminal remote_start --program code/subspace_scan_queue.py，在两原job内新aux程序，原三类程序仍waiting。新monitor会等两prep完成后生成CACHE_INDEX解锁workers，按分钟监控/5min语义/12hdeadline；CVdrained唤醒→select冻结并追加confirm兼容任务→monitor --phase confirm→独立audit+report。


## 最终完成接续：全部验收通过，资源继续保留

记录时间：2026-10-16T13:45:40.760719+00:00。本节覆盖前述运行中进度、旧monitor session、关闭队列或等待作业Succeeded的要求。**无待续算任务，不自动启动下一轮实验。**

- 正式报告：`doc/work-output/1016-rl_representation_analysis/representation_observation.html`；最新主报告归档 `provenance/report_versions/repair_with_subspace_final/`，扩展章节归档 `analysis/subspace_scan_v2/report_versions/final_v5/`。整体复核 `provenance/EXPANDED_FINAL_VERIFICATION.json`、最新报告验收 `provenance/LATEST_REPAIR_REPORT_ACCEPTANCE.json` 均PASS；HTML/核心数字/链接及图像已检查，浏览器渲染未验证。
- 修复开发27956分块／5655031输出、真正Gaussian/QR对照3279分块／366975输出均完成。冻结方案后的独立navtest12146场景×5自然采样×Base及4干预，共303650输出，600条原评分入口复核全部分项差异0。安全优先ΔPDMS约+0.0026、PDMS优先约−0.0148，区间均跨零；后者净碰撞+98、出界+47、零分+144、TTC扣分+338。安全规则按用户确认的净碰撞／出界／零分不增加，TTC与总失败数另报；当前没有稳定全局修复证据。
- 扩展复用既有表征和充分统计，无模型重采集。3040位置、4091840请求配置、5折会话CV完整；冻结16区域／215读出配置后留出确认，10区域达到邻点与会话标准（路线一4，路线二6）。路线一仅自然S0；路线二另检验P0/P1。144个预设控制比较、完整BH/Holm、多维固定变量扫描及全维／同r随机对照均保存。路线二ks8/kf48/r48候选成立，但同r等维优势不确定，不能外推为维数越大越好或已找到因果修复机制。起点80/60无合格高低端点对、40/20很少；原始采集完整，不能据此重跑采集。
- 新子空间未用于重选本轮测试方案；真实交互闭环未开展。所有冻结代码、协议与既有结果保持不变；未来兼容实验追加对应队列，换程序用已验证容器终端和独立config/run/output。

**资源现场证据（13:38 UTC）：** `provenance/RESOURCE_RETENTION_FINAL.json` PASS。`dlc1whaxhnd8c2zs`、`dlc1whaxhnnaj1nn` 各16卡、均Running；开发／真随机／独立测试／扩展四套队列open，原始PID5及各协调器保留，worker均等待。没有停止／释放当前作业。上限720分钟、JobReservedMinutes=0；保守共同截止 **2026-10-16 22:20:39 UTC**，启动新程序不重置时限，**未验证可不中断延长**。未来实验先现场核查剩余时间与进程状态。当前前台重负载监控均已正常结束，资源由DLC原主进程维持；不宣称结束对话后智能体仍会自动唤醒。


## 最新覆盖：两个节点已释放（2026-10-16）

用户明确要求释放此前保留的两个DLC节点。本节覆盖全部“保留节点／主进程等待／队列开放”的历史接续要求。已按JobId、工作空间、任务名及启动命令核验身份后调用StopJob；`dlc1whaxhnd8c2zs`、`dlc1whaxhnnaj1nn` 均确认Stopped，JobReservedMinutes=0。开发、真随机、独立测试、扩展四套队列已关闭。所有科学任务此前已验收通过，结果与报告保留，无待续算任务。证据：`provenance/RESOURCE_RELEASE_FINAL.json`，当前状态：`STATUS.json`。未来计算需重新安排资源，不再使用已停止的容器终端或假设原进程仍在。
