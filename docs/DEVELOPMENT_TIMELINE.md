# 开发时间线与本次接续范围

证据来自本次归档的原始计划、CURRENT_HANDOFF、配置与验收；训练进度快照时间为2026-10-21 22:15 UTC（北京时间10月22日06:15）。这些是历史状态，不是GitHub端实时DLC监控。

| 时间／目录 | 开发内容 | 已确认进度 |
|---|---|---|
| 10月16日 `1016-rl_representation_analysis` | 官方RL基线、自然样本与配对样本、子空间／动作接口／VLM层干预；形成修复分析和初始策略 | 分析、初版拟合与报告已形成 |
| 10月18日 `1018-representation_repair_batch2` | 专家化修复、独立拟合、路由与强度组合、验证／测试评估 | 形成冻结参数和评估代码；尚不能把逐场景Oracle增益解释为稳定在线整体增益 |
| 10月20日 `1020-representation_teacher_portable` | 将首版11策略和资产打包成可移植GitHub仓库 | 你的fork原main起点；原README保存为 `LEGACY_FIRST_BATCH.md`，根目录入口保留 |
| 10月21日 `1021-representation_repair_batch3` | 首42候选全量真实轨迹与评分、R1/R2/R3分析；扩展3762成型身份、123包／246阶段的宽搜索 | 首42的navtrain 103,288和navtest 12,146均完成审计；扩展任务已登记，不能视为全量完成 |
| 10月21日起 `1021-representation_distillation_batch4` | 固定首42 R2场景教师；完整padding接口H与五条同执行轨迹T；可微原生DDIM、广覆盖LoRA、H/T/HT对照 | 完整教师重放已验收；正式学生训练进行中；三组epoch3开发检查已完成，最终全量学生评价尚未完成 |
| 本次迁移 | 保留原研究代码和冻结资产，新增 `continuation/` 与8×A800入口 | 目标机重建固定R2，再从官方RL Base重新训练三组；当前服务器未运行8×A800全量实验 |

## 原DLC分工

| 原任务／节点 | 工作 |
|---|---|
| `dlclfqx3fyywxyw3` / `replacement_a1` | H：只蒸馏完整动作接口表征，16卡；进度快照最慢rank 5,175/6,670优化步 |
| `dlcsdgrnvcu5fbrw` / `replacement_a2` | T：只蒸馏轨迹，梯度穿冻结动作头的原生DDIM，16卡；4,575/6,670步 |
| `dlc156fgujiqhoj5` / `replacement_self0` | HT：联合蒸馏，实际权重(1,80.21022962075446)，16卡；4,600/6,670步 |
| `dlc1pfltsbob3ov1` / `replacement_self1` | 新增16张物理卡，接回第三批扩库工作；已接入64个模型slot，不是第四个H/T/HT组 |
| `dlc1ng7aizi7oi5p` | 交接记录中仍排队的后续扩库资源 |

三训练节点早先合计48卡还承担过完整教师H／轨迹重放；教师重放已结束，不能把原缓存任务名称直接等同于当前计算内容。上述任务由原环境管理，本迁移工具不操作或释放它们。

## 已得到什么结果

固定首42 R2的历史Oracle结果：navtrain PDMS由94.87895到96.11612，差值+1.23717；navtest由90.47931到93.36588，差值+2.88657。R2依赖原评分选定逐场景分支，这是教师上限诊断，不是学生在线性能证明。

H/T/HT在epoch3固定512开发场景相对Base的PDMS差值约为+0.10714、−0.34791、+0.17439；区间均跨零。尚无足够证据声称蒸馏稳定有效，也没有在此快照中完成最终全量学生测试。

原始证据：`reference/continuation_20261022/STATUS.json`、`runs__TRAINING_MONITOR.json`、`FIRST42_NAVTRAIN_SUMMARY.json`、`FIRST42_NAVTEST_SUMMARY.json`和逐组epoch审查JSON。原HANDOFF保存在对应 `research_snapshot/` 任务目录。

## 下一台服务器从哪里接上

按 [8×A800说明](CONTINUE_ON_A800.md) 依次prepare、pilot和单卡梯度检查，再cache、teacher、train、evaluate。主训练入口仍调用原 `d4_train_v4.py`，模型／损失仍调用原 `d4_student_v1.py`；路径、目标加载、开发评分与本地多卡启动由适配层处理。

本次保留原候选、场景、I/P/E、训练／验证划分、初始化、损失权重、噪声曝光和优化预算。新机的实际教师数值与环境单独记录，H/T/HT共用同一份新教师。跨库版本或硬件的数值等价需要测量；版本号相同不能代替验证。

无需原学生优化器或414GB教师缓存。除已有官方RL权重、完整VLM、数据和地图外，当前R2需要的约493MB冻结修复参数已经入库。第三批更大扩库额外约12GB参数另有清单，不是复现当前H/T/HT的必需项。
