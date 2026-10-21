# 2026-10-21 两个本人实例释放记录

用户明确范围：只释放 `dlcrnshl7t4hcmoy`（self_0）与 `dlcrxs2yz4ime2fe`（self_1），保留其他运行节点与排队替补。本条覆盖此前对这两台的保留指令，不扩大到其他实例。

- 两台均在 UTC 01:15:33／北京时间09:15:33 回读确认 `Stopped`。平台仍可能显示 Pod `Terminating`，不能将云端作业终态等同于已现场确认所有底层资源回收。
- 各44个计算 worker 在结果落盘／队列等待边界暂停后才 StopJob；全部675个队列范围、5,714,650条 claim 的只读审计确认：这两台无未完成且无终态失败记录的科学任务。保留32个历史无限派单器租约作为已停止进程的运行记录，不删除、不伪造科学完成回执。
- 共享控制面已迁移到 `replacement_a1 / dlclfqx3fyywxyw3`，PID33141；原有应运行的97个控制器接续，73个历代已完成／退休ID继续排除，单领导锁与心跳验收通过。迁移中首次遗漏继承更早排除列表，短暂重入41个历史辅助脚本；已停止该尝试并完成名单纠正，错误与恢复证据均保留。
- 当前保留 `replacement_a1`、`replacement_a2` 两个运行节点及三个排队替补。没有停止其他作业、关闭共享队列或创建新作业。实时状态仍查 `resources/CLOUD_LATEST.json`。
- 正式HTML报告、最终科学验收及交付验收文件SHA256复核未变；不修改本批已冻结结论，不启动下一阶段蒸馏。

证据入口：`resources/releases/self_pair_20261021T010932Z/FINAL_ACCEPTANCE.json`；在途收尾：各节点的 `QUIESCENT.json` 与 `PRE_STOP_ACCEPTANCE.json`；遗留租约：`PENDING_CLAIM_AUDIT.json`；新控制面：`controller_corrected/control/ACTIVE.json`、`HEARTBEAT.json` 与 `CONTROL_MIGRATION_ACCEPTED.json`。辅助收尾脚本的问题和恢复见 `RECOVERED_OPERATIONAL_HELPER_ERRORS.json`。

后续操作读取 `runs/discovery_v1/control_plane/LIVE.json` 的 `migration_proof`，不要使用旧self_0的PID或日志路径。现成 `r2_agent_wait_v3.py` 会沿此字段定位新事件日志，无需硬编码新路径。不要重启这两台旧worker或重新提交已停实例；三个已排队替补保持原安排。
