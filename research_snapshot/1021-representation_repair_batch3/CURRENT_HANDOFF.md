# 第三批执行接续

## 当前优先执行覆盖（2026-10-21；先读本段）

首版42的完整navtrain103288与navtest12146、1882630条共享旧记录精确复核及首版R2等教师快照均已完成，正式证据为两份`analysis/first42_*/SUMMARY.json`和`teachers/first42_v1/FROZEN.json`。其他3762成型身份／123包全部DSW工程通过，48实际设备4模型同卡最大包压力／金标通过，首成型包全量只完成部分分片，结果和独立CPU审计均保留。

用户随后要求**现有三节点先分别完成第四批H/T/HT首轮蒸馏重计算，再回第三批**；已在12:30 UTC启动5epoch正式训练。当前3节点各16训练rank；原192个Base服务在`r3_priority_multiplexer_v1.py`中保留等待，禁止停止。仅本组`../1021-representation_distillation_batch4/runs/GROUP_COMPUTE_COMPLETE_G.json`出现后回第三批。新获得节点直接用于第三批。原`ELASTIC_STAGE_QUEUE.json`保持两个成型stage开放，测试仍需对应训练验收；并未放弃原任务。当前唯一工具托管监控终端**66379**位于第四批，代码`d4_train_wait_v7.py`，同时监控新Running、异常、临期与训练／评价阶段。完整当前入口见第四批`CURRENT_HANDOFF.md`和`STATUS.json`。

两替补`dlc1ng7aizi7oi5p`、`dlc1pfltsbob3ov1`仍排队。不要恢复已Stopped的B2/self0/self1，不关闭队列、不释放节点。下文旧状态均属历史，不据其“未冻结／未启动”重复启动42或旧监控。第三批下一步仍需成型包CPU合并验收、实时最优清单汇总、宽搜预筛扩库与最后GT逐场景优化，均未完成。

## 当前有效状态（2026-10-21；下文旧时点仅作历史）

- 首42全navtrain的103288场景、51644分片已计算并独立CPU审计、合并验收。合并训练＋验证：Base94.878950；R1=96.127691（+1.248740），R2=96.116118（+1.237167），R3=95.953770（相对后两次Base+1.070413）。`analysis/first42_navtrain_v1/SUMMARY.json`为准。其余成型库、宽搜、GT优化尚未计入。
- 首42完整冻结navtest正在运行，12146场景、6073分片、五采样。早期阶段4.8场景/秒、192worker、0失败，`FIRST42_FULL_NAVTEST_EARLY_PHASE.json`。主监控工具终端**67743**，`r3_work_wait_v7.py --stage first42_navtest_v1`，60秒脚本检查，完成／异常／异步工程／新节点事件才唤醒智能体。不是频繁人工检查。
- 全测试旧存档参照已准备完成：`provenance/test_shared_reference_v1/PACK.json`。测试合并后运行`r3_test_shared_reference_v1.py --verify-stage first42_navtest_v1`，要求31共享定义×5×12146轨迹／评分精确一致。此前工程2场景310记录已完全相同。
- 全测试和审计完成后：先`r3_finish42_v1.py --stage first42_navtest_v1`，完整旧共享参照验证，再仅一次`r3_freeze_first42_teacher_v1.py`。目前快照未冻结。之后才正式扩库。
- DSW工具终端**80928**：`r3_formed_pack_engineering_v1.py`逐包工程，123包／3762成型身份，两个固定训练场景、五噪声，独立CPU审计，绝不按收益筛掉成型候选。成功／异常由v7的`resources/ASYNC_WATCHES.json`唤醒。未完成前不能宣布全3762已经准入。
- 通用运行时48实际设备工程已通过15840记录、240实际H与独立CPU审计，`FORMED_RUNTIME_MULTI_DEVICE_ADMISSION.json`。首42H跨噪声统计也完成：R1有16479场景H不一致；R2全部103288场景H一致、92319场景五次均>90；仅适用于当前上游42库。
- 新准备但**未部署**：`r3_stage_service_v1.py`、`r3_enqueue_formed_stages_v1.py`、`r3_stage_auditor_v1.py`。压缩式SPEC+可追加stage队列避免生成数百万重复任务JSON；每分片落盘边界领取下一可用阶段，测试须训练显式验收。12个CPU进程、215个索引的并发去重／依赖锁／失败跳过合同已通过，`runs/stage_service_contract_v1/PASS.json`。尚未创建正式`ELASTIC_STAGE_QUEUE.json`、尚未追加其常驻leases。
- 三Running节点/48卡、192常驻模型保持；另两节点排队。用户Stopped的旧B2/self0/self1不恢复；不关闭队列、不释放节点。新节点只在监控事件到达后现场preflight/准入。机械等待继续工具托管，不以启动监控后结束会话替代等待。

当前任务：按用户已确认的PLAN完成离线教师候选库与三口径上限，不启动学生训练。所有计算仍在执行，不能据工程通过宣布正式结果完成。

## 正式计算与监控

- 首版42条目（40个实际执行定义）正在跑完整navtrain：103,288场景＝85,813探索＋17,475验证，每场景S0～S4。`runs/first42_navtrain_v1`；51,644个两场景科学分片。
- 冻结执行器`r3_first42_rollout_v2.py` SHA `5a95411d707a296a92e8e8fd4f63d7c23fb4eac6bae564be4395b179366b5006`。工作清单SHA `4f12a88693663b40e7f686828ef7556150a2d8dd3b91b62a6626d96c6fe0d808`；42候选清单SHA `6ebc7bb74eabd7549fead47e040163bae086645ee693015d78ff9f186d5e3da8`。
- 2026-10-21 05:30Z阶段验收：48物理卡、192常驻模型（每卡4），22,614场景／4,748,940条输出已提交，近期约4.833场景/秒，无计算／CPU审计失败；不是全量完成。见`provenance/EXTRA_GROUP_V4_PHASE_ACCEPTANCE.json`。
- 监控终端**81654**：`python3 -B code/r3_work_wait_v6.py --stage first42_navtrain_v1`。60秒机械轮询，仅完成、异常、新Running节点、源过期、长时工作项、节点临期等事件唤醒。后续保持工具托管等待，不手工定时查进度。
- 三节点各2个CPU审计进程流式验收分片，见stage的`audit_v1/`。正式完成后先确认全部审计，再调用`r3_finish42_v1.py`，主结果为训练＋验证合并总体，另列两子集。
- 完整训练验收后，先测试工程检查，再按`FIRST42_TEST_LOCK.json`冻结范围完成12,146测试五采样及独立Base对照；随后只调用一次`r3_freeze_first42_teacher_v1.py`生成首版42快照。测试、首版快照目前均未开始。

## 资源与并发

实际Running节点以`resources/REGISTRY.json`及第二批`resources/CLOUD_LATEST.json`为准：replacement_a1/dlclfqx3fyywxyw3、replacement_a2/dlcsdgrnvcu5fbrw、replacement_self0/dlc156fgujiqhoj5，各16张PPU-ZW810E。待入列：dlc1ng7aizi7oi5p、dlc1pfltsbob3ov1。保留全部授权节点和队列，不主动释放；不恢复用户已停止的B2、self_0、self_1。

并发已依次实测：2模型较1模型同卡约1.73倍；3较2约1.26倍；4较3单卡约1.154倍、A2整节点约1.150倍，另两节点整体验收约1.130倍。全部新增模型通过42×5金标，实际轨迹／评分／接口完全一致。当前保留4；不做第五进程试验。

lane1/2程序为`r3_extra_worker_v1.py`，lane3为独立`r3_extra_worker_v2.py`，支持在其工程目录写DRAIN.json后于科学分片落盘边界自然退出；仅限确有回退必要时使用，不用于释放节点。它通过`r3_first42_driver_v2.py`复用同一冻结科学执行器。原始主worker与48卡科学数据未改。outer leases仅追加至512，支持后续弹性接入。

新节点Running后先调用真实容器preflight，准备了`r3_register_ready_node_v1.py`：核对状态、实际设备和持久化挂载来源，再注册ROOT3并仅追加已授权的BATCH2兼容派单槽。该helper尚未执行。之后用`r3_phase_wait_v1.py`等等待原始16卡工程，通过`r3_accept_node_v1.py`后再扩额外lane；每一lane仍须first42金标。不得只改注册表就称多卡准入。

原控制面位置由第二批`runs/discovery_v1/control_plane/LIVE.json`定位；旧97控制器保留，不重启已停止旧节点的worker。节点72小时运行上限不因内部换程序重置。

## 后续已准备，尚未正式扩库

- 原库存195,148项包含网格、CV与中间检查点，不是同等数量的已形成专家。元数据源保留，不逐点交叉全量。
- `FORMED_CATALOG_DRAFT_V3.json`：3762个成型身份；17动作头／后处理、26第一批上游、458 learned、161 analytic、317 delta、948 hard、649 candidate、839 joint、3 finite、344 token。保留独立fit路径／训练任务身份，旧包装和同倍率缩放仅合并别名。6179显式＋14派生资产已核对，`FORMED_V3_ASSET_REVIEW.json`，不是运行准入。
- `FORMED_SCHEDULE_DRAFT_V1.json`：123个草稿包，共享原始专家、每个成型身份全量覆盖一次；未按U收益淘汰成型候选。10970头部采样/场景是含重复及全部joint激活的保守上界，须真实分类计时后估算工时。
- `r3_formed_scene_v2.py`：共享场景自然前向、原始专家；硬选择保留实际分支轨迹与H；联合软干预实际经过原网络。缓存fit有界持久化，相同实际weights／strength才复用joint条件。
- `r3_inference_cache_v2.py`只允许无梯度、输入／输出版本未变的场景；禁止GT优化使用。当前冻结42程序未使用该缓存。
- DSW单卡（实测8CPU／约50GB主存／1张100GB PPU）完成330输出对照：6类完整策略与原始第二批评价器轨迹／评分一致，21个旧动作头／后处理定义与原续采样一致，缓存前后实际轨迹与H逐位一致。`FORMED_V2_SINGLE_DSW_ENGINEERING_REVIEW.json`。
- `r3_formed_rollout_v1.py`准备了输入预取、评分流水、紧凑分支NPZ、first42全五噪声Base对照、竞争性实际教师H保存。DSW集成330输出＋5个真实教师接口通过；独立CPU审计为`FORMED_GENERIC_DSW_CPU_AUDIT.json`。`r3_formed_integration_v1.py`可复用为后续多卡工程。仍须多卡准入、代码冻结、训练侧分批计划和各批测试锁；尚未正式追加任何扩库科学工作。
- 当前无DSW工程计算在途；旧工程终端10825／31656／85574均已结束，不再等待它们。

## 科学规则与后续顺序

先42全训练／验证→冻结测试→首版教师快照；之后其他成型专家／完整策略分批全量，再训练／开发侧宽搜晋级扩库；逐场景GT辅助优化最后。后续只更新实时最优清单，除用户要求不再冻结快照。原始结果及来源全部保留。

不设<70才修复门槛，不设额外安全选优。R1逐采样、R2五次固定完整候选、R3前三选后两评，后两次下降保留。所有tie-break与R3准入也只读前三；后两次不能反向调整。轨迹与H必须同一实际执行，动作头修复的VLM接口可能仍是Base，需如实标记。

宽搜池U1（任次逐采样Oracle<90）与U2（场景固定五次平均Oracle<90）并集，两者不冗余；详见PLAN4.3反例。至少一个训练／开发场景、任一种口径可信复现改善可晋级，不设整体均值或场景比例限制。R3另建仅前三噪声的池及晋级证据；五次晋级不自动准入R3。既定成型候选不受U预筛限制。

首版旧错误与无效计时草稿均保留：首次阶段计时误把路径长度当场景数的INVALID草稿不能引用；V3/V4测量脚本的contained-chunk rate是窗口内完整分片下界，不能当全局提交吞吐。以V4_PHASE_ACCEPTANCE的实际完成时间计数为准。

后续CPU分析已准备`r3_first42_teacher_consistency_v1.py`：完整验收后统计R1／R2／R3五噪声所选实际接口的字节一致性，不平均H、不改选择、不生成快照。新节点兼容注册helper已按三节点真实CPFS来源校验，剥离每容器不同的rund句柄后仍严格核对持久化路径；未执行节点接入。

2026-10-21 10:17Z转换：首42全navtrain已完成51,644分片、全部独立CPU审计和最终合并，`analysis/first42_navtrain_v1/SUMMARY.json`及stage AGENT_ACCEPTANCE为准。合并主Base94.878950，R1=96.127691（+1.248740），R2=96.116118（+1.237167），R3=95.953770（对后两次Base+1.070413）。U并集10945，U2_only10。
冻结测试2场景420输出验收通过，且Base＋30共享专家310条与旧独立存档五噪声轨迹／评分／种子完全相同。正式`runs/first42_navtest_v1`现已启动12,146场景×42×5；主监控工具终端78542，v6 --check-after420，等早期阶段检查后换v7（已准备，加入ASYNC_WATCHES机械事件）。三个节点各2CPU测试审计进程已启动，旧主控及队列仍保留。
新通用执行器在48实际卡完成15840记录、240个实际H目标对照及独立CPU审计，`FORMED_RUNTIME_MULTI_DEVICE_ADMISSION.json`已生成；不是3762配置逐项通过。借CPU合并窗口完成，未修改冻结42源码／清单。
DSW辅助工程任务：终端80928执行`r3_formed_pack_engineering_v1.py`，持久化一个模型＋2评分进程依次核对123包／3762身份，两固定训练样本、五噪声、纯工程且不按收益筛任何候选，不是全量扩库。产出`configs/formed_packs_v1/`和`runs/formed_pack_engineering_v1/`，成功或失败由v7 watches唤醒。另有CPU终端87500做已验收全训练的实际H跨噪声身份统计；成功文件亦在watches中。

测试早期检查已触发并处理，证据`FIRST42_FULL_NAVTEST_EARLY_PHASE.json`。主监控当前终端67743：v7 stage first42_navtest_v1，无定时人工检查，ASYNC_WATCHES一并监控DSW3762身份工程。CPU终端87500已完成H一致性：R1有16479/103288场景五噪声选出不同接口；R2全103288场景接口逐位一致，其中92319场景五次PDMS均>90。仅当前42上游固定方法库的事实，不推广到后续条件化策略。
`r3_test_shared_reference_v1.py --prepare`工具终端28312：从旧完整独立测试存档解析Base+30共享专家五噪声轨迹／按名称评分为验证参照，不修改候选，不产生新教师。完成后全测试合并再`--verify-stage first42_navtest_v1`，要求31×5×12146逐条完全相同；工程2场景已310记录精确相同。
