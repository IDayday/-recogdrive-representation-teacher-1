# 当前状态：全部实验与报告已完成，新72小时节点保留

2026-10-18接续：**没有待续跑重负载或报告任务**。`provenance/VLM_FINAL_PACKAGE_VERIFICATION.json`为整体PASS，`vlm_repair_v1/REPORT_ACCEPTANCE.json`为正式报告PASS；同一HTML已整合五批VLM修复、完整搜索与精准修复上限，全部旧图保留。未经新指令不自动追加实验。

最后旧节点legacy1已在用户明确授权且所有任务落盘后主动停止；legacy0此前平台终止。A1/A2/B1三个72小时16卡节点及其开放队列保留，B2和本人续建006仍排队，007未提交且不再自动提交。任何新72小时作业的停止/释放仍需用户同意；作业累计时限不会随新实验重置。实际状态请读`vlm_repair_v1/elastic_v1/CLONE_LIVE_LATEST.json`并现场核实，不将本段快照当持续监控证据。

报告：`../doc/work-output/1016-rl_representation_analysis/representation_observation.html`。最终计划及结论记录见`PLAN.md`末节。以下为历史运行记录，不代表现在仍有计算待做。

# VLM追加任务当前接续（21:04 UTC）

用户范围全部覆盖；两个现有16卡节点 dlcmi53bf3ah2c2s / dlcms4op7agqj50d 不释放，主进程和队列保持。保守期限 2026-10-17 03:42:10 UTC，未验证可延长。不要因为旧动作头验收或当前回合耗时而终止追加任务。

- 动作头候选全部重计算和科学验收完成，SCIENCE_READY/FINAL_ACCEPTANCE/CROSS_STAGE_REPEATABILITY PASS。R1/R2最终测试净PDMS未确认提升。旧报告生成与视觉验收待做，优先追加重计算。旧队列又追加oracle_ungated_validation，4个关键去门控方法×17475×3，加Base共262125输出，已完成并分析验收；旧冻结选择不重选。
- VLM全103288场景6456分块20:29完成；62模块、2272模块/池化区域组合，32卡真冒烟和512场景语义抽查PASS，COLLECTION_COMPLETE逻辑验收PASS。冻结collection/runtime不要修改。
- 两节点pivot逐成员读取并转连续cells，约614GiB RAM缓冲/节点；node1在21:02开始写cells。状态整批读完才更新可能滞后；已容器/proc核查身份/RSS/io前进。原始块持久化，完整cell及SHA才可验收。偶见CPFS ESTALE，common.read/sha有界重试，不能凭一次cat失败宣告作业失败。
- 全11633配置×2中心化full-grid CPU扫描已冻结并启动32worker，另独立rapid81配置覆盖全部cells的全r PCA/随机/全维＋能量/QDA，32worker，全部数值smoke PASS。真实1536D单次完整几何443秒，当前期限内不保证全Cartesian全部完成，不能冒称全部完成。
- full-grid队列优先每层1个canonical格点（62个），其余2170有显式SCHEDULER_RESERVED claim和history，不算结果，40个已有worker claim保留不干预。FULL_GRID_SCHEDULE/STATUS记录。follow session34681每分钟对已完成canonical层释放一个强候选区域。补充8CPUworker/节点、2线程仅抢canonical，code/vlm_core_scan.py，node0已启动，node1待启动（configs/vlm_core_scan_launch_node1.sh），不改原冻结扫描代码。节点现场CPU176核无quota。所有待算完整范围保留。
- 为提前进修复，从源块只抽interface_post全部41区域到early_interface独立目录（无模型重跑），全网格CV已完成；后续须与formal pivot cells SHA/数值完全对照。接口线性AUROC约0.70，QDA约0.76，仅相关性。初步选择5类代表（低/中/高r、QDA、全维），两个节点32卡已完成1000组coarse配置×32训练case，并追加20候选×新256探索case replay。所有实际cell/config/rank/噪声指标保留原文件。
- 正式修复run=vlm_repair_20261016_v2，engine=vlm_intervene_v2，queue=vlm_repair_queue_v2；32卡全部62位置零编辑/cache/评分DSW精确复现；非零各模块完整forward/suffix等价，10种算子、风险门控、reverse/Haar、零组合实际两case×2seed重复/cap验证PASS。REPAIR_STAGE_AUDIT已32卡3312记录PASS。V1 GPU queue也保持idle不关闭。
- VLM_FITS/SELECTION/FUNNEL/RESULTS已写并在DEVELOPMENT_CODE_FREEZE记录。funnel session8062滚动冻结每块候选、4CPU进程探索fit/val读数，再追加coarse。replay session66554将每块各算子净收益/失败Oracle及各rank代表送新256训练case复查。新pipeline使用独立源文件，不改冻结collection和推理。后续还需补强残差家族候选、全局精筛/门控/组合/完整验证/锁定测试/全面Oracle与报告。已完成候选不可因改代码重算覆盖。
- 辅助独立engine V3测试索引缓存/接口投影缓存，未采用/未启动DLC：V3_EQUIVALENCE_PERFORMANCE尚待读取，session7163。若未显著改善（预设>=10%），不采用。此前预取对照轨迹/评分/实际编辑完全相同，热样本约1–2%收益；未加评分进程。EIGEN_BACKEND_PROBE表明该设备FP64 eigh更慢，不切数学后端。
- 所有旧已评分面板Oracle在legacy_oracle_v2/INVENTORY覆盖，逐方法failure-only和benefit及面板全部实算候选max，null/特权GT单列。v1分类缺少control_kind已被v2修正，引用v2。还需并入新增ungated、合并严格相同面板的候选Oracle、补统计CI和报告；不同面板不能混用。finaltest既有诊断不能用于新VLM选参。
- 监控：foreground session45015原每分钟DLC时限/collection/pivot/cells/failure；code/vlm_progress.py可查三扫描与两主run。root所有重计算完成前保持工具等待而非留后台结束。重计算/报告/最终验收当前均未完成，不得标记总任务完成。

## 21:48关键更新（优先于上文）

- 全2272原始cell转置完成，CACHE_COMPLETE正式验收PASS；6456源块whole-SHA各由恰好1节点核验，64缺失文本池之外的必有池覆盖全103288；优先接口41池与正式缓存SHA逐项完全相等。
- 发现真实工程错误：`Output requirements:`的冒号与换行被BPE合并，子串定位失败，导致command/requirements在语言30模块＋接口2模块共64cell被错误记空。其它2208名义cell不受影响，旧64项INELIGIBLE不是无差异证据，不得宣称完整token覆盖。SEMANTIC_MASK_CORRECTION记录；新code/vlm_semantic.py使用无冒号锚点，两个真实case native hidden、轨迹、评分精确等价和64池非空smoke PASS。独立run vlm_semantic_20261016_v2，DSW rank32连续工作session28998；两个DLC节点新gap collector仅在对应GPU的V2/V5/final workers QUEUE_WAIT时采下一例，主实验优先。当前DLC启动receipt56447/67960待poll。所有旧输出保留。后续必须完成64池缓存/CV/竞争候选修复，不能只修代码就算完成。
- 精确latent去重的新queue V5已实际3case×64真实校准arms×2seed与原V2完整轨迹/seed/评分/实际编辑逐字段完全相同；热耗时35.14→13.49秒，ratio0.384，采用于新阶段。当前冻结V2广筛/重放完全不动。全局新run vlm_global_refine_20261016_v5，REPAIR_EXECUTION_v5；待V2全部完成且PARENT_LOCK就绪才加载GPU，两个容器已部署waiter。
- 所有CPU生产/调度已从DSW优雅交给容器：DSW8062/66554/74063/34681已仅SIGINT父进程退出130（主动交接，非实验失败），DSW_CONTROLLER_HANDOFF有证据，所有DLC主进程/队列完全未触碰。容器host_v2在node0 pid40910运行funnel，node1 replay40814/residual40815/global_v5 40816/schedule40817均RUNNING；CONTROLLER_EXECUTION_v2冻结代码SHA。global_v5从旧run读已完成源stage，在新run做refine→3650 replay→组合→17475×3验证→FINAL_CANDIDATE_LOCK。它尚未自动纳入新semantic修复，必须另行实现补池分析/候选/修复并在最终总验收计入。
- V5的当前global脚本还有待按真实结果审查/测试，尤其门控/组合/最终统计；最终测试/全train锁定回放程序尚未部署。code/vlm_intervene_v4.py、vlm_repair_queue_v4.py仅已写未测试，修了support_projection的Haar支路，不可直接当通过；最终宜组合V5精确去重＋V4控制分支（新queue V6）。需要实现真实选中父项/控制engineering→独立最终GPU启动（旧计算结束后）→锁定test5seed＋global两角色fulltrain3seed、统计/报告。
- 新前台总监控session43624覆盖V2/V5/semantic及CPU失败与DLC时限；旧45015/67386也还运行，可在确认新监控后退休旧DSW监控，不能碰DLC节点。VLMprogress脚本已含新runs。semantic后续处理尚未写。
- 旧关键4个去门控方法navtest各seed仅Base<70子集全部4268输出已算完（21340含Base记录）；legacy_ungated_test_accept.py正在session待回收，日志provenance/legacy_ungated_test_accept.log。须保留非失败Base原样的Oracle语义，不能叫无条件全test去门控表现。每方法还需补failure∩benefit Oracle（区别全样本benefit）、兼容面板合并、stable-case和CI，避免将原成功微小增分误认成修复。现legacy_oracle_v2是早期全26面板表，新增去门控与此test需并入。
- 21:39新进度：rapid1970/2272、fullgrid10/2272（均缺失类cell，canonical仍0/62），48CPUworker在重网格中；V2 2352/16224队列仍持续追加。当前完整Cartesian很重，必须按实际完成记录。两节点期限仍03:42:10 UTC，未验证能延长；原始源块/全部输出/claim须留好，临近时清晰断点准备，不主动释放。
- 老动作头报告生成/新VLM与Oracle正式报告整合、视觉/链接/数字验收、最终STATUS/PLAN仍未做。全部任务尚未完成，继续工作。

## 22:08更新（接续务必先读）

- 两节点新阶段等待器已改为V6（Queue6=V5严格tensor去重＋Engine4新语义池alias/投影Haar修正），V6_EQUIVALENCE PASS：原3case×64arms×2seed轨迹/评分/实际编辑全等，额外2case×4位置×2新语义区域非空/实际cap/后缀PASS。REPAIR_EXECUTION_v6冻结。先前V5等待器仅是未加载GPU的辅助等待程序，已核验PID后SIGINT退休；所有DLC主进程/现有GPUworker未动。wait_v6_node0/1 receipt均PASS，仍等旧V2队列完全完成且global PARENT_LOCK存在才加载GPU，继续使用run名vlm_global_refine_20261016_v5。不要同时启动V5原等待器，否则重复worker。
- 新code/vlm_final_driver.py、vlm_final_engineering.py已写并部署在node1等待global FINAL_CANDIDATE_LOCK，FINAL_DRIVER_EXECUTION冻结。它生成global两角色独立reverse+3Haar、组件最佳诊断，训练case真实工程校验后，直接追加同一V6/GLOBAL5 run的final_test（12146×5）与navtrain_locked（103288×3，只global角色）。无需再换GPU程序。尚未触发/真实验证最终父项；需后续监督其工程、最终统计/验收是否正确。source最终统计、显著性/多重比较、图表报告仍待写。
- 新SEM补池DSW rank32持续采，两个节点32个gap collector已部署native cache smoke，合计33卡smoke PASS；DLC状态WAIT_SHARED_GPU正常，不抢正在计算的V2/V6卡。22:01已143/6456块。新语义collector所有代码/两个checkpoint smokes均通过，不改原输出。还有SEM两个字段64cell后续修复必须完成。
- code/vlm_semantic_analysis.py（全103288、64cells、40GB转置与whole-sha）、vlm_semantic_cpu.py（同冻结full/rapid math）已写并py_compile，仅待完整采集后真正工程验收。node0 analysis-controller＋两节点各8rapid/8full CPUworker已部署等待，cpu_node0 session52239、cpu_node1新receipt待poll。模型无需再采除这64错误池之外的任何表征。尚未写SEM竞争候选fit/修复/完整val/锁定test producer，需要用Engine4/Queue6支持的command_v2/requirements_v2。建议在final/PRIMARY_STAGES_APPENDED之后把新SEM coarse/replay追加同一GLOBAL5队列，不挡主测试；比较原同层强候选，以新64池CV稳定效应筛选，再多算子/力度/门控/组合/验证/测试。SEM源cellproof指向SEM/cells，vlm_fits.make显式cell_proof_path支持；vlm_selection.block_candidates(...analysis_root=SEM)支持；这些核心冻结文件别改。
- 旧关键4个去门控test-failure诊断ACCEPTANCE PASS，4268实际失败输出×(4方法+Base)=21340记录，所有fresh Base7项与旧全test bit-exact。非失败完全Base，不能叫无条件去门控政策。
- 旧Oracle扩展29个实际面板全部完成：oracle_extended/INDEX.json，逐方法失败∩有益上限（区别原成功小增分），stable-case any/all、零→90、强增分、sessionCI以及严格同token排序/seed数/7字段Base完全相等面板合并。所有现有3/5seed面板的具体seed列表需审计都是range(N)，避免只凭数量认为相同seed；单seed面板all-seed字段不能称重采样稳定。脚本repair_oracle_extended.py，session27019已完。后续把VLM实际矩阵也做同口径、整合报告。
- 22:01 primary全部62块已冻结310fits，队列coarse378（含68残差补充）；fullgrid canonical16/62已完成、全cells26，48CPUworker，余2154调度保留（不算完成）。完整Cartesian额外搜索非常大，不得假报全覆盖/总任务完成；按实际范围和未完成部分记录。CPU source矩/初期结果可做阶段语义审查，不能只有进程活着。
- 还需准备12小时deadline的可复核重启包，当前共同上限仍03:42:10 UTC，约5h半余量；如未完，保留chunks/claims/原始错误并在平台自动终止后按授权重申请2节点。不能主动释放当前节点，不能假定/承诺无中断延长。新任务启动不重置12h。Root monitor43624仍前台，每分钟watch；旧45015/67386也在跑。


## 22:56 UTC接续更新（优先于以上旧状态）

- **动作头正式报告已完成**：candidate_repair_v1/report_versions/final_v2，REPORT_ACCEPTANCE PASS，保留原15图、新4图，canonical SHA e12b6079f38a38bff7a0fdd08b7e0f794601090d107b084e01c5d8b116cddce3。仅修了图中两个相同角色标签重叠，冻结推理/拟合未改。STATUS/PLAN已更新，不再将旧报告列为待办。整个VLM追加任务仍未完成，不能结束交付。
- 新阶段语义抽查 code/vlm_stage_audit.py PASS：32卡2304记录，种子/轨迹/评分/cap全核验。code/vlm_analysis_audit.py已审查2298份已完成CV结果，6个源表征坐标全类充分统计重算一致；会话划分/有效rank/样本资格/数组SHA等PASS，audits/analysis_20261016T223653.json。后续仅在有新阶段/新结果后按需要复核。
- **新重要观察**：冻结探索代表的留出QDA（r128）较均值差读出更稳。language_20 last32 CV AUC .7684、val .8049、会话内正向比例.897、预设1000家族Holm约.001624；interface_pre text_mean CV .7638、val .8000、会话正向.931、Holm3.686e-05。语言后层S1/S2留出AUC .8049/.8124，会话正向.929/.893；接口.7962/.8054，均.929。仅支持质量关联，未证明可修复；QDA没有r邻域确认，不能叫残差稳定区域。多数均值差方向虽总体AUC .72-.75，但会话内方向不稳。不要将总体可分概括成全部层都稳定。
- code/vlm_readout_report.py已生成两次独立绘图快照；READOUT_REPORT_LATEST指向readout_snapshots/20261016T224257/SUMMARY.json，3张图：分层CV/val、4个均值差留出分布、总体AUROC vs会话稳定/校正p。已看过3号；新快照1/2尚未单独视觉验收，状态PLOTTED_NOT_VISUALLY_ACCEPTED；没有写canonical新VLM章节。最终需要更新快照并审图整合。
- 新全方法Oracle：code/vlm_oracle_all.py首快照115个当时实际完成面板，包含旧29+VLM已完coarse/replay+4个旧去门控test失败诊断，oracle_all/LATEST引用。逐方法实际/失败门控/有益门控/失败且有益均有全部安全与稳定病例账本，按真实seed ID、token顺序和7项Base完全一致才合并。code/vlm_oracle_policy_groups.py把动作头表征、简单轨迹缩放、VLM及总体分开，另加同一病例跨噪声固定方法的Oracle与存在一个方法使所有采样>90的统计，最新ORACLE_POLICY_GROUPS_LATEST。
- 旧test含去门控后：纯动作头表征逐draw失败Oracle +.36815359 PDMS；每病例固定方法+完美失败识别 +.36338436；固定方法且只收有益+.36694774。稳定失败699病例里，同一个实际算子可全5次>90的仅5个（最大pool逐draw同样5）。纯表征全样本有益Oracle+.7310552，含轨迹缩放总体+.8234284/失败专属+.4092067。强制区分原成功微小增分与失败修复。全部为已算算子库诊断，不是可部署成绩。
- CPU调度补充：发现12个canonical未被领取，两个节点现场CPU忙碌29.8%/30.5%、空闲内存约1.46TB，各加8个只抢canonical的CPU worker（每个2线程），code/vlm_core_extra.py，CORE_EXTRA_EXECUTION；ranks48-63，smoke沿冻结core_scan数值参考。两节点launch receipt PASS，GPU/旧程序完全不改。当前full scan共64worker；有些canonical抢完后QUEUE_WAIT正常。恢复主程序未包含extra，届时canonical已完则不用再起。
- **SEM修复生产器目前实际为v3**：code/vlm_semantic_repair_v3.py，node1等待，REPAIR_EXECUTION_v3、repair_controller_v3_launch_receipt PASS。它等64 corrected rapid+full scan全部完成才选候选，并额外保留两种残差构造的等维/非等维，各rank段/QDA/full。支持无活跃候选正常完成、重拟合失败原记录、3650复放、组件组合、去门控val对照、单独真实父项/控制工程验收code/vlm_semantic_engineering.py；不覆盖primary engineering。旧未开始计算的v1/v2辅助等待器已核验PID/cmd并SIGTERM替换，所有DLC主进程/GPU程序均未动。模型收集和数学内核冻结源码未改。
- **VLM最终去门控诊断已另外部署**：code/vlm_ungated_final.py（node1等待，ungated_final_launch_receipt PASS），先依据primary TEST_LOCK的全部带门控父项（含组件诊断）生成保持算子/fit/alpha/cap不变的去门控版本，只实际推理各seed的Base<70集合，5个新兼容stage（final_test_primary_ungated_failures_s0..4）；SEM同理，在其ENGINEERING_PASS与final_test_semantic协议后追加。完成输出final/ungated与SEM/repair/ungated的ACCEPTANCE和全5×12146的failure_gated_scores（非失败定义为Base，**不是无条件去门控政策**）。UNGATED_TEST_EXECUTION在最终选择前冻结。还没触发/实际测试未来父项。代码vlm_oracle_ungated_sources.py在这些完成后汇总新增虚拟面板并正确归类上游；最终必须运行这个入口刷新Oracle，不能只用旧vlm_oracle_all忽略新诊断。
- code/vlm_final_accept.py已写/语法检查，尚无最终数据实际验收：final各32rank；600条原只读入口独立评分（strata按token+seed配对，避免把5seed任务的S1误同S0比较）；fulltrain和val同seed/同ID/7项逐值一致；老test与全train Base逐值一致。写各阶段SCIENTIFIC_ACCEPTANCE，不暗示完整Cartesian/总任务完成。
- code/vlm_postcompute.py CPU-only等待器已在node0部署PASS，primary完成后验收、SEM完成/无候选后再联合stats/Oracle/plots/multiplicity，最后POSTCOMPUTE_REVIEW_READY，仍需智能体审图和报告。**此旧postcomputer不等待新增ungated最终诊断，也只调用旧Oracle入口；若其先完成，仍须等UNGATED_TEST_DIAGNOSTICS_COMPLETE并手动跑vlm_oracle_ungated_sources.py刷新、再交付。** 未自动关队列/释放资源。
- **断点恢复包已准备但未提交/未动节点**：code/vlm_resume.py status只读；必须等两旧作业真实terminal且无Running pod。先运行code/vlm_resume_stage_registry.py（恢复PROTO提交后queue尚未append的稀有中断，并保留归档未提交CPU数组，避免BLAS线程分配变化导致npz精确相等失败），再vlm_resume.py prepare（归档剩余claim、领养完整无receipt结果、重置实际新设备smoke）、submit。prepare见到任何原failure会拒绝，需先复核是否真正科学错误或平台preemption原异常再处理，不能盲清。DSW semantic rank32不归档/重排。
- code/vlm_resume_node.py/master、vlm_resume_launch.sh、vlm_resume_terminal.py已写/语法及3个真实旧结果验证器PASS，RESUME_ENGINEERING，RESUME_EXECUTION（pre-submission修订保留initial）。请求仅在原两job终止后生成，镜像/挂载/配额复用同2×16/720min/Reserved0，新目录不覆盖。续算原V2未完task采用已有严格等价Queue6，不改任何旧结果。原主程序/队列不停止。新resume master重启old/global/scan/core/CPU controllers/SEM gap+CPU+v3 producer/final_driver，**尚未包含后来新增postcompute与ungated_final辅助等待器**：新容器正常后须用新的scoped terminal另起这两个，保留独立launch receipt。新terminalhelper校验resume CLOUD_READY与新request UserCommand，不用旧hardcoded allowlist。
- 活跃foreground：原总监控session43624每分钟API时限/失败/计数；新code/vlm_event_watch.py session90017，每分钟看关键phase标记，新phase/failure/<20min会返回唤醒root；它还硬编码旧03:42:10 deadline，换job后需用独立新监控配置。DSW语义worker28998仍持续工作，不能停止。早期45015/67386只读重复监控尚在跑；无需触碰DLC。
- 最新约22:46：rapid2272全完；full42/2272（部分无效老文本格点计数）、canonical约32/62，CPU64卡外worker；GPU旧V2 5840/28224且producer仍追加。无失败，两个job剩约4.9h，原保守共同期限03:42:10 UTC保持。不保证全部原Cartesian在期限内完成，不能把计划范围冒称实际覆盖，更不能提前结束当前任务。


### 23:06 UTC资源调度试验（新接续必须检查10分钟结果）
- 因64池补采只有DSW连续工作可能赶不上当前时限，在原两节点各物理GPU14/15上增加2个独立native采集实例，与冻结V2共存；没有停/改任何旧GPUworker或主进程，无新增物理卡。code/vlm_semantic_overlap.py，SEM/OVERLAP_EXECUTION在试验前冻结；实际新logical ranks64/65（node0）、66/67（node1）。它仅覆盖原collector idle调度函数，其余冻结模型/池化/atomicclaim/落盘代码完全相同。
- 4实例actual smoke全PASS：两份实际已提交SEM记录的64池逐值完全一致、原生hidden与缓存一致、S0轨迹及全部PDM评分一致；每卡启动前空闲GPU显存约68.14GB。旧V2每任务仍独立断言Base轨迹及评分exact，当前无失败。
- **还不能据此宣称性能收益或扩大。** code/vlm_overlap_measure.py --minutes 10的完整窗口结束为2026-10-16T23:14:31.017314 UTC；到时读取生成SEM/overlap/MEASUREMENT_10min.json，比较原任务输出速率、4张共享卡相对其它28张的归一化吞吐、SEM实际场景速率与截止前能否补完。属观察性比较，阶段/样本混合变化须注明；优先避免明显拖慢原计算。不只看GPU利用率。新增4实例证明的是同33张实际物理卡的37个collector实例，不得写37卡。
- 当前旧foreground43624、event90017不自动扫描SEM/overlap/failures（SEM在VOUT之外）；试验期间root每分钟须另外查该目录及2个overlap节点STATUS/log，任何辅助错误先查原trace，不动主进程。原SEM BASE/failures仍被主监控覆盖。
- 续跑master未包含这4个overlap实例，今后是否重启取决于测量与主任务进度，勿不加判断地重起。若补采已完成则无需任何GPU补采进程。正式CELL转置/CV/repair生产器会自动使用这些同一队列/同一case定义的合法新receipt，6456全覆盖才继续。

23:13：并行补采5–10min阶段实际验收PASS，SEM/overlap/EARLY_AUDIT_20261016T231159.json：只采4个smoke完成之后的原32卡最新时间戳结果（不是任务名字字典序），3936记录和4新实例128个正式场景/64池数据通过，原冻结S0 Base轨迹/评分断言持续有效。code/vlm_overlap_audit.py可复查，后来加了3份execution当前源码SHA再核验。10min性能窗口仍23:14:31结束，不要提前宣布扩容收益。

另已准备code/vlm_integrated_report.py（只语法检查，未执行/未改canonical）。它要求primary/SEM真实科学验收、SEM全部64 full/rapid、62canonical完整、去门控诊断全完成、最新联合统计/Oracle/读图快照后才能构建新正式报告。须先用vlm_oracle_ungated_sources.py刷新包含虚拟面板的Oracle；该新报告生成器尚待真实最终数据调试。最终新的HTML静态/链接/数字/图片验收脚本还未写，需人工审图；旧candidate_report_accept只适用于历史动作头版，勿拿它断言新canonical SHA必须等于旧档案。


### 23:20 UTC最新必读
- 并行补采10min测量完成：SEM/overlap/MEASUREMENT_10min.json；原场景臂输出100.27→97.07/s（原始总速率−3.2%）；4共享卡相对其它28卡归一化比.5307，估计整体−5.9%。SEM2.24→9.12场景/s，剩86648预计9501s（2h38）低于旧节点余16036s。**已采用仅4实例，不扩大GPU共享**，ADOPTION.json。观察性吞吐估计，不能宣称受控严格加速倍数。原冻结worker及源码保持；无新增物理卡，无失败。
- SEM补池完整扫描另加空闲CPU：code/vlm_semantic_cpu_extra.py，CPU_EXTRA_EXECUTION；两节点各16额外worker×2线程，启动receipt PASS但等待ANALYSIS_EXECUTION数据，真正数值smoke尚未触发。原8 full/node不动，新rank16..31/node0、32..47/node1，args workers32只用于owner/node gate（原rank0..15的workers8逻辑不变）；全部共享atomicclaims/同一冻结数学/constant保护。纠正full scan总48workers，rapid仍16。此辅助也不在resume_master，冷重启后若SEM全格点未完且CPU有余量可另起，不能重复起活动进程。
- 新code/vlm_baseline_trajectory_audit.py已写语法检查，未执行（尚无最终VLM数据）：读取旧candidate finaltest全部Base轨迹，核对新primary/SEM全部12146×5×8×3逐坐标bit-exact，超越仅7分项分数相等；保存原轨迹cache及hash，写各BASE_TRAJECTORY_ACCEPTANCE。**old postcompute不会调用它**，root在最终推理完成后必须按study手动跑再构建报告，vlm_integrated_report已强制require此marker。
- 现finalstats的policy_change_rate基于最大平移变化>1e-8m，未包括纯航向改变；新报告已经准确标成“位置变化率/原失败比例”，不将其冒称全三维轨迹精度。PDMS所有效果仍由完整8×3轨迹重新评分，修复/损伤数不受此代理限制。
- 新报告生成器/新的formal HTML最终验收尚未真运行（无最终数据），不能宣称VLM整体完成。需要源图、核心数字、全部链接/无下载检查，保留原19图，canonical在未来新build才更新。


## 23:50 UTC关键新成果与接续项
- 原full canonical已60/62，尚待bridge_pre__patch_mean与bridge_0__patch_mean（4096维重任务），无失败。23:45语义补采2105/6456块，继续4个overlap实例，不再加GPU。估计约01:5x完成，需随实际更新；当前deadline仍03:42:10。
- SEM full CPU并行进一步准备到**64worker**：原16＋cpu_extra32＋新增cpu_wave16（每节点8个，nice10、2线程）。code/vlm_semantic_cpu_wave.py，CPU_WAVE_EXECUTION、两节点receipt均PASS，尚待SEM ANALYSIS_EXECUTION才做实际数据/数值smoke。新增ranks48..55 node0、64..71 node1，workers64用于owner/node gate；与collector逻辑rank64..67在不同目录，别误认为重复GPUworker。冷重启master没有这些辅助，若SEM已完不要重复启动。
- **同读出QDA对照已完成真实CPU计算**：code/vlm_qda_controls_v2.py（v1仅冻结选点/范围、未实际计算；v2避免full-space I矩阵GEMM并准确标source/fit_definition hash）。PROTOCOL、RUN_EXECUTION_v2，两节点_v2_receipt、node_COMPLETE PASS。按原探索CV score选4个固定点：bridge_3 thumbnail_mean、interface_pre text_mean、language_20 last32、vision_23 thumbnail_mean。PCA和3随机空间每r64/96/128/192/256＋fullQDA，共84控制，全部CV及会话留出/S1/S2计算，不改变原修复选择。原PCA128 CV复现PASS，80新增确认文件进入VOUT/confirmation，预设家族1000仍足够（primary310＋residual248＋SEM最多288＋controls80=926）。
- 主要控制观察：interface PCA128 CV/val .7638/.8000，随机128 CV .7470-.7532/val .7922-.7982，full .7204/.7547；language PCA128 .7684/.8049，随机.7582-.7620/.7958-.8069，full .7587/.7923。bridge/vision随机更接近PCA。64→256曲线平滑、128非孤立最佳。这说明可由多个投影读出，**不证明质量信息真实内在维数较大/分散，也不否定低维机制存在，更不能证明特定PCA故障基。** 早先“较分散”的口头表述已在未来报告改成这个更准确解释。
- **新增84探索比较已纳入共同校正**：code/vlm_qda_joint.py会先刷新原vlm_multiple_comparisons，再附84 CV比较做全家族BH/BY；23:44的joint snapshot=vlm_repair_v1/multiplicity/20261016T234407_qda，finite790783，planned54746580（原54746496＋84），heldout630个，Holm仍1000且未来未计算项p1。原PCA128重复计入探索家族是保守处理，非新增病例。每次最终old postcompute刷新原multiplicity后，**必须再运行vlm_qda_joint.py**，新report强制要求最新multiplicity带all_qda_control_sites_complete，防止漏这些新增比较。
- code/vlm_qda_report.py已生成84条完整控制表和CV/heldout两图，qda_controls/REPORT_LATEST指向report_snapshots/20261016T234516。两SVG含4组AUROC/x标签、PNG已核查源文件。view_image重复近似图片时显示怪异/像差分图，尚未标最终视觉验收，最终再看一次实际源图；不要把工具显示差异当数据文件损坏（PIL/SVG可检查）。未来report已准备把这些图、全部84行放折叠部分。
- **与4个固定旧方法的比较已前瞻登记**：PRIOR_REFERENCE_PROTOCOL在任何上游TEST_LOCK前写入，code/vlm_prior_reference_statistics.py（仅语法检查，无最终数据未运行）。对primary/SEM所有去重全局角色，逐一比较legacy_safety_priority、legacy_pdms_priority、scale_1.005、scale_1.02，统一家族Holm；不按测试挑最佳旧参照，含净NC/DAC/zero/TTC差值。最终必须运行此程序，vlm_integrated_report已require PRIOR_REFERENCE_LATEST。
- 新正式报告生成器仍未执行（无最终数据），已经加入QDA完整控制、旧参照比较、Base已训练于原train数据的说明、位置改变代理定义，且强制真trajectory审计与最新joint correction/Oracle。**没有新的报告最终静态/数字/视觉验收器**，还要写。旧动作头canonical仍是已验收e12b...，别误记VLM已完成。
- 后续report/analysis全部计算要遵守链：真实GPU完成→primary/SEM验收（postcompute自动）→去门控诊断完成→vlm_baseline_trajectory_audit.py --study primary/semantic（手动，postcompute不会调用）→vlm_prior_reference_statistics.py→vlm_oracle_ungated_sources.py→vlm_qda_joint.py（在原multiplicity最后一次刷新之后）→vlm_qda_report.py及最新readout图→vlm_integrated_report.py新version→视觉/链接/数字/源hash验收。原readout_report内Holm只对它见到的fit集合、余项p1，较全confirmation更保守；新joint汇总才是完整family口径，最终一致性可用新绘图版本统一。
- 冷续跑master还需现场判断：它无条件启动semantic_gap，若6456已采完应在提交前准备独立v2master跳过这32个无必要模型重载；若PARENT_LOCK已存在且旧V2任务全done，也可跳过旧原GPUactor，仍保留作业main和开放queue。已有旧master功能可恢复，但不能盲重跑已完成模型收集/覆盖launch日志。新增aux（postcompute、ungated、CPUextra/wave等）尚不在master，若需要，用新resume目录独立日志/receipt启动，勿复用“>旧.log”的旧shell脚本覆盖日志。


## 00:15 UTC接续：最新监控、分折备份与冷恢复v2
- 当前实际时间2026-10-17约00:15 UTC；现有两个job仍保留，原保守截止03:42:10，不作stop/release/延时承诺。V2约11532/36352任务、SEM约3102/6456块（producer仍追加）；无实验错误。原node1四个CPU生产器RUNNING。
- 旧event session90017在23:26因递归glob遍历一个正在移动的claims目录FileNotFoundError退出（非实验失败）；新code/vlm_event_watch_v2.py session78492仅扫描明确failures目录，覆盖SEM overlap/cpu_extra/cpu_wave及独立backup异常，有界容忍共享文件系统瞬时错误。总monitor43624仍运行。新event仍以旧03:42:10期限告警，换job后须另设监控。
- 独立CPU备份实际启动PASS：code/vlm_fold_backup_v2.py，VOUT/fold_backup/{node0,node1}_v2_receipt；每节点10worker×4线程,nice10，只有CPU，无旧主进程/旧worker停止或源码修改。15个held-moment任务和10个384维control方向任务已完成；ENGINEERING_PASS 00:09，control=interface_post__valid_mean，状态/rank/evalidx/degen精确，非退化指标maxdiff 1.51e-14/2.46e-14。其后20个4096维方向任务真实计算，BASE=runs/vlm_fold_backup_20261017_v1，原2个whole-cell仍正常算。新错误在provenance/fold_backup_errors（不污染原实验failures），event_v2覆盖。
- code/vlm_fold_backup_adopt.py已写/语法检查，尚未运行：只有两旧job及每个pod在相隔10秒两次查询均明确terminal时允许；既有原结果永远优先（即便仅缺receipt），不按分数挑实现；否则仅领养已通过10方向/原冻结scan聚合的backup结果，数组/moment仍引用独立目录；不覆盖结果，不动claims。原job还活着时不能运行。
- **冷恢复使用独立v2**：先严格quiescence→fold_backup_adopt→vlm_resume_stage_registry_v2.py（归档未提交CPU数组/补冻结stage append）→vlm_resume_v2.py prepare→submit。原v1源码/执行记录保留。RESUME_EXECUTION_v2在00:14 UTC冻结，未提交任何新job；节点总数上限仍2×16。新master code/vlm_resume_node_v2.py可--dry-plan，只恢复未完成阶段；若SEM6456已完跳过32个补采模型重载；若PARENT_LOCK且旧queue排空跳过原V2模型重载；仍保留GLOBAL6队列等待后续。已包含postcompute、ungated_final、SEM原CPU+extra+wave，所有controller主日志放新resume目录append，不使用旧host覆盖LAUNCHED.json。额外SEM node metadata仍是状态快照，旧launch receipt/日志保留。
- 新code/vlm_integrated_report_accept.py已写/语法检查（未有最终数据，未实际执行），核对HTML/图片/旧19图保留、快照hash、核心PDMS/CI/Holm/安全/84QDA数、覆盖范围和必要科学限制，需真实审图后--figures-reviewed。生成器新增snapshot_sha256，仍未构建新canonical；旧动作头final_v2已验收版本不变。整体任务尚未完成。
- 用户最新提速建议是可选参考；不因建议中断冻结任务。已有预取/批回传对照只约1–2%收益，新阶段严格latent去重已验证显著收益；当前不增加评分进程、不再扩GPU共享。按实际吞吐和节点剩余时间判断，优先重计算，不为优化而优化。


00:28 UTC：新增只读维数组合图code/vlm_dimension_report.py，当前snapshot 20261017T002600已生成/实际看完3图（FIGURE_REVIEW）；240个既有冻结残差fit，4个仅按CV挑出的展示代表，固定两项分别扫ks/kf/r、固定r的ks×kf热图、同r等维/非等维包络与PCA/3随机/全维对照。包络两类搜索机会不同，不作公平优越性检验；全部AP/标准化差异/会话稳定性另表，未新拟合或选修复参数、未访问test。当前complete=false，等62canonical与64SEM full完后必须手动python -B code/vlm_dimension_report.py --require-complete刷新并重新看图；老postcompute不会调用它，新integrated_report与accept已强制引用此完整快照。已读到vision17 variance24/4/r4、bridge2 variance16/8/r8、language20 variance4/8/r8在会话留出positive fraction约.793/.828/.793，interface图块代表.517，不能仅凭CV stable标志当确认；未改原冻结选择。当前canonical/SEM仍计算，整体未完成。

00:29补记：当前95个已提交有效full-grid（含early_interface）全部通过独立代数rank边界检查：各折/两中心化residual rank≤min(kf,D−ks)，无合格r超界；audits/rank_bound_20261017T002806.json。复核源码已保存code/vlm_rank_bound_audit.py，最终数据到齐后再跑一次（当前新文件只语法同逻辑，无需重复旧95格点）。完整最后手动链另加vlm_dimension_report.py --require-complete及rank_bound审计；原postcompute不覆盖这两项。

2026-10-17T00:32:12.122357+00:00：独立CPU最终后处理等待器code/vlm_analysis_finalize.py已冻结FINALIZE_ANALYSIS_EXECUTION、node0启动PASS（finalize_analysis_v1/initial_launch_receipt，日志controller_initial.log）。它等旧POSTCOMPUTE_REVIEW_READY、去门控全完成、canonical62和SEMfull64后顺序跑：baseline_trajectory_audit primary/semantic→prior_reference→oracle_ungated_sources（含policy_groups）→qda_joint→qda_report→readout_report→rank_bound_audit→dimension_report --require-complete，最后FINAL_ANALYSES_REVIEW_READY。每步append日志和不可重复step receipt，不构建报告、不关队列、不释放。原postcompute不改。冷续跑v2master尚不包含这个新aux，届时用新resume scoped terminal另启一次（新日志名，保留旧记录；先查是否已ready/有活动锁，勿双起）。这是替代之前必需手动链的自动接续，仍要人工审图/构建验收正式报告。
基线轨迹新审计（尚无最终数据未运行）使用JSON原数值的float64精确比较，防止float32转换掩盖差别；旧样本实查本来就可float32精确表示。当前缓存不存在，未改任何旧输出。最终仅允许匹配raw坐标，科学marker还要实际跑后才能PASS。

2026-10-17T00:37:39.227996+00:00：重要调度纠正：现场按workers task核实，原32个full主worker全部在4096维（bridge_pre/bridge0）任务，而32个canonical辅助已空闲；另有60个由既有冻结scheduler释放但无人领取的低维任务（1536维34、1024维25、384维1）。已追加code/vlm_scan_spare.py，SPARE_SCAN_EXECUTION事前冻结，两节点initial_receipt PASS，每节点16个CPUworker×2线程nice10，disjoint ranks80..95/node0、128..143/node1；仅从原tasks按atomic claims领取已释放且D≤1536格点，不新设科学比较、不动原32重任务/主进程/模型/结果。它调用原numeric_smoke和scan不改数学，全部32新rank真numeric smoke PASS，现有活跃D=4096:32/1024:25/1536:6/384:1。约00:43前后应做5–10分钟实际资源/进度检查。新CPU异常写原VOUT/failures，event_v2会唤醒。原GPU和SEM继续，仍无失败。
已完成canonical辅助CPU全网格耗时实测：1024维median1507秒(n25)、1536维median2929秒(n34)、384维66秒(n1)，均2线程；4096仍无完成可用实测，不能按小维度简单承诺时长。增加spare是利用当前空闲CPU扩大原定完整格点覆盖，并非修改冻结实验。冷resume_v2 master尚不含spare，后续按任务剩余和CPU状态用新scoped terminal独立启（原PREFLIGHT等先归档，日志用新名字或append；别覆盖旧launch日志）。全部token完整Cartesian仍未完成，报告必须区分rapid全覆盖与full实际覆盖。

2026-10-17T00:42:40.918857+00:00：spare CPU启动后约6分钟实际检查PASS，scan_spare/node0_early_runtime_receipt与node1同名记录。32worker CPU时间全前进，3个已落盘结果source/config/class sizes按协议验收；CPU45.3%/46.2%，RAM可用约1315/1316GiB，无资源不足。审计code/vlm_spare_runtime_audit.py，scan_spare/audits两个时间戳JSON。接下来继续监控，无其它干预，仍保留两节点。

2026-10-17T00:54:30.095978+00:00：新增code/vlm_live_watch.py动态前台监控，已--once对真实两job只读验收PASS（两者Running，余2.8h）。用--cloud-ready指定old candidate CLOUD_READY或新的resume/CLOUD_READY，从实际API GmtCreateTime+MaxMinutes算deadline（不再硬编码03:42）；每分钟进度/失败/phase/20min告警返回唤醒，不stop/release。冷续跑后用 python -B code/vlm_live_watch.py --cloud-ready <resume>/CLOUD_READY.json，旧monitor43624与event78492在旧时限下不可用于新时限；需要等旧作业真实终止时可用--warn-minutes 0继续只读等。当前保留原监控未换，新增程序只--once未启动第二个长循环。
报告生成器继续只准备未构建：新增全部冻结残差候选的真实联合Holm列，并明确跨S1/S2检验的是固定VLM读出与行为质量关联，非表征本身不变；限定原S0极端队列口径。finalize源文件冻结不变，只有尚未执行的report builder改动。正式canonical仍e12b...旧已验收版本。

2026-10-17T01:02:11.174256+00:00：已把独立checkpoint池复用至**两个**原未完4096维任务bridge_0__grid_00/grid_01（按任务名排序取前2，非按CV/结果挑选），EXTENSION_PROTOCOL事前冻结，code/vlm_fold_backup_extension.py。源数组SHA核对通过，原主worker继续，原pool20个CPUworker源码/进程/核函数未改，无新GPU/节点；10 held任务已追加到同BASE，后续20direction仅由独立extension controller追加；输出仍fold_backup独立目录。核心ALl_BACKUPS_COMPLETE只指原3cell scope，新2cell另用EXTENSION_COMPLETE，不要误读总数。controller scoped launch receipt=fold_backup/extension_initial_receipt，正在回收确认。新code/vlm_fold_backup_adopt_v2.py把可用的额外2cell也纳入事后领养，仍只在两旧job+pod明确terminal后、原提交结果永远优先，不按分数选实现；EXTENSION_ADOPTION_CODE保存SHA。**冷接续入口先用adopt_v2替代旧adopt_v1，再registry_v2→resume_v2 prepare/submit**。若新2cell只部分checkpoint，则先保留原分片，不让未验收分片冒充完整扫描；现冷master未包含这些aux，不盲重复起controller/worker。

2026-10-17T01:12:01.121301+00:00：**核心checkpoint全完成并真验收PASS**：ALL_BACKUPS_COMPLETE 01:09:53（scope仅control384＋2个canonical4096），code/vlm_fold_backup_validate.py已实际运行，audits/data_validation_20261017T011057：3cell全部充分统计与原正在跑的scan/moments**逐值bit-exact**，数组/矩/SHA、概率指标及rank≤min(kf,D−ks)、可用r边界全部PASS。原结果与原进程未改/未停止；原canonical仍60/62，不可把独立backup算作原receipt。可在旧jobs真正终止后按adopt_v2复用，原已提交结果总是优先。extra grid00/01仍在独立checkpoint计算，不能把核心3cell完成当额外2cell完成；后者EXTENSION_COMPLETE。event_v2 session78492已因正确phase唤醒退出0；原总监控43624仍活跃。准备切到已验证动态live_watch（后续查STATUS实际session）。

2026-10-17T01:34:16.758952+00:00：独立64池cache验收器code/vlm_semantic_cache_accept.py已node0部署PASS（SEM/cache_accept_initial_receipt，日志cache_accept_initial.log），只在CACHE_COMPLETE后运行：所有64文件whole SHA/shape/float32/全finite/常量性，按每个实际producer rank取首尾块，检查对应global_indices/token以及每样本所有64池逐值等于源块。源码在CACHE_ACCEPT_EXECUTION事前冻结于数据到齐前，当前尚无cache故无实际data PASS。新报告将强制CACHE_ACCEPTANCE，原采集/转置/CPU分析均不改，不等此验收器才启动后续（已实际smoke的程序自动接续）。冷续跑若该验收尚未结束，可同逻辑新日志再起；通常应早于旧job截止完成。

2026-10-17T01:56:46.506560+00:00：**SEM补采/缓存及独立验收全部PASS，真实CPU分析已启动**。6456/6456、103288案例；CACHE_COMPLETE 01:45:58、ANALYSIS_EXECUTION 01:45:59，64池、6456源文件SHA全部由转置核对；独立CACHE_ACCEPTANCE核对所有64文件哈希/形状/float32/finite、5实际producer[32,64..67]共152样本×64池全值等源，PASS。元数据不含后来加的constant标记（旧等待controller已加载较早格式），不改旧cache，扫描独立逐行constant fallback正常；唯一静态language_input__requirements_v2被INELIGIBLE排除，QA也确认。实际rapid16/full64 CPU numeric smokes全PASS，CPU extra/wave两节点SMOKE_PASS全有；rapid64/64（63COMPLETE+1静态），full4/64（3COMPLETE+1静态）。EARLY_ANALYSIS_ACCEPTANCE已新起阶段数据验收PASS，source/class sizes/所有已完成数组/矩SHA核对。后续full继续、SEM v3仍等64full。
资源snapshot_v2两节点CPU63.0%/62.8%，176affinity，RAM可用1318/1317GiB，无过载；首次只读资源命令缺少sys.path=code导致common导入失败，已保留v1 receipt，用独立v2显式路径解决；这不是实验失败，不动环境/主进程。
动态watch session20002已因CACHE+ANALYSIS阶段正确返回0，当前新动态前台session**1306**；旧43624总监控仍在。下一处人工检查full阶段（约2:00后/每10分钟），全部full64结束要检查结果；v1 watch未直接对SEM full64计数发phase，但latest.json存semantic_full_completed，不能只等后续修复FINAL_LOCK。


2026-10-17T02:15:03.606756+00:00：额外两格点checkpoint EXTENSION_COMPLETE 02:08:22，code/vlm_fold_backup_validate.py 对全部5cell再次实际PASS，audits/data_validation_20261017T021409.json，充分统计与原局部moments bit-exact、rank/r/概率/SHA均合格，仍未领养/不动活跃原结果。独立fast_space原型384D数值通过，但缺同环境吞吐收益，DECISION=NOT_ADOPTED；不消耗剩余节点时限继续优化。原live_watch PID3868517活跃但旧session不可复连，新增code/vlm_foreground_follow.py只读其latest并按1min轮询/10min或新phase唤醒root，不触碰DLC主程序。当前GPU22488/38720、SEMfull4/64、原full175/2272，两个原job截止03:42:10不变。


2026-10-17T02:22:26.661629+00:00：code/vlm_recent_stage_audit.py 实际PASS，audits/recent_stage_20261017T022046.json，按真实文件mtime取每个rank最近已提交结果（非任务名排序），全部32rank的seed/8x3轨迹/score/quality/实际cap检查，并与旧全train Base七项评分逐值一致。原REPAIR_STAGE_AUDIT未覆盖，新增独立时间戳记录。当前所有上游粗筛算子均为gate=none，故这些原始面板的failure-only Oracle确实测去识别限制的算子能力；后续带门控全局候选仍按既定vml_ungated_final补诊断。


2026-10-17T02:33:59.014934+00:00：**冷续跑入口现为v3，覆盖旧v2入口**。02:30原global V5等待器递归glob撞上scheduler正常移除scan/claims/vision_01__cls_mean，FileNotFoundError；原异常/原日志SHA已归档controller_recovery_v1，科学输出无故障。只精确退休辅助CPU observer父PID40811（非DLC主/GPU），原residual40815、schedule40817原进程及32GPU未停。global_v6 PID57079只是固定错误目录轮询，原V5数值/候选/种子/门控/阶段函数全部不改；现ENGINEERING_PASS对真实已完stage摘要逐值相同，RECOVERED/STATUS真实PASS。旧controllers/node1/STATUS为保留旧快照FAILED，现以controller_recovery_v1/STATUS为准，原failure已归档且当前errors()空。
新RESUME_EXECUTION_v3冻结未提交：code/vlm_resume_v3.py prepare/submit，node/launch_v3使用global_v6，并包含原32个spare CPU与analysis_finalize；prepare在旧job/pod真终止后额外归档旧scan_spare/node{0,1}，避免覆旧辅助preflight/log。其余strict quiescence→validate→adopt_v2→registry_v2顺序不变；两个dry-plan实际PASS。不要再用旧v2 master重新启动有glob竞态的global_v5。
原livewatch在failure正确退出，新前台session**81120**真实Running，2:33两job各余1.15h，GPU23980/39104、SEM6456齐；primaryfull约200，SEMfull4。DSW增量Oracle仅缓存新294个已经完成真实面板的逐方法上限（progress_refresh/derived_20261017T023039.json），未合并新测试/选择参数、未改已有panel或最终LATEST，终局仍需全量刷新。新CPU原型NOT_ADOPTED，不再做优化。

2026-10-17T02:38:42.216263+00:00：恢复5–10min实际检查PASS：controller_recovery_v1/node{0,1}_runtime_20261017T023756.json，原32个GPUworker PID与create_time均保持19:24–19:25原进程，node1原residual/scheduler及新global均活；CPU60.3%/57.3%、可用内存各约1.3TiB，无新失败。两份scoped terminal receipt PASS，不能把旧controllers/node1/STATUS的历史FAILED当作仍未恢复。

2026-10-17T02:54:52.302756+00:00：SEM64/64完整网格已齐（63COMPLETE＋唯一静态language_input requirements排除），同时rapid64齐。独立验收**vlm_semantic_full_accept_v2.py**实际128结果全PASS，FULL_ANALYSIS_ACCEPTANCE_LATEST→audits/full_cv_20261017T025207，逐结果/数组/矩SHA、训练类74900/1850、会话折/极端资格、AUROC/AP/p范围及代数rank/r边界通过。v1 QA误把64进程当连续0..63，原冻结实际是0..55＋64..71；只校正独立验收器v2，保留v1源码与engineering_note，不影响科学实验。正式report builder现强制引用这份全64结果独立验收（未构建report）。SEM v3生产器已自动开始，2:52真实32fits/6blocks，无rejected_fits或全局failure；待旧PRIMARY_STAGES_APPENDED后追加GPU阶段。

2026-10-17T02:57:26.869262+00:00：SEM64全完成释放大量CPU后，仅在node0追加独立fast_space_probe_v2，同一4096D cell/center/fold用原算法和compact原型**同时各4CPU线程**计时，已冻结EXECUTION、scoped launch receipt PASS，两个nohup PID在各original.pid/compact.pid。新runner v2先核对全部非退化归一化方向(1e-6)、rank/status/center/degen及128真实源行投影；原始V1 DSW小维比较不可用于速度结论，保持原NOT_ADOPTED。新实验/旧扫描/模型未改。约03:01–03:05作5–10min进程/资源检查，之后每10min或结果文件变化核查provenance/fast_space_probe_v2_errors；主live_watch不扫描该可选错误目录。03:37仍不完只可精确停止这两个自有CPU probe，不停任何DLC主/GPU程序；不完整probe不恢复、不自动采用。当前原基线参考为相同node的历史4线程2153s，真正速度结论优先本轮并发原算法对照，不据历史拥塞比率宣称加速。

2026-10-17T03:37:44.079963+00:00：同机CPU benchmark已双完成，未停任何进程。original directions2211.17s、compact1973.30s（内核耗时减少10.76%，1.1205x），同hostname/输入/参考hash，非退化方向最大相对误差8.52e-13且所有rank/status/center/degen exact、128真实行投影合格。**fast_space_probe_v2/DECISION=NOT_ADOPTED**；未测完整cell/场景吞吐，不为约11%内核收益引入新数学版本，采用准备好的空闲CPU并发调度更直接。所有新旧scanner/inference数学保持，optional errors无。


2026-10-17T03:58:55.610798+00:00 **资源与当前接续覆盖前文旧IDs/时限**：旧dlcmi53bf3ah2c2s/dlcms4op7agqj50d由system按上限Stopped（node1约03:44、node0约03:46），pods皆Stopped及两次quiescence实际PASS，lifetime/platform_terminal_20261017T034744.json，root未StopJob。验证backup5cell后，adopt_v2发现2canonical原结果已临终前提交，严格保留原结果；仅额外grid00/01备份领养。原4096两个canonical vs独立checkpoint全10折/pooled非退化指标与secondary **差0**、status/rank/indices/degen exact，fold_backup/audits/original_4096_compare_20261017T035021。release_remaining_grids_v2已在旧均终止后实际释放原1895held scope，registry_v2归档未提交CPU数组后，resume_v3 prepare/submit完成，所有已完成结果保留，oldGPU32与CPU62未完claim重排。
**新2nodes**：dlcu6ibrfm98a7nh / dlcughx571mkmu6x，resume目录vlm_repair_v1/resume/20261017T035006，03:52:13提交、03:53双Running、03:53:52真实preflight各16PPU/176CPU/1.8TB/共享资产RO/版本SHA通过；全32 fresh GPU smoke 03:54:46 PASS（含native/cache、62zero、Base轨迹/七分评分）。新master_v3已含spare CPU及analysis_finalize，无需再单独双启。新动态前台**session68490**，必须带这个新CLOUD_READY；旧session28378/77222皆旧时限/旧作业不要再用。保守新创建+720min截止约2026-10-17 15:52:11 UTC，Reserved0，未承诺原地延长。旧平台实际终止接近RunningTime+12h，仅作事件证据，未来仍保守计时。
已在fresh32 smoke之后启动CPU wave0（48/node）两端scoped receipt PASS，resume/cpu_wave/node{0,1}_wave0/{PREFLIGHT,SMOKE_PASS,STATUS}，96新数值smoke全部PASS、启动CPU36.1/35.4%。原32/node继续，当前共80CPU workers/node。约**04:00–04:05必须5–10min语义/资源/GPU吞吐检查**再决定wave1（每node24）/wave2（再24），不盲追128/node，实际source/maths不改。目录在新resume下，无旧输出覆盖。新jobs已Running且无需排队，这个事实现场核查通过。
SEM243 CPU fits及confirm全SHA/ID/spec/source核验完，SEM/repair/FITS_READY，32blocks、243spec=243fit、无rejected；主/SEM修复尚未完成。Probability字段126个非静态rapid/full实际额外全PASS，SEM/audits/probability_fields_20261017T032305（含AUC/AP/会话正向比/p/prev）。fast_space_v2原/compact均完整数值PASS，同机内核2211.17→1973.30s减少10.76%，DECISION NOT_ADOPTED；不要继续该优化、不要改当前数学。
后续仍按late protocol_v2（978<=1000）与LATE_TOKEN_SELECTION_IMPLEMENTATION：全部原full网格结束后在完整数组所有eligible residual config筛新区域，而不是仅旧shortlist；对未保存S1/S2读出的候选用已有cache、原geometry懒重构5折方向，先核对S0与原数组，再在同原S0极端队列/IPW口径检验S1/S2；不重跑模型。最多48新fit、第三独立补充批次（仍是上游路线一），源代码尚需准备。最终两研究postcompute/报告builder不足以宣称全部任务完；补充批次结束或无新竞争候选之后再完整统一报告。


2026-10-17T04:11:46.601461+00:00 **最新运行约定**：active foreground改为**session27595，code/vlm_live_watch_v2.py --cloud-ready vlm_repair_v1/resume/20261017T035006/CLOUD_READY.json**。新latest=vlm_repair_v1/live_watch/db168b08316b9dba_latest.json，实际两个创建+720min deadline都是15:52:13UTC（更新此前11秒估计）。新GPU5–10min真实审计3712条全32rank PASS，audits/recent_stage_20261017T040108，最早receipt4:00:37均来自新node，Base7分项/种子/轨迹/quality/cap精确；队列继续，4:11GPU32129/41472、原full约309。
第一批CPUwave0各48（加原32/node→80/node）全部实际numeric PASS。node0 4:01已验证2个新完整结果与source/array/momentSHA/class，CPU71.1%、RAM约1.5TiB；node1所分配全是慢任务，4:03验证2个真实已完成充分统计(ns/nf=74900/1850、shape/finite/SHA)、48原进程+numeric通过，完整wave输出尚未到不能声称已验收完成结果；CPU78.9%。其最初只读QA要求5min已有full结果失败仅因任务时长，保留receipt，v2明确running-moment scope。
**一次已恢复的辅助状态错误，别当未解决科学错误**：node0观测CPU67.5%后尝试wave1，实际父预检升到78.8%，v1以assert拒绝（没有任何wave1子worker启动），却把正常resource deferral写VOUT/failures，global_v6等待器随之退出。code/vlm_scan_wave_v2.py＋SCAN_WAVE_EXECUTION_v2今后预检超阈值只写独立launch/DEFERRED并exit0，不能再用v1启动后两批，阈值没放宽。原VOUT2异常及日志归档在新resume/global_recovery_v1/CAUSE；未停止/修改DLC master，原failed childPID15仍被master写在node1/failures/global.json是**保留的历史失败**。新code/vlm_cold_global_recovery.py在node1另起相同冻结global_v6 **PID6807**，STATUS每15s真实心跳，原主/GPU/CPU进程保留。RESOLVED_FAILURES.json以原PID/rc/logSHA精确签名并要求新进程心跳fresh才承认恢复，code/vlm_failure_resolution.py；新watch_v2只对这个精确已恢复旧标记免重复报警，其他异常仍唤醒。新master node1/STATUS原global显示FAILED仍是历史，不要因此杀或重启master，也不要用旧watch_v1。
目前不再加CPU后两波，先看真实负载和首批完整输出；若后续稳定有余量，使用**vlm_scan_wave_v2.py**、全新launch目录以及新receipt重试，不覆盖旧wave1失败记录。CPU0/1各80进程已经在忙，32GPU也忙；不盲追名义并发。
