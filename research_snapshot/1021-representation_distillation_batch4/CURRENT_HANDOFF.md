# 第四批优先执行接续（2026-10-21）

用户新指令：第三批首版42完成完整测试后，现有三节点优先分别H、T、HT首版蒸馏；完成再继续第三批。新获得节点用于第三批。不要释放现有节点、不要恢复用户Stopped旧节点。各节点72h总上限不重置。

## 当前状态与工具终端

- 第三批首42：全navtrain103288＋navtest12146均已独立审计、合并验收；1882630条共享旧测试记录轨迹／评分完全相同。首版教师快照`../1021-representation_repair_batch3/teachers/first42_v1/FROZEN.json`已冻结；固定R2作为本批教师，不随后续扩库变动。
- 本批训练尚未正式启动。DSW真实学生零初始化重放、可微链路、冻结权重、H/T/HT单训练场景12步小拟合检查通过：`provenance/TRAINING_SMOKE_V1.json`。LoRA292个线性模块，视觉24层／语言28层全覆盖；总可训练34008448参数；峰值约7.76GB。小拟合不能当正式PDMS结果。
- 全接口目标接入：原首42仅保存valid token，但动作头会使用padding。`d4_replay_teacher_v1.py`只重放已选R2分支，完整H保留2800或实际更多token，不重新选择。要求原valid H、五次轨迹、独立新评分全精确相同。DSW3案例和DLC48实际设备通过。正式`runs/full_context_replay_v1`正在用192原常驻模型／48卡补103288场景；8场景一分片，共12911片。7分钟3418片，0失败。各节点4个CPU审计并行验收完整H／hash／原记录与评分公式。
- 主监控工具终端**27510**：`python3 -B code/d4_wait_v3.py --mode replay`。60秒机械轮询，完成＋全部CPU审计、错误、DDP v2三节点全部通过或失败、新节点／临期事件才唤醒。此前60190因7分钟事件退出，77549因DDP v1错误退出；不要再等旧终端。需保持工具托管等待，不是仅后台启动后结束会话。
- 两节点待可用仍为`dlc1ng7aizi7oi5p`、`dlc1pfltsbob3ov1`；通过第三批原cloud guard状态文件监控，Running后按原preflight／16卡工程接入，分配原第三批。

## 三节点身份与当前调度

`resources/ALLOCATION_V1.json`：replacement_a1/dlclfqx3fyywxyw3=H；replacement_a2/dlcsdgrnvcu5fbrw=T；replacement_self0/dlc156fgujiqhoj5=HT，各16卡。

第三批原成型库3762身份、123包已全部DSW工程通过；最大包又192模型／48卡／4模型同卡真实对照195840输出通过，最少剩余显存60.5GB。其第一成型包正式全量刚启动，已保留全部输出及审计。用户改变优先级后，`d4_enqueue_replay_v1.py`只把第三批可变`ELASTIC_STAGE_QUEUE.json`暂设`stages=[]/open=false`，让其服务在科学分片提交后自然返回；备份`provenance/BATCH3_DISPATCH_BEFORE_PRIORITY_V1.json`。没终止计算进程、没丢分片、没改冻结源码。常规外层ROOT3队列追加`r3_batch4_replay_bridge_v1.py`→本批`d4_replay_service_v1.py`，完整重放完成后服务自然返回，原常驻模型留在原队列中。

恢复第三批时应使用独立新服务版本，支持当前三节点训练保留／新增节点原任务；不要把旧192长lease阻塞新训练。可让旧推理模型留在显存空闲，单训练模型峰值仅7.76GB，当前空余约60GB，预计不必停常驻模型或卸载。正式训练前仍须现场多卡验证。

## DDP工程：v1隔离，v2在途

- `runs/ddp_smoke_v1`仅一次性工程，不用于任何正式权重：清单混入验证例，已告知用户并隔离。另DDP构造广播会递增冻结参数版本计数，原仅版本检查误报；48个rank均在此异常退出，无正式训练或科学结果继承。记录`provenance/DDP_SMOKE_V1_QUARANTINE.json`。
- **权威替代**`d4_ddp_smoke_v2.py`／`d4_launch_ddp_smoke_v2.py`：清单严格过滤探索训练的两个示例[3902,6]；三节点各16个实际rank、H/T/HT各自分组。`d4_distributed_v1.wrap`在DDP构造前后读取每个冻结参数的完整字节SHA，完全相同后才更新版本计数ledger；之后继续每步冻结检查。不能未经值核验直接重置ledger。
- v2已分别通过容器终端启动，输出`runs/ddp_smoke_v2/<node>/rankNN_PASS.json`或`rankNN_FAILED.json`；`ALL_RANKS_PASS.json`需要人工验收全部48、优化后全部rank可训练权重SHA一致，再写`provenance/DDP_SMOKE_ALL_NODES_ACCEPTANCE_V2.json`。监控v3会在成功或失败唤醒。远端启动终端75724/31966/76701可能有少量完成输出待取，但实际任务独立于终端。

## 科学边界与接入清单

- 本批全程无GT：不训练、不回退、不准入、不辅助优化。只用R2实际教师和Base；测试不作学生监督／调参。
- 训练仅探索子集，验证只开发／评价。`manifests/R2_TRAINING_SCENES_V2.json`为**权威训练分类**；`TRAIN_INDICES_V2.json`共85339（I49472＋P35867），探索E474不训练但完整评价；验证I9578／P7777／E120，共17475。
- V1接入使用相减的两个均值产生一例1ULP伪提升：61156的五分数只是相同值重排。V2按五个配对差值用math.fsum求均值，识别真实零收益，分到E；不设epsilon、未换教师或轨迹。旧V1及所有重放身份保持只读，完整重放仍绑定V1 hash；训练加载V2分类。见`TRAINING_SOURCES_V2.json`。
- `d4_student_v1.py`：原BF16视觉／语言与FP32原生动作链；292 LoRA rank16/alpha32/dropout0，LoRA权重FP32。`mlp1`完整参数用FP32 master并在前向cast回原精度；`feature_encoder`FP32全参。其后动作生成参数冻结/eval，但T梯度穿完整原生DDIM链；禁止推理detach／缓存。按层nonreentrant checkpoint，不依靠把冻结模块切train。
- H完整token坐标MSE；T为位置SmoothL1，x/40、y/10，航向0.1*(1−cosΔheading)。只在训练侧32个I（8hard＋24other，seed2026102103）做接口梯度标度：`configs/LOSS_CALIBRATION_V1.json`，λH=1，λT=80.21022962075446，32有效。没有按验证／测试调这个权重。单例DSW拟合的11.3875不是正式权重。
- `d4_dataset_v1.py`已准备但未正式使用；构造需明确scene_manifest+hash，读取完整目标字节一次并SHA校验，原始观测只走raw_features。噪声epoch轮换`(epoch+seed(token,0)%5)%5`；五epoch每个场景覆盖S0~S4。

## 仍需完成

1. 监控事件：DDP v2通过／错误、全教师重放＋CPU审计完成。故障只处理身份核实的本任务进程，不动DLC主进程／环境服务。原重放源码已hash冻结，改科学代码须新版本新输出。
2. 编写并冒烟正式训练／验证／推理／checkpoint与节点协调器。已有Student、Dataset、loss和真实梯度证据，不代表正式训练已启动。
3. 建议首版共同固定自然I/P曝光、global batch64（按实际卡数配置累积）、LoRA LR5e-5/投影LR1e-4、AdamW、rank16、5epoch轮换五噪声；这是当前工作判断，尚未写成正式冻结配置。相同初始化/数据顺序/曝光比较H/T/HT，联合权重用上面训练侧标度。训练重复与主训练范围对照遵循PLAN，合理控制预算。配置正式落盘后再启动。
4. 验证开发选checkpoint后冻结测试；完整训练＋验证总体103288必须报告，另分训练与验证，以及新噪声S5-S9（需训练前冻结）；不要把已选／训练S3S4叫学生新噪声。HT与T同教师轨迹和曝光。所有组原有成功能力保持、I/P/E和安全事件另报；不能把teacher Oracle当student成绩。
5. H/T/HT完成后继续第三批3762成型全量、宽搜U预筛扩库、最后GT辅助逐场景优化（仅第三批）；后两阶段本批绝不接入。第三批后续只更新live best，不自动再冻结教师快照。

保留原结果，不做Git发布。正式报告最终各任务包各一份连贯中文HTML。


## 当前有效补充：正式训练程序V4／实际恢复检查（12时UTC以后）

完整R2重放103288场景、12911分片及全部独立CPU审计已完成并验收：`runs/full_context_replay_v1/AGENT_ACCEPTANCE.json`、`analysis/full_context_replay_v1/SUMMARY.json`。DDP v2三节点48实际rank已验收：`provenance/DDP_SMOKE_ALL_NODES_ACCEPTANCE_V2.json`。

实际训练程序短测V2卡在PyTorch张量IPC：深TMPDIR超AF_UNIX长度；短路径CPU测试又确认CPFS不支持socket。未做系统／公共环境改造。只核验并停止了本任务V2失败工程的16rank及各自后代，原DLC主进程／192常驻模型均未触碰，证据`provenance/ENGINEERING_V2_STOP_<node>.json`。旧V2无任何优化步／checkpoint，V3只做CPU IPC验证、未启动模型训练。

权威新程序：`d4_common_v2.py`私有短TMPDIR；`d4_dataset_v2.py`；`d4_prefetch_v1.py`（有界同进程线程预取，不走张量IPC）；`d4_development_eval_v3.py`；`d4_train_v4.py`；`d4_prepare_runs_v4.py`；`d4_launch_train_v4.py`。模型仍`d4_student_v1.py`，损失／数据／噪声不变。每节点实际CPU预取合同全部输入与目标精确相同，`PREFETCH_CONTRACT_<node>.json`。

`provenance/TRAINING_ENGINEERING_CONFIGS_V4.json`：三组各64训练例、16验证例，2epoch／2优化步，16卡全链路。第一epoch三组都成功，早期与epoch末相同模型的16×5验证原始记录完全相同，已真实保存checkpoint并退出。`TRAINING_ENGINEERING_EPOCH_ONE_V4.json`。当前已从`step000001_epoch01_micro000000.pt`实际重新加载模型和优化器，接续第二epoch，检查恢复与评分。源码及配置已hash冻结，不在原文件上改。

**当前主监控工具终端96741**：`d4_train_wait_v3.py --suite provenance/TRAINING_ENGINEERING_CONFIGS_V4.json`。它区分旧暂停标记和RESUME_LAUNCH，等全部三组完成／异常／新节点事件。此前40065已因V2启动过久退出，74861是未启动V3的废弃监控已身份核验后停止，29652在V4第一epochEARLY事件退出；不再等旧终端。所有V4工程EARLY事件已验收ACK。

正式配置正通过`d4_prepare_runs_v4.py`生成`provenance/MAIN_CONFIGS_V4.json`，尚未启动。实际恢复检查完成后，核验全部48rank的TRAINING_COMPLETE、原始两epoch数据／验证输出、checkpoint与冻结身份，生成`TRAINING_PROGRAM_ENGINEERING_ACCEPTANCE_V4.json`；才可用`d4_launch_train_v4.py --config configs/distillation_main_v4/<H|T|HT>.json`启动正式5epoch。正式与工程权重完全分开，重新从RL Base开始。5epoch预计每组6670优化步、426880场景曝光（含尾部padding185），原85339训练场景各覆盖五噪声。第50步64例早期开发仅诊断，第1～5epoch末512例开发；主比较最终等曝光checkpoint，开发选优辅助口径另报。

训练程序支持独立checkpoint文件名含step／epoch／micro，避免早期与epoch边界同一步元数据冲突。已备断点恢复；训练全程梯度仅探索I/P。不要把工程16例开发PDMS当正式学生结果；仅用于全链路验收。


### 正式H/T/HT已启动（当前以此为准）

V4实际断点恢复全部48rank通过，`TRAINING_PROGRAM_ENGINEERING_ACCEPTANCE_V4.json`已生成。三节点已分别启动正式`distillation_main_v4_H`、`distillation_main_v4_T`、`distillation_main_v4_HT`，配置`provenance/MAIN_CONFIGS_V4.json`，全新RL Base初始化，5epoch/6670步；不继承工程权重。当前主监控工具终端**30093**，`d4_train_wait_v3.py --suite provenance/MAIN_CONFIGS_V4.json`，等第50步EARLY诊断、完成、失败、新节点事件。96741已在所有工程组完成事件退出。

为了新节点可立即用于第三批，已注册ROOT3新`r3_priority_multiplexer_v1.py`及512常驻leases，恢复原成型包两个stage的可追加调度表；当前3训练节点的原192个Base服务在该mux中只保留等待，训练后可通过本批`runs/EVALUATION_EXECUTOR.json`（尚未写）领取本组独立全量评价任务。新增节点直接走原第三批科学工作，保持原handler/配置/结果。仅在本组`runs/GROUP_COMPUTE_COMPLETE_<H|T|HT>.json`存在后，当前节点才回到第三批；标记尚未生成。后续需实现评价executor，并在全部重计算验收后才写GroupDone；不能提前恢复原任务与训练争GPU。

`d4_train_wait_v4.py`已准备，增加mux失败事件，但尚未替代当前v3。下个事件处理后可切换v4；避免留下重复DSW监控。当前未运行任何教师扩库重计算于这3节点。完整学生推理／最终验收／报告尚待后续实现和完成；正式长训练仍在进行，不以启动通过视作实验完成。


### 正式第50步与下一阶段准备

所有3组第50步3200训练曝光、64开发例×5已检查原始轨迹与评分公式，`MAIN_EARLY_PHASE_ALL_THREE_V4.json`。H -0.0573、T -0.6997、HT -0.5151分；只属于排序开发前缀的早期诊断，非最终／全局估计，未用于模型选优，继续冻结预算。192个原Base服务均确认RESERVED_FOR_BATCH4_TRAINING，48正式训练rank确有优化进展，`MAIN_START_AND_RESOURCE_RESERVATION_V4.json`。

当前主监控工具终端**91385**：`d4_train_wait_v5.py --suite provenance/MAIN_CONFIGS_V4.json`，新增加每epoch开发结果事件及mux错误。30093旧v3监控已身份核实停止；新v4当场返回EARLY事件已全ACK；不重复等待旧终端。

完整评价已准备`d4_evaluate_student_v1.py`、`d4_evaluation_service_v1.py`、`d4_prepare_evaluation_v1.py`。DSW工具82191已完成：两个真实验证场景，原五噪声与工程模型已存开发轨迹／评分完全相同；新S5-S9学生和原Base独立评分、Base S0精确重放；完整H与valid-only测试格式分支均通过，**未访问真实测试样本**。`STUDENT_FULL_EVALUATION_SMOKE_V1.json`。

`FROZEN_EVALUATION_PROTOCOL_V1.json`已在学生全测试之前冻结：最终第五epoch匹配曝光为主；开发五端点选优为辅，若同权重合并别名。全navtrain103288评S0-S4；验证17475补S5-S9；测试12146评S0-S9，原五Base引用已验收first42，另五Base现场配对并重放S0核验。新噪声没有教师实算，不计算旧Oracle分母吸收率。各组全量结果均保留，不基于测试改配置。

已注册`runs/EVALUATION_EXECUTOR.json`及`EVALUATION_QUEUE.json`中的三组多lane工程，**严格等本组TRAINING_COMPLETE才运行**；不与正式训练抢GPU。当前3节点旧Base mux会在各自训练结束后用其64个原常驻lane做工程，然后等智能体验收才正式全量。新增节点仍走第三批原工作。来源Spec/源码已hash冻结，若修改用新文件版本与输出。

下一步需实现评价CPU审计／汇总／GroupComplete验收，以及监控这些评价阶段；在本组工程all64通过后运行`d4_prepare_evaluation_v1.py --group H|T|HT`。它建立主／辅checkpoint测试锁与原始stage；测试等本模型完整navtrain评价验收。最终CPU汇总必须保留I/P/E、训练/验证/整体、会话bootstrap、新噪声与安全事件，全部重计算验收后才写GROUP_COMPUTE_COMPLETE并让本节点回第三批。


### 13:55 UTC 接续补充

正式三组持续训练；当前工具托管监控终端为 **36013**（d4_train_wait_v6.py），旧91385和13:45恢复时未知终端已仅核验停止DSW监控本身，未停止计算。新增三台各4 CPU进程的完整评价审计服务，已通过容器终端启动并有心跳：`runs/evaluation_auditor_launches_v1`和`runs/evaluation_audit_workers`；尚无正式评价输入，保持等待。外层异常纳入AUXILIARY_WATCHES，监控会唤醒。

已准备`d4_accept_training_v1.py`（实际三组工程checkpoint／48rank全通过，含曝光、数据池、随机状态、开发选择、权重有限及来源核验）；`d4_complete_group_v1.py`（全部主／辅权重的全navtrain旧噪声、验证新噪声、全测试均验收才放回第三批）；`d4_compare_students_v1.py`（精确配对H/T/HT和会话CI、训练／验证／I-P-E／难例及接口拟合）。后两者尚未应用正式结果。

教师标签统计已验收：`TEACHER_GEOMETRY_REVIEW_V1.json`。hard I 1847例贡献62.1952%教师增益，但仅5.5503%初始H损失；**损失质量不等于梯度质量**。自然比例首版配置完全不变，难例曝光对照未启动。

正式结果后依次使用`d4_accept_training_v1.py --group G`、检查旧Base常驻64lane工程后`d4_prepare_evaluation_v1.py --group G`、每个AUDIT_COMPLETE调用`d4_finish_evaluation_v1.py --stage ...`、全部本组评价通过后`d4_complete_group_v1.py --group G`。三组齐全再`d4_compare_students_v1.py`与`d4_write_report_v1.py`；后者才生成正式HTML和独立PNG。完整评价CPU审计服务已启动，不必重复启动。每epoch事件可用`d4_review_epoch_v1.py --group G --epoch N`核对原始512例／评分、I/P/E及接口误差，阅读结果后加`--acknowledge`落审阅标记。配对统计已通过恒定+10分与零差工程合同。正式HTML尚未生成，报告生成器尚待真实完整结果验收。


### 15:01 UTC：H第1个epoch已验收

`provenance/training_epoch_reviews_v1/distillation_main_v4_H_epoch01.json`：512例／30会话／2560输出，Base94.435966，H94.540329，+0.104363，95%会话CI[-0.195702,0.526013]，不能确认提分。I接口MSE为原Base的0.9391倍；P原误差0、现0.2151，整体误差0.46966高于Base初始0.40272。12个hard I增益+5.57分但区间很宽，不作全局推断。固定配置继续第2epoch，T/HT尚在第1epoch；无测试读取／调参。当前唯一主工具托管监控终端 **29473**，v6；36013已经由H事件正常退出，等待cell595亦完成。


### 15:21 UTC：三组第1epoch均验收；当前主监控51923

T和HT与H完全相同512场景／30会话。对Base增益H+0.104363、T−0.237399、HT+0.072913，各全局会话CI均跨零；原P215场景Base100，H约−0.0401、T−1.4264、HT−0.4653，损伤如实保留。各组继续既定5epoch，不用开发子群新增安全筛选或改配置。三份`training_epoch_reviews_v1/*epoch01.json`和原始16rank记录可查。旧29473监控/cell601已因T阶段事件正常退出，当前仅51923（v6）。

补充了`d4_behavior_fit_v1.py`，直接复用已落盘学生与固定R2轨迹，在CPU检查实际训练代理误差、ADE/FDE、航向，以及“代理更接近但PDMS更差”的现象；只分析S0~S4，不伪造新噪声目标。无模型重跑、无配置变化。当前已用于第1epoch；完整比较和正式报告生成器已纳入这项诊断。代码通过40米定值偏移／2π航向检查。

CPU原始轨迹监督统计也已完成并验收：`analysis/initial_trajectory_geometry_v1/SUMMARY.json`。1847个hard I仅占11.31046%初始T代理损失（H损失5.55029%、PDMS增益62.1952%），训练I/P整体初始T代理均值3.2824e−5；所有P目标轨迹精确等于Base。**损失分布不是梯度分布，也不是因果证据**。已并入最终报告生成器，没有改本轮训练。第1epoch开发代理误差：Base3.5150e−5，H4.3144e−5，T1.6940e−4，HT4.8582e−5；不要写成“代理已拟合但PDMS不升”，目前连留出平均代理也未优于Base。完整训练最终拟合仍待全量评估。


### 16:24 UTC：新增第4节点用于原第三批

脚本在16:20检测到`replacement_self1 / dlc1pfltsbob3ov1`新Running（起始16:19:15Z，4320分钟，至Oct24 16:19:15Z）。实际176CPU、约1.8TB可用主存、16×100GB PPU-ZW810E；三挂载来源、研究共享资产只读与工作区可写均核查。`r3_register_ready_node_v1.py`追加16个兼容slot，`r3_accept_node_v1.py`已逐16实际卡核对48记录/卡的真实轨迹、评分和同执行H，原始worker进入第三批。现有3节点H/T/HT保持原样。

正在通过独立容器命令增加该节点lane1/2/3（48worker，每卡共4模型；每lane先全42×5五噪声金标）和CPU原stage审计服务。组清单`../1021-representation_repair_batch3/resources/nodes/replacement_self1/EXTRA_LANES_1_2_3_V1.json`；远程启动工具终端8698可能还有完成输出，实际任务独立于终端。

新主监控`d4_train_wait_v7.py`已启动，加入新节点16卡准入／额外lane金标、准入420秒后的科学阶段语义验收、第三批原stage失败／审计完成，以及学生CPU审计心跳过期。旧v6终端51923与等待cell614均因新节点事件正常退出；不用恢复。当前新工具终端ID待本次启动结果记录。r3_phase_wait_v1会误报已完成的旧教师bridge需要验收，此旧监控不再使用；以新v7为准。

当前唯一主工具托管监控终端**49756**（v7）；新增节点48额外lane启动容器命令已成功返回，实际金标及首次科学阶段仍待v7唤醒验收。

新增replacement_self1已64实际Base模型／16卡全验收，`FOUR_LANES_ACCEPTED_V1.json`核对48额外lane×2场景×42×5=20160输出，原生16lane另各48记录。额外启动命令8698、金标验收76111均完成，不再等待。新程序`r3_finish_formed_pack_v1.py`已在原工程2个稀疏全局索引[60,1]上真实CPU合并通过：93条目，完整q、选择、选择力度及实际胜者轨迹缓存，保留所有raw；不新冻结教师。正式仍需各pack全量CPU审计完成后调用。该程序报告仅本pack+Base，整体union实时最优汇总尚需实现，不能误称现有库整体成绩。

16:35 UTC新增节点科学阶段验收：1590个新场景／739350条输出，64实际进程、16卡均提交，765/795新分片当时已CPU审计，0失败；3份审计原始轨迹／七评分与公式、Base五噪声精确一致及R3规则已抽核。`resources/nodes/replacement_self1/SCIENTIFIC_PHASE_ACCEPTANCE_V1.json`（第三批）为准。容量快照CPU45.5%、最少空余显存约64.2GB，主机可用约1.58TB。每2场景平均推理38.67秒、评分等待5.13秒、读取解压0.57秒；这些为每进程分段时间，不能当全节点串行工时。
原计划全部123已工程通过的成型包／3762身份正在追加弹性stage（各训练与冻结测试一对，共246stage；不是123包全量已完成）。保持三训练节点保留条件，新节点只领原任务，测试仍等对应训练验收；第一包之外其他训练stage可在前包待审计时接续，避免空等。


### 16:40 UTC当前工具与原任务准备

当前唯一主工具托管终端 **76831**，`d4_train_wait_v7.py --suite provenance/MAIN_CONFIGS_V4.json`。之前49756已由额外lane事件退出，后续即时v7由科学阶段事件退出；均不再等待。首3组仍在第2epoch，尚无新epoch验收。

原任务全123包／246stage已正式登记成功：`r3_enqueue_formed_stages_v1.py --chunk-size 2`，注册记录`provenance/formed_stage_registrations_v1/registration_20261021T163748347091.json`（第三批）。这是已确认3762成型身份全量计划，不使用U筛减；测试均锁定来源且等对应训练验收。现有4节点（3训练、1原任务），只剩`dlc1ng7aizi7oi5p`排队。

第三批新增`r3_finish_formed_pack_v1.py --stage runs/formed_full_v1/ID`，等AUDIT_COMPLETE才正式调用。工程用首包原2场景[60,1]验证已通过，`FORMED_MERGE_ENGINEERING_ACCEPTANCE_V1.json`；真实原始q/轨迹未重跑。正式输出全候选scores、7种选择、所选干预力度、三口径实际胜者全五轨迹，统计仅本包+Base，**整体union实时最优汇总尚需实现**。存储实测空余229TB，无需省略原始分支。

已给新增节点追加4个CPU进程读取首42原始记录，生成`analysis/first42_selected_edits_v1/navtrain`的7个选优力度缓存，以支持后续global union tie-break。**这是纯CPU分析缓存，不是新教师快照、不改变任何已有选择、无模型前向、R3力度仅S0~S2**。程序`r3_cache_first42_edits_v1.py`及启动器`r3_start_choice_cache_v1.py`；两稀疏工程例已通过。远程启动94203已成功返回；监控通过第四批AUXILIARY_WATCHES识别成功／失败。成功后需核对103288覆盖及来源，写第三批`provenance/FIRST42_EDIT_CACHE_NAVTRAIN_REVIEW_V1.json`，避免重复唤醒。后续测试缓存可在相同程序另用navtest独立路径准备。

后续应实现global union增量汇总（现有first42+逐个已全量验收pack），严格R1/R2/R3三口径和既定tie-break，不自动再冻结教师；随后宽搜训练侧U预筛与最后GT逐场景优化。第五模型并发未尝试；保持当前每卡4，冻结科学代码未改。

整体union汇总建议接续：先42 `scores.npy/trajectories.npy/selected.npy`＋上述新selected_edits缓存初始化三种实际端点；每新增已验收formed包读取其完整scores、selected、selected_edits与winner_trajectories，在同场景逐采样／五次固定／前三次固定间分别比较。完全同分按Base→较小实际干预→稳定ID，R3比较与力度只读前三，替换后保存后两次真实下降。原42与formed包都保存全五个实际胜者轨迹，来源可用catalog候选ID→原stage/cases/token/RESULT.json定位，原raw和接口不可丢。动态LIVE指针可指向不可变的分析修订文件，但不生成教师FROZEN／快照。U1/U2和R3前三专用池分别从各端点计算；不能把R1逐噪声混合的向量当成合法固定候选去计算R3固定均值。整体主要报告103288训练＋验证，并分子集；测试汇总单列，不反馈扩库。

16:45 UTC首42选优力度缓存全103288场景已验收：来源hash、全覆盖、Base所有选择力度0、[60,1]工程精确相同、额外6个R2/R3选法不同场景的R3仅前三均值均核对。`FIRST42_EDIT_CACHE_NAVTRAIN_REVIEW_V1.json`已写。旧76831和等待cell638由该AUX事件正常退出；新v7已重启，终端ID见本次工具结果。原教师FROZEN sha仍c6d5f9ec1e7eac2202c33458e485d92ed420076527dd89be82f1f84c72157c1a，没有新教师快照。


### 16:51 UTC：实时整体最优清单程序已准备并验收

当前唯一主工具托管监控为 **31273**（v7）；旧76831/cell638因选优力度缓存完成正常退出，新31273等待中。

第三批新增`r3_update_live_best_v1.py --cohort navtrain|navtest`已完成：只纳入**已全量CPU审计并由r3_finish_formed_pack_v1验收**的本cohort成型stage；first42＋增量库分别比较R1/R2/R3，完全同分Base→干预力度→稳定ID；R3比较／力度仅前三，后两下降照存。源候选ID映射到原stage/cases/token/RESULT.json，轨迹与H来源可追溯；不生成新教师快照，不动首版R2学生教师。

工程验收`LIVE_UNION_ENGINEERING_ACCEPTANCE_V1.json`：真实2场景[60,1]的42＋93条目（去重Base共134）增量结果与完整暴力搜索三口径、实际轨迹／评分精确相同；合成R3前三更好、后两更差的结果被保留，Base同分优先检查通过。

又已执行**仅first42**的完整navtrain初始化；`analysis/live_best_v1/navtrain/LIVE.json`目前revision1、42候选、0个新成型全量包。`LIVE_UNION_FIRST42_FULL_ACCEPTANCE_V1.json`核对103288全覆盖、3子集3口径PDMS／增益一致、所有会话CI逐值相同、全部六个U池清单完全相同。不要声称新成型库全量已有结果！动态LIVE所指revision为分析缓存，不是教师提取／冻结。新成型stage完成时先finish_formed_pack，再update_live_best；测试也需相同cohort的first42选优力度缓存，可用r3_start_choice_cache_v1在已核验节点另启动navtest CPU缓存（尚未启动），再独立更新navtest。

原123包246stage完整已登记，新增节点持续科学计算；原三节点仍H/T/HT第2epoch，正式全量学生评价尚未开始。后续完整学生评价CPU审计3服务已经启动，不要重复启动；完整R4验收／比较／正式报告程序均见前节。


### 17:32 UTC：H第2epoch验收，当前主监控34599

H第2epoch512例开发PDMS94.438301（Base94.435966），+0.002335，95%会话CI[-0.257061,0.336663]；I接口MSE0.64720，较初始Base0.70134改善，但P偏移仍在，整体MSE0.45680>初始0.40272；未确认稳定提分。诊断`H_epoch02.json`和`analysis/development_behavior_fit_v1/H_epoch02.json`已验收，不改训练配置，继续第3epoch。T/HT第2epoch尚未验收，正式学生全量评价未开始。旧31273/cell649因H事件退出；当前**34599**为v7主工具托管监控。

已在新增节点启动固定旧首42测试记录的**CPU选优力度缓存**，用相同`r3_start_choice_cache_v1.py --cohort navtest`，不作新候选搜索、不跑学生测试、不用于补库决策；为之后已冻结各成型包测试的独立汇总准备。容器启动终端26815已成功；输出第三批`analysis/first42_selected_edits_v1/navtest/SUMMARY.json`，success/failure纳入AUXILIARY_WATCHES。完成后须核验12146全覆盖、来源与Base零力度、R3仅前三，并写第三批`provenance/FIRST42_EDIT_CACHE_NAVTEST_REVIEW_V1.json`；然后可初始化`r3_update_live_best_v1.py --cohort navtest`，要求仅42时与旧首42测试汇总及六个U池逐项一致，不冒充新增候选结果。


### 17:38 UTC当前监控84454；测试算术缓存与整体汇总准备齐全

当前唯一工具托管主监控 **84454**（v7）；旧34599在旧首42测试力度缓存AUX成功事件退出。该缓存12146覆盖、源Summary匹配首教师快照test_reference_sha、所有Base力度0及[0,1,15,55,60,61]原记录R2／R3均核验；`FIRST42_EDIT_CACHE_NAVTEST_REVIEW_V1.json`。

已初始化第三批`analysis/live_best_v1/navtest/LIVE.json` revision1：**仅42旧候选，0个新成型全量包**。全部三口径PDMS／增益／会话CI及六个未解决池与原冻结首42测试完整相同，`LIVE_UNION_FIRST42_TEST_ACCEPTANCE_V1.json`。这只补齐旧数据算术缓存／统计程序验收，不是学生测试、不据此补库、没有新教师快照。后续任一formed包对应训练／测试stage审计后，调用finish_formed_pack再对应cohort update_live_best即可。

全123包3762 ID再核对与首42ID互不碰撞，`LIVE_UNION_FULL_CATALOG_IDENTITY_V1.json`；全库条目最终为3804逻辑ID（不是3804种独立物理执行的保证）。新节点4th持续原任务，无新停止或释放。

另准备`d4_accept_evaluation_lanes_v1.py --group G`：等各组实际训练完成且TRAINING_AGENT_ACCEPTANCE之后，检查原保留64lane/16卡工程全部来源、原五Student与Base金标、S5~S9全lane一致、full／valid两格式轨迹一致，才写本组评价工程AGENT_ACCEPTANCE。**目前尚未有这项真实64lane结果，也未执行该脚本，只做了语法检查**；首3组训练仍在运行。此前DSW独立评价单卡全链路已通过，不混作这次实际64lane验收。


### 18:12 UTC：三组第2epoch全部验收

同512开发例：H+0.002335、T−0.540538、HT+0.205483，三组对Base的95%会话CI均跨0。T保持池215例PDMS98.39764（Base100），碰撞新增10／出界新增5／TTC新增15，如实报告。HT保持池99.69460、其余I约+0.4281，尚不作全局推断。三份epoch02 reviews均已ACK；H/HT/T的`analysis/development_behavior_fit_v1/*epoch02.json`也已保存。

仅开发阶段配对诊断：`analysis/development_paired_v1/epoch02/SUMMARY.json`，HT−T=+0.74602，95%会话CI[0.03316,1.56733]；HT−H=+0.20315、区间跨0。它仍是已用于开发选择的512例，不是完整独立确认，也不改变预定配置或5epoch预算；不要宣称最终蒸馏已有效。正式全量学生评测仍未启动。

旧84454/cell658因HT epoch02事件正常退出；接着一次v7立即由T epoch02事件退出。当前v7已重新启动，ID见本次工具输出；最新主状态需跟随该ID。现有三学生进入第3epoch；第4节点继续第三批第一成型包，全部123包246stage开放，无停止／释放。

当前唯一v7主工具托管监控终端为 **61244**；全部已知epoch／缓存事件均已ACK，下一阶段／异常／新节点才唤醒。


### 20:03 UTC：H第3epoch已验收

`H_epoch03.json`：512例PDMS94.543106，Base94.435966，+0.107140；95%会话CI[-0.224649,0.577950]，仍不能确认总体提分。I接口MSE0.63821（初始0.70134），全体0.45105（初始0.40272）；P215例PDMS99.99881、没有新增碰撞／出界／TTC扣分；hard I12例约+7.66但其余I约−0.131，均为开发诊断。`analysis/development_behavior_fit_v1/H_epoch03.json`已存。H继续第4epoch；T/HT第3epoch尚待，正式完整学生评价未开始。

旧主终端61244／等待cell668由H epoch03事件正常退出。新v7刚重启，ID见本次工具输出，随后以STATUS记录为准。当前4个Running节点的分工仍3蒸馏＋1原第三批，1个待排；没有节点释放，也没有冻结新教师。

当前唯一v7主工具托管监控为 **30545**，H epoch03已ACK，其余等待完成／阶段／异常／新节点事件。


### 21:04 UTC：三组第3epoch全部验收

固定512开发例对Base：H+0.107140、T−0.347911、HT+0.174390，各全体CI均跨0。T保持池215例约−1.71404，仍明显损伤；HT其余I约+0.39791、保持池约−0.31111。三组都继续冻结第4epoch，不变数据／LR／损失，原三学生无正式完整评价结果。

三组`training_epoch_reviews_v1/*epoch03.json`全部ACK；`analysis/development_behavior_fit_v1/{H,T,HT}_epoch03.json`全有。HT整体轨迹代理误差3.28340e−5首次低于初始化Base3.51504e−5，但平均ADE仍更高，PDMS全局增益尚未确认；T代理约1.09314e−4仍高于Base。不得据此写成已完成全量比较／普遍方法优劣。

旧30545/cell674由HT epoch03事件退出；随后一次即时v7由T epoch03退出。v7已重新启动（当前ID见工具返回／随后STATUS）；当前4 Running节点分工不变：3训练＋1第三批原任务，1排队，队列开放、不释放。新准备的正式报告明确本轮没有逐组LR搜索，T不能当充分调优的全部轨迹蒸馏；这是首版固定配方的边界，不自动增加新试验。

当前唯一v7主工具托管监控为 **66379**。三组epoch03全ACK，下一边界／异常／新节点再唤醒。
原第三批最终还需宽库所选R1/R2/R3的接口跨噪声一致性统计：固定完整策略不保证其内部条件路由后的H固定。可从LIVE choice→CATALOG source_stage→原case记录的每噪声interface_sha256检查，formed局部竞争胜者接口已由CPU审计保证保留；只统计已保存的**有序有效token**，不将其说成完整padding上下文一致。完整上下文补充重放留待用户明确提取新教师时处理，不能现在再冻结新教师。当前只有首42的H统计／本轮R2完整上下文重放已经验收。
