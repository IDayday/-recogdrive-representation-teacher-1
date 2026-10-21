# 表征修复第二批实验已完成

完成于2026-10-21北京时间（证据时间使用UTC）。本文件优先于历史接续记录中的“尚未完成”指令；不自动启动下一阶段。

- [正式HTML报告](../doc/work-output/1018-representation_repair_batch2/representation_repair_batch2.html)：实际策略、特权上限、原能力损伤、匹配Base机会数、完整统计与边界。
- [计划与完成范围](PLAN.md)：分层准入已完成，未齐／未准入的原始网格不冒充完成。
- [科学执行验收](provenance/FINAL_SCIENTIFIC_ACCEPTANCE.json)：PASS代表执行与证据完整，不代表提分成功。
- [最终科学结论](analysis/final_scientific_conclusions/SUMMARY.json)：没有建立稳定的在线整体提分；事后选择与逐场景特权控制仍有潜力。
- [验证验收](runs/frozen_natural_validation_batch2_three_roles_v1/AGENT_FINAL_ACCEPTANCE_V1.json)与[测试验收](runs/frozen_natural_test_batch2_three_roles_v1/AGENT_FINAL_ACCEPTANCE_V1.json)：17,475×3噪声、12,146×5噪声，同一策略家族于验证前锁定，保留全部三次拟合。
- [全4549策略已有评分上限归约](analysis/frozen_privileged_repair_envelope/AGENT_REVIEW.json)：没有新增模型／轨迹／评分，不改变确认方案。
- [下一阶段目标](NEXT_STAGE_GOAL.md)：离线教师及轨迹／内部表征联合蒸馏仅记录意向，本批未做学生实验。

资源按用户指令保留，未主动停止或释放DLC作业，未关闭原开放队列或DLC主进程。A1、A2、B1由平台72小时上限自动终止，此前科学分片全部落盘并验收；不复活其旧worker。完成时仍有3个Running节点、5个替补Queuing，动态状态见[云端监控](resources/CLOUD_LATEST.json)。只有B2没有替补，其余按[最终映射](resources/replacements/20261020/FINAL_FIVE_NODE_REPLACEMENT_MAP.json)接续，是否即时获配取决于卡池与优先级。

常驻资源监控及控制面继续记录状态；此记录不承诺智能体会在会话结束后自行开启新回合。后续启动实验前读取最新节点状态、阶段事件与实际多卡验收；新任务使用独立配置和输出。冻结之后的非准入探索产出不回流本批结论。
