# 最终状态：正确两路线已完成并验收

以PLAN最终完成表、STATUS和provenance/TWO_ROUTE_FINAL_VERIFICATION.json为准；所有计算结束。下文为执行与纠错过程归档，不再作为待办。

# 最高优先级：路线一/二数据定义与当前进行中的工作

用户纠正：路线一=模型**自然输出**成功与失败，完整S0有103288场景（90153高质量、2288失败、10847中间）；路线二=模型自己的失败与对应GT配对后加噪、完整去噪重评分。此前把路线二全部候选global_class_residual当路线一，是错误，完成声明已撤回。必须完成真实路线一，不能再次以route2数据代替。仍只观察，不干预/修复，不读navtest。

本轮有用户明确授权继续PLAN全部工作。先前补充方案configs/plan_completion_v2.json在用户数据定义纠正前写入，**已过时，不能执行它假定的route1数据来源**。

## 已更正
- PLAN已明确两种独立数据入口；STATUS撤回route1完成。原报告已在顶部加数据定义更正，原版备份provenance/route-definition-correction/。最终要更新同一份连贯报告，分别呈现两条路线。
- 不修改任何冻结baseline/paired代码、上游或共享资产；新natural_*.py/sh为真实route1专用。
- manifests/natural_s0.json：完整103288场景，精确对齐baseline manifest与scores.csv，按原采集会话80/20划分，与route2保持相同split seed20261016。

## 当前真实路线一正在运行
- run: natural_s0_repr_20261016T080905Z
- 作业node0: dlc9cj9xntza8q3z；node1: dlc9mivbfrv2je24；各16卡，共32卡。
- configs/natural_execution_v1.json，configs/natural_route1_v1.json；源代码已哈希冻结，**不要改natural_representation.py/natural_coordinate.py/natural_launch.sh**及其引用的frozen files。
- DSW smoke runs/natural_route1_dsw_smoke_v2/smoke/rank000/COMPLETE.json PASS。自然success/fail/middle三个锚点，hooks不改输出，全部张量和实际噪声可精确重放。v1仅非seekable流API错误工程记录，已修正并保留。
- 两节点先32卡smoke，每卡与DSW三个锚点全部张量/噪声/轨迹精确相同，共96锚点对比，才放正式全量。
- 每条都调用原agent.forward/get_action，**不传init_actions、不用GT**，每token原S0种子；捕获5步、18个384维阶段×8token及独立512维输出、latents、x0、noise、trajectory，逐条要求与原保存S0轨迹float32精确相等才复用原评分。
- 原始表征约123GB（不是1.2TB，已纠正估算）。按32场景chunk写NPZ，非seekable写流同时SHA256，不额外全量读盘。投影时应一次read_bytes，验SHA后BytesIO载入，避免重复IO。
- 同时每rank累计float64充分统计，每subset×quality三类共6组：n,sum_y,sum_y2,representations_sum/gram/xy, dit_output_sum/gram/xy。每rank约5.6GB；node完成后reduce16rank到node{0,1}/moments/各组.npz约5.6GB。完整raw约123GB，rank moments约180GB，node moments约11GB。
- 终端session89752：前台monitor，日志provenance/natural_cloud_monitor_v1.log，必须保持工具等待并完成验收，不仅后台写状态文件后结束回合。节点每5分钟语义检查原S0种子、自然来源、exact replay。
- COLLECTION_READY仅代表采集完成，**不是路线一分析完成**。

## 分析实现与剩余交付（以下实现状态以本节新增说明为准）
1. 合并两个node moments，按组/field输出.npy memmap，避免NPZ不支持切片导致每个cell读1GB。核查6组n、sum_y、sum_y2与baseline原records一致。每group约1GB，全部6GB，DSW RAM51.5GB足够。
2. 真实路线一：从全部探索自然success/fail的Gram做精确eigh/SVD；5步×19阶段×8token=760cell；Us/Uf等维k8，uncentered/pooled共中心两套，R=(I-UsUsT)Uf再SVD；保存完整谱、Us/Uf、R奇异值/有效rank/能量、共同残差basis和center。维数2/4/8/16/32敏感性可由moments直接计算能量/mean/cov距离；主k8做全经验分布。不混不同去噪步。
3. 将完整自然raw一次读盘验hash后投影到固定探索basis，保存每case×step×stage×token×两套basis×8维，约5GB。6CPU并行逐chunk投影（float64计算、float32存坐标），103288顺序用global_index对齐。可以测试DSW PPU float64 matmul是否支持/更快，但不能降低弱残差精度。用户算力充裕，16卡更快则优先，不刻意省8卡。
4. route1评估数据是**留出自然场景**，不是成对GT样本；质量标签成功>90、失败<70，保留中间作连续PDMS。共同残差坐标下均值向量、协方差矩阵、mean/cov差、固定探索分位数bin的经验重叠、AUC/AP、continuous PDMS ridge（可用充分统计拟合）等。按采集会话bootstrap，不将10万条当完全独立会话。可用每个留出会话内fail-success的scalar均值差进行cluster sign permutation1999与BH（5*19*8*2=1520主检验），防止只看跨场景来源差。维数敏感性描述性。原始成功极不平衡，不能只报accuracy。
5. route2原有两个core都确实完成（差分SVD+配对残差），global_class_residual只是route2候选对照。尚欠残差mean/cov/经验重叠与连续PDMS、按失败模式的独立空间/比较（原先只共享方向分模式评分）。可复用analysis/observation_v1/cache（2×2288×2×18×8×384 +512输出），全部在任务内。补充不要再将其称route1。
6. 更新同一HTML为两条独立路线，给出PLAN逐项完成表、样本/fit/验证来源与差异，保留旧报告版本。独立验收原S0全量replay、完整覆盖、raw hash（投影时全验）、moments一致、自然来源、两个云作业与pod成功退出、不同路线无混用。更新PLAN/STATUS/nav/handoff。

## 资源与边界
DSW live 8CPU/51.5GiB RAM，1张PPU-ZW810E 96GB可Torch运算；nvidia-smi HGML错误不要环境改造。32DLC卡是PPU同类型，镜像/RO三挂载与baseline同。共享资产只读，全部新输出任务内。无子智能体授权，不spawn。


## 08:31最新实现状态，避免压缩后重复工作
- `code/natural_analysis.py`已完整实现并完成真实自然smoke tensor数值交叉检查，见`provenance/natural_analysis_math_smoke.json`。代码已冻结到`configs/natural_analysis_execution_v1.json`；**不要改它**，等待中的pipeline会校验hash。
- 分析协议`configs/natural_analysis_v1.json`已冻结。原始R1数据完整103288，拟合natural high74900/fail1850，中间9063；验证high15253/fail438，中间1784。不是使用route2候选。
- 前台分析等待终端session11534，日志`provenance/natural_analysis_pipeline_v1.log`：等COLLECTION_READY后自动依次merge两node精确moments→760cell类别SVD/残差→3232 raw chunks全hash验证与投影→1520项自然分布/continuous/session contrast检验。输出`analysis/natural_route1_v1`。必须继续监控89752和11534至结束并验收。
- 每个raw chunk约35MB，总raw约123GB，主投影约5GB。CPU6workers，float64投影，FP32存坐标；不用1.2TB的错误估算。原始rank moments约180GB，node reduce共约11GB。
- `code/paired_distribution_completion.py`已运行完成，session37377退出0，结果`analysis/paired_route2_completion_v2/COMPLETE.json`，152cell×5种差分/残差/候选控制的means/cov/共享bin重叠/连续绝对PDMS与场景内差值。独立final-failure modes fit：collision142对/57会话，offroad152/43，ttc421/101，progress1/1不足不拟合。10944种模式迁移描述，8208项满足条件构成FDR家族。P0探索拟合、P0/P1留出固定。**这些全属route2**。
- `code/two_route_report.py`已写好并语法通过，待R1结果后写`analysis/two_route_conclusions.json`（conclusions/boundary/next_observations/completion_checklist）。report命令输出仍用`doc/work-output/1016-rl_representation_analysis/representation_observation.html`，同一连贯正式报告；新builder图6张，route1 natural AUC与route2 paired ordering分开，不能直接比较数值。
- `code/verify_two_routes.py`已写好，待生成新报告后运行，输出新不可覆盖`provenance/TWO_ROUTE_FINAL_VERIFICATION.json`；之前OBSERVATION_FINAL_VERIFICATION只机械验收了route2误归类的数据，已撤回route1范围，旧证据保留。
- 还需要保存`dlc/natural_final_node0.json`、node1，使用cloud GetJob返回的Pods（不是/jobs/id/pods错误接口），只保存JobId/Status/Pods等必要字段，不保存credentials/env。
- 最后更新PLAN/STATUS/navigation/handoff为正确两路线状态，并保留明确更正记录。所有GPU任务、raw hash、原轨迹exact replay、独立moment tile/projection crosschecks、两作业及Pods退出成功、6图报告数字与source dataset核对通过，才最终报告两条均完成。PLAN仍只观察，不干预/修复。

08:37状态：全部103288自然S0捕获已结束，32worker receipts均COMPLETE，质量计数90153/2288/10847精确一致；两DLC节点各自6个moments组已写5组，仍在reduce最后一组，预计很快COLLECTION_READY。89752与11534仍工具等待，不能结束回合。完整capture evidence=provenance/natural_all_workers_capture_complete.json。新builder与verifier均已写好但尚未运行，须先等真正R1分析完成并根据实际tests.json写结论。

08:40更新：两个DLC均Succeeded/Pod exit0，32GPU释放；全量moments合并完成，760个真实自然S0 cell已完成SVD/残差。初版projection把str当Path报错，原v1 source/输出全保留；新增natural_analysis_v2.py仅修路径类型，真实32场景projection smoke PASS。接续只跑project/evaluate，配置natural_analysis_execution_v2.json；11534已因该工程错误退出1，不再等待旧终端。新前台终端号见最新工具返回。不要重跑采集/合并/SVD。
