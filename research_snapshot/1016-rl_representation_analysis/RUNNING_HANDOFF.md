# 当前状态：全部实验与报告已完成，新72小时节点保留

2026-10-18接续：**没有待续跑重负载或报告任务**。同一HTML已按研究逻辑中文重编，正文以对照表为主，42张原数值表和1,131条记录保留于折叠附录，图表合并重绘为14张中文图。已增加左侧分级目录，正文、候选分布图与附录均可跳转并自动展开对应内容。当前报告版本与验收为`report_distributions_20261018/`，正文含六类首选与两个强第二名的八组分布图、`vlm_repair_v1/REPORT_ACCEPTANCE.json`；改版与原科学验收的衔接见`provenance/REPORT_PRESENTATION_REFRESH_20261018.json`。`provenance/VLM_FINAL_PACKAGE_VERIFICATION.json`和v5报告保留为改版前的完整科学验收，不将其旧HTML指纹用于否定当前编排版本。实验结果与冻结代码未变；未新增计算或操作资源。未经新指令不自动追加实验。

最后旧节点legacy1已在用户明确授权且所有任务落盘后主动停止；legacy0此前平台终止。A1/A2/B1三个72小时16卡节点及其开放队列保留，B2和本人续建006仍排队，007未提交且不再自动提交。任何新72小时作业的停止/释放仍需用户同意；作业累计时限不会随新实验重置。实际状态请读`vlm_repair_v1/elastic_v1/CLONE_LIVE_LATEST.json`并现场核实，不将本段快照当持续监控证据。

报告：`../doc/work-output/1016-rl_representation_analysis/representation_observation.html`。最终计划及结论记录见`PLAN.md`末节。以下为历史运行记录，不代表现在仍有计算待做。

### 2026-10-17 当前资源策略覆盖（高优先级卡池任务）

用户要求优先充分利用现有4节点，不因旧任务落盘而提前释放原两12小时节点。滚动额外要求同池汇总空闲≥32张连续120秒，并在Stop前重查；仍不保证整节点可用或重新调度。只读容量等待器已直接托管运行：python3 -B /mnt/workspace/dlc-pool-monitor/wait_for_capacity.py --min-free-cards 32（session36932）；不发送ntfy、不改外部脚本或配置。没有容量证明则不主动Stop旧DLC，接近15:52 UTC前做好精确中断/接续，不能假定可重新获得。

机械监控改为code/vlm_clone_watch_v4.py，每300秒检查，正常静默，阶段/异常/旧时限剩余120分钟时唤醒（当前session19455）；旧DSW v3监控253567已精确退出，所有DLC计算未动。滚动只能使用code/vlm_elastic_roll_capacity_v4.py，替代此前无容量保护的v3入口；CURRENT_USER_RESOURCE_POLICY指向v2，旧授权保留作历史。成功容量结果须保存到elastic_v1/capacity_wait并建立带SHA的CAPACITY_AVAILABLE_LATEST.json，新鲜度180秒；原始JSON需带exit_code=0与wait_script_sha256。


# 当前接续：五批VLM修复继续，4节点运行、2节点排队

当前核实状态（2026-10-17 10:23 UTC）：原DLC dlcu6ibrfm98a7nh / dlcughx571mkmu6x 继续GPU及在途完整网格计算，原上限截至今日15:52 UTC；A1=dlcb46akrk2hji1u、A2=dlcgxxrm3yape59d 均Running/4320min，新增160 CPU worker及32 GPU worker已加入，共64卡。B1=dlcqdtslnqnytsc7、B2=dlcwhkv0rt5t8crx均Queuing/4320min，身份及自动bootstrap已配置。4个本人冗余模板均Stopped。主实验final_test已完成6073任务/546570条输出，动态64卡检查5760条PASS；训练集复核及另四批继续。DSW第五批冻结test特征采集中（session70551）。前台监控code/vlm_clone_watch_v3.py（session71212），动态验收与原收尾分析在elastic_002。完整网格/late资格尚未齐，未暂停或停止旧DLC。旧滚动入口code/vlm_elastic_roll_clones_v3.py；本人续建elastic_006/007已准备但未提交，须先精确旧节点退休证明，再以code/vlm_self_renewal_v2.py提交/激活72小时实例。不得调用旧全局reconcile。全部五批、原4544/补正128网格验收、联合统计、独立评分和报告图表验收完成前不结束本轮；新实例和队列最后保留等待用户同意释放。

### 2026-10-17 克隆配额接入（当前资源方案）

用户确认师兄与本人地域/工作空间相同：cn-wulanchabu / 245760。由当前DSW准备并提交本人配额排队模板，用户从师兄账户克隆；回传原任务→克隆ID并确认时长至少4320分钟后，写入独立身份绑定，先通过挂载/软件/全部配置卡/真实模型与评分验收，再接入原子领取队列。无需获取师兄账密；不假定拥有克隆任务的云端查询/停止权限。共享心跳和Python指令收件箱负责监控/接续程序，保留失败原文及全部结果。

已提交并云端核验的4个单节点16卡、4320分钟模板：A1=dlc1ma7v2ju7zxvh（elastic_002）、A2=dlc1mk7ggbl5xg23（003）、B1=dlc1mu71u38w5kya（004）、B2=dlc1mu71u3enbzr7（005）。均Queuing，Reserved=0；企业目前仅2节点可用，优先克隆不同的两个模板，其余分批接入。原排队模板只等待身份绑定，不会误领取计算；绑定实际克隆且共享心跳确认核心已启动后，才停止对应本人冗余排队任务，保留克隆及其他未接入模板。

入口 code/vlm_clone_manage.py；冻结源清单 vlm_repair_v1/elastic_v1/CLONE_EXECUTION.json；指令与心跳见 elastic_v1/nodes/<node>/commands、attestations/<actual-job>；前台监控 code/vlm_clone_watch.py。卡数/rank/验收按配置和实际参与记录，原32卡仅为既有部署。已运行原两节点继续原任务，新节点CPU只拿未被领取格点；GPU须等完整主验证自然结束、全部本卡冒烟及动态验收服务就绪才进入主队列。旧节点在途长任务保留；滚动换72小时的准备代码仍需适配克隆资源证据后执行，绝不调用旧全局reconcile。新增/续建节点不自动释放，完成后须获用户同意。

提交证据 provenance/CLONE_TEMPLATE_SUBMISSION_20261017T0905.json。克隆真实运行、冒烟、动态服务迁移均尚未执行；不要把准备/提交成功当作新算力已可用。

以下为历史观察/修复接续记录，不代表当前计算已完成。

# 当前接续入口：表征修复已授权，正在实施

用户已认可修复计划并要求开干；见PLAN末节与REPAIR_HANDOFF.md。两条观察路线已结束，原始产出保留；当前修复代码/协议/运行须独立命名，使用两节点各16卡动态调度，持续等待并验收。不要把下面的旧观察完成状态当作本轮任务结束。

# 当前接续入口：两条路线均已完成

先读`PLAN.md`中的正确定义和最终完成表，及`STATUS.json`、`OBSERVATION_PROGRESS.md`。当前没有待续跑DLC或DSW计算，不重复提交或覆盖结果。

- 路线一=模型自然S0成功/失败，完整103288场景（90153成功、2288失败、10847中间）；不是GT初始化候选。运行`natural_s0_repr_20261016T080905Z`，两个16卡作业`dlc9cj9xntza8q3z`/`dlc9mivbfrv2je24`均Succeeded。每条轨迹精确匹配原基线，760单元/1520项主检验、共同坐标分布与连续质量已完成。入口`analysis/natural_route1_v1/`。
- 路线二=自然失败输出与同场景GT配对、加噪、完整去噪及重评分。原GT不按90分筛，P0/P1固定对应噪声。原`analysis/observation_v1`所有结果及其global_class_residual均属于路线二；分布/独立失败类型补齐为`analysis/paired_route2_completion_v2`。
- 正式报告：`../doc/work-output/1016-rl_representation_analysis/representation_observation.html`；完整验收：`provenance/TWO_ROUTE_FINAL_VERIFICATION.json`。此前OBSERVATION_FINAL_VERIFICATION只机械核查了路线二数据，不能证明路线一完成；更正和旧版在`provenance/route-definition-correction`。
- 实际数据来源、模型/种子/轨迹/统计/覆盖/进程退出均已验收。所有本任务计算结束，仍只观察，不干预、不训练修复。
- 调试历史：首次路径类型错误仅影响投影启动，`natural_analysis.py`与已完成moments/760cell保留不变；`natural_analysis_v2.py`修一处Path转换后只接续project/evaluate。执行hash分别由natural_analysis_execution_v1/v2冻结。不要因保留的旧错误标记再次重跑。

2026-10-17 09:12 UTC接入验收：A1实际克隆dlcb46akrk2hji1u、A2实际克隆dlcgxxrm3yape59d，GetJob均Running/4320分钟，实际16卡PPU-ZW810E、176CPU与挂载/版本/模型SHA全通过；160新CPU worker数值冒烟通过且已领取原未领取格点；32新卡全部真实模型/评分冒烟通过，验证任务逐字段重放精确一致。对应原排队模板已Stopped。B1/B2继续排队待用户克隆。动态验收服务在elastic_002正常运行；旧6个闲置验收等待器已验证退出，原GPU/full-grid/DLC主进程保持。首个10秒退出检查超时原错保留，精确故障确认与服务新心跳绑定于elastic_v1/RESOLVED_ADAPTER_FAILURES.json；原postcompute主动切换的supervisor记录由原精确故障账本确认。

新增GPU暂未进入队列，须等原完整验证自然结束、PRIMARY_STAGES_APPENDED存在才enable。克隆实际身份/源排队模板明确区分。旧节点滚动入口改为code/vlm_elastic_roll_clones.py，独立冻结清单CLONE_ADMIN_EXECUTION.json；只读inspect当前缺完整网格验收/最终分析/late冻结，尚未暂停、停止或重建旧DLC。后续前台监控为code/vlm_clone_watch.py，按阶段唤醒后接续；不会因原模板Stopped误报克隆停止。

2026-10-17 09:21 UTC接续：旧analysis_finalize等待器也已验证闲置后迁入elastic_002，原数值源码不改，原supervisor主动退出记录与新心跳精确绑定。此后滚动旧节点不必等所有收尾分析完成，仍必须满足完整旧重计算结束、全网格验收、late候选拟合/资格阶段结束、所有旧GPUclaim提交与新72小时实际算力/服务就绪；入口code/vlm_elastic_roll_clones_v3.py，未执行旧DLC停止。新前台监控code/vlm_clone_watch_v2.py。一次前置休眠检查拒绝后提前入队的启动被RETIRED依赖保护拦下，未启动重复分析；原命令/日志保留，RESOLVED_COMMAND_FAILURES按精确job/pid/rc/log签名、不可变日志SHA及新替代心跳确认，不能全局忽略报错。

2026-10-17 09:36 UTC：原完整validation_main 4369任务全部完成，主候选/对照锁定与真实最终工程检查通过；PRIMARY_STAGES_APPENDED落盘后，elastic_002/003于09:36:10/11启用，32新rank均已进入实际计算，目前共64 GPU worker。原CPU在途保持；测试复评/全训练集诊断/已批准后续批次同队列并行。DSW第五批FEATURE_ENGINEERING_PASS通过后已开始12146例冻结测试特征采集。扩容边界证据elastic_v1/EXPANSION_BOUNDARY_ACCEPTANCE.json；新增每卡真实输出5分钟检查将独立唤醒验收。

2026-10-17 09:42 UTC：B1实际克隆dlcqdtslnqnytsc7、B2实际克隆dlcwhkv0rt5t8crx，均GetJob核验Queuing/4320分钟；对应本人B1/B2原模板均已Stopped。实际克隆身份已绑定，预置bootstrap先等实际LAUNCHED及完整CPU/GPU冒烟/工程复放，再做5分钟阶段检查，接入队列后另做逐rank实际输出5分钟检查，避免排队未启动时过早检查文件。监控改code/vlm_clone_watch_v3.py，用克隆实际云端状态/创建时间与共享心跳，不把正常排队当心跳异常。A1/A2的新增32卡接入后真实输出5分钟验收均PASS（每节点16rank、各1440条核查输出），原错误均有精确解决证据，无新未解决失败。

旧节点72小时续建准备：已独立准备elastic_006→legacy_0、elastic_007→legacy_1的16卡/4320分钟配置，均未提交，未占额外资源。入口code/vlm_self_renewal_v2.py；submit硬性要求对应旧作业retirements/<legacy>.json双终止证明，不能在旧任务还活着时误启动。确认旧作业安全退出后逐个submit→activate，activate先保存真实云端72小时回读，再绑定本人新作业身份并追加同一bootstrap；runtime_kind=OWN_RENEWAL、was_cloned=false，兼容身份门控文件名但不可误称师兄克隆，也不可取消它作为冗余模板。续建节点结束后仍须用户同意才释放。4个师兄克隆及两节点续建共6个潜在实际节点；registry还保留已退休旧rank，历史身份数不等于同时占用节点数。

2026-10-17 11:06 UTC：DSW冻结VLM特征采集session70551已rc0完成，12146场景/760分片及全部token、数组SHA由TEST_MASKS构建复核，无缺失。冻结观测门控风险阳性889场景；实际父算子并集覆盖1769场景、885任务、5噪声，已自动追加原GLOBAL队列。COLLECTION_REVIEW.json保存复核及分段计时，未改门控/模型/种子。新静默监控session80173。

2026-10-17 11:29 UTC验收启动修复正在进行：主训练/测试推理均已完成。旧vlm_elastic_entry.py虽然patch import模块，但runpy直接执行final_accept时重定义audit32，误触固定32检查；不影响GPU/轨迹/完整网格。独立冻结ACCEPTOR_RECOVERY_EXECUTION：entry_v2仅直接调用同一原main，其余数值函数/评分/源码不变；control_recover_v2在A1精确确认旧8978/8979已退出，保留并接管原8980/8981/8982等待器，仅重启postcompute为27896，新service27895。原异常和日志已复制在controllers/recovery_20261017T1130。需等待实际primary SCIENTIFIC_ACCEPTANCE通过后，服务才更新三个精确故障账本及旧postcompute心跳引用；不可提前忽略旧故障。前台恢复等待session96884，容量等待36932继续。旧DLC未停。

2026-10-17 11:31 UTC：上述独立启动器修复已实际验收，primary SCIENTIFIC_ACCEPTANCE PASS；64实际rank、600原源码独立评分七项精确、103288训练/17475验证三噪声复现全部通过。RECOVERY_READY和RESOLUTIONS_UPDATED均已写入，旧三种精确故障账本/心跳引用更新已核查PASS，不忽略任何其他新错。后续主收尾使用entry_v2，其余原8980/81/82继续原地运行。

2026-10-17 11:59 UTC：第五批OBS INFERENCE_COMPLETE通过，1769实际并集场景×5采样，原12146自然测试组合完整。早期动态验收按64实际参与卡抽查1270条，种子/轨迹/评分/力度PASS；最终仍需五批收尾的600原源码重评分。主队列继续Q邻域精调及语义分层复放，未更改在途程序。原full网格2096/2272，尚未完成。静默v4监控session23484，容量32卡等待36932。

2026-10-17 13:56 UTC：QDA提前批次完整test及103288训练三噪声已完成，等待全批联合验收。原full网格2260/2272；13:54旧两节点只读进程检查确认11个4096D长任务仍计算（node0=8、node1=3，各约9.8–10.7 CPU小时），均未停止。官方UpdateJob公开字段无JobMaxRunningTimeMinutes；IN_PLACE_EXTENSION_REVIEW留来源，已向用户询问控制台/管理员能否原地延长，未发未证实Update请求。原截止15:52:13 UTC。

到期接续预案已冻结但未执行：code/vlm_deadline_handoff_v1.py，DEADLINE_HANDOFF_EXECUTION。只有剩余<=15分钟、全部原重CPU/late资格结束且分析服务已迁移时，才能在各旧容器drain，最长等600s在claim提交边界暂停本任务GPU及producer，保留DLC主进程直到平台自然终止；不含Stop/Delete API。15:52后DSW confirm需两次job/pods终态证明，写原retirements标准格式，再可用elastic_producers迁移未完成生产器并用self_renewal_v2申请72h本人续建。若重CPU未完成则DEFERRED无进程改变，不能冒称已checkpoint。实际指令需当时生成并核对，不提前执行。当前静默watch v4 session87534（warn90min），容量32卡等待36932。

2026-10-17 14:25 UTC：时限90分钟预警触发；旧DLC截止仍15:52:13，无原地延长答复/证据；A两节点余66.7小时、B两节点仍Queuing。原full网格2271/2272，剩['bridge_pre__grid_11']；GLOBAL138033任务/134271完成，64卡继续计算。容量32卡连续窗口等待仍未返回，未主动释放/重启/暂停旧节点。下一时限提醒缩为30分钟；真正最终15分钟drain前需检查full-grid审计/late资格/拟合和所有安全前置，不提前暂停在途任务。

2026-10-17 14:39 UTC：原2272完整格点和4544原rapid/full结果全部完成并通过FULL_ORIGINAL_ANALYSIS_ACCEPTANCE（14:35:21）；约10小时旧CPU任务全部保住。late资格48任务中38先完成，5个worker因save_npz对字符串fingerprint错误传equal_nan=True触发TypeError；旧两qualifier监督器及late_services派生报错，原selector/repair及其他5个健康inflight不停止。原source不改；独立dtype兼容适配器只给字符串精确比较，浮点保持equal_nan精确，失败指纹拒绝工程测试保留。旧两容器已验证rank6/20/22/26/30原worker终止，分别OLD_NODE_0/1授权，仅在原claim目录保留前OWNER并转给2100000+oldrank，目录从不重排，避免影响活跃claim。A2服务命令20261017T143847_31049c75，code/vlm_late_dtype_recover_v1.py，LATE_DTYPE_RECOVERY_EXECUTION冻结；等全部48真实资格提交后才精确确认原9个异常。前台恢复等待session56787；容量36932继续。新常规监控尚未重启（旧session44802已因原异常退出），不得提前忽略原异常。

2026-10-17 14:42 UTC：dtype独立适配已实际PASS，48资格任务全部完成；工程floatNaN/字符串相等/错误指纹拒绝通过。5个已验证终止的claim完成，原5健康任务保留，原9个异常按精确SHA和A2持续心跳确认，均已复核resolved=True。原4544统计不变，没有重采模型。恢复服务继续保留A2。下一常规静默监控重新启动，warn30分钟；容量等待36932仍运行。

2026-10-17 用户已答复没有找到原地延长办法；沿用原15:52:13截止，不发未经证实的UpdateJob写请求。DSW独立deadline_launch_v1已冻结：将在15:42（保留前序GPU计算至最后约10分钟）通过已验证旧容器终端启动deadline_handoff_v1 drain，核验完整CPU/资格/fit结束后才在claim提交边界暂停；DLC主进程保留至平台自然终止，不调用Stop/Delete。若已退休或时长延长则跳过。工具托管终端负责等待并返回真实QUIESCED或DEFERRED，DSW仍需确认双终态、迁移未完成producer与续建申请。

2026-10-17 15:10 UTC附近：SEM INFERENCE_COMPLETE已落盘，当前五批中primary/SEM/QDA提前/OBS均推理完成，late新残差批次继续。常规监控刚因SEM完成唤醒；旧节点仍占用计算，15:42预定drain的DSW托管session84409仍等待，容量36932继续。正式报告尚未build/验收，不能按四批提前收尾。

2026-10-17 15:16 UTC附近：SEM SCIENTIFIC_ACCEPTANCE通过，实际参与rank动态核查、600原源码独立重评分最大差0，原Base七分项精确。deadline_launch session84409仍待15:42；旧节点不主动Stop。当前正式报告builder为独立未冻结v5，已加实际强度/精度/随机反向对照、按批次明确fulltrain覆盖、弹性及两次兼容恢复证据；尚未build/审图/正式验收。所有五批最后必须等ALL_FIVE_BATCHES_ANALYSES_REVIEW_READY再写正式HTML。

2026-10-17 16:20 UTC实际云端核查：legacy0实际GmtFinishTime15:53:46，已double-terminal；legacy1仍Running，max720、GmtRunning03:53:47，已超过标注上限但未被平台结束，保留继续用，不推断可无限保留。B1 elastic004已Running/GPU_ENABLED/ENGINEERING_PASS，B2 elastic005 Queuing；新本人续建elastic006=dlc1mxzax7hcl8tx已提交/激活、实际4320min，现Queuing，未当作新算力。当前真正运行仍4节点（legacy1+A1+A2+B1），新B1的后验5min证明待读。

15:42 deadline保护未能全部quiesce，两边15:51:53均DEFERRED且自动SIGCONT恢复全部已暂停进程，无主动Stop/Delete；不可使用旧QUIESCED路径迁移。v1 confirm对legacy0已写不变终态证明，对仍运行legacy1按20min观察上限退出，原错误保留，不是模型故障。独立v2可按单legacy-id确认/恢复，只处理已真实结束节点的rank，绝不碰仍运行legacy1或其他活跃claim。现将接续legacy0，使用原已验证GPU程序新增独立工程replay stage，输入切片/arms/种子/评分不变；保留原claim目录避免重复领取，完成后严格校验覆盖并按原taskid提交canonical结果，工程replay不参与新统计样本。每个legacy独立计划，已确认终态证明不覆盖。

2026-10-17 16:24 UTC接续结果：首旧节点的16个未提交GPU分片已通过单节点v2按原输入/arms/种子/评分在现有验证GPU程序上新增工程回放stage，16:21:46全部REPLAY_COMPLETE PASS。原已完成输出不覆盖，原失败claim不全局清理；canonical记录覆盖/seed/7score/shape/cap逐条验证，工程回放不生成科学scores矩阵、不进入Oracle新样本。v2第一次仅因新父目录未初始化在prepare入口报错，未读改任务/claim，异常原文保留；目录由失败记录原子写入创建后同代码重试实际通过，EXPIRY_OPERATIONAL_REVIEW说明。

当前云端异常不是模型故障：legacy1超过720min仍Running，16:23其rank16/17/18/31最新真实final_test_late输出状态仍更新。按用户保留资源要求继续使用，绝不假定无限时长。新常规监控改code/vlm_clone_watch_v5.py，OVERDUE_MONITOR_EXECUTION冻结；仅已审阅legacy1的负时限Running重复提醒被抑制，真实负小时仍保留状态，终态/错误仍唤醒，其他新72h正常时限告警保留。B1四项环境/数值/逐卡/真实GPU5分钟全部PASS。需要重启v5监控（上一个95816已因B1通过等阶段返回）。容量等待36932继续；old1未真终态，因此007仍未提交，未迁移仍在old1运行的late producer。正式HTML仍未build。

2026-10-17 16:42 UTC用户追加：最后旧节点若无任务可主动停止，有任务则保留。现场通过云端/容器进程及rank16..31最新状态核实，16卡均COMPUTING navtrain_late_locked（全训练集最后一批复核）；保留不中断。此后late推理/追加生产器结束且确认全CPU/GPU无在途任务时，可仅停止legacy1，不再受旧空闲32卡滚动门槛限制；新72h节点与队列仍保留。只读核查证据见elastic_v1/idle_release_review/LIVE_2026-10-17T164135.144963_0000.json。

2026-10-17 17:22 UTC：用户授权旧节点无任务可主动停止。late INFERENCE于17:13:11完成；只读容器实核查全部生产器已结束，GLOBAL189828/189828、原队列42496/42496，无任何legacy1未提交claim，所有原full/补正full/资格完毕。首次探针因未知cold_global_recovery闲置监督器拒绝，未修改进程；v2显式要求该监督器STATUS COMPLETE/rc0后验收通过（LEGACY_IDLE_RELEASE_EXECUTION_v2）。17:19后仅向legacy1发StopJob，17:21后两次job+pod终态确认，retirements/legacy_1.json已有标准证明。3个实际72h节点及全部新队列不动；007不再提交（无剩余重推理需求）。ELASTIC/idle_release_review保留两个探针/授权/Stop回包/终态证明。最终ALL/FIVE验收仍在elastic002，不能当作报告已完成。
