# ReCogDrive 表征修复与 H/T/HT 蒸馏

本 fork 在2026-10-20首版基础上，整理了后续四阶段研究代码、冻结修复参数、固定R2教师选择、学生训练和评价入口。当前方案：**单机8×NVIDIA A800重建教师目标，再从官方RL Base开始复现H/T/HT**。不需要GitHub Release、Hugging Face或阿里云凭据。

先读 **[8×A800接续说明](docs/CONTINUE_ON_A800.md)**，其中有完整命令、资产清单、评价范围和复现边界。

原项目定位、开发进度和DLC分工见 **[开发时间线](docs/DEVELOPMENT_TIMELINE.md)**。

| 内容 | 入口 |
|---|---|
| 准备、冒烟、评分缓存、教师重建、训练、评价 | `python -m continuation.reproduce --help` |
| 首42候选对应38份冻结修复资产，约493MB | `research_snapshot/`，`INDEX.json`记录SHA256 |
| 固定R2的103,288场景选择、原轨迹和接口指纹 | `reference/continuation_20261022/r2/`及冻结清单 |
| 第一批观察／修复、第二批专家化、第三批扩库、第四批蒸馏原代码 | `research_snapshot/<任务日期>/code/` |
| 原计划、配置、报告和阶段验收 | `research_snapshot/`、`reference/continuation_20261022/` |
| 10月20日11策略历史复现和旧教师导出 | [原版说明](docs/LEGACY_FIRST_BATCH.md)，原根目录脚本保留 |

```bash
git clone --depth 1 https://github.com/IDayday/-recogdrive-representation-teacher-1.git
cd -- -recogdrive-representation-teacher-1
cp configs/paths.example.json paths.continuation.local.json
# 编辑本地路径，并按接续说明准备独立的ReCogDrive/NAVSIM环境。
python -B -m continuation.reproduce --paths paths.continuation.local.json \
  --workspace /your/writable/recogdrive-run --stage prepare
```

H仅监督完整动作接口表征，T仅监督轨迹，HT联合监督。三组使用相同初始化、场景／噪声曝光和5epoch预算，全局batch64；8卡时每卡累计8个microbatch。教师固定为首42候选的R2获选分支，不随后续扩库改变。

重建的H和轨迹来自同一次真实执行，包含动作头实际使用的padding。A800重跑有独立环境与输出身份；不保证逐位复现原PPU浮点值或最终分数。默认`record`模式记录差异，`exact`模式严格核对原接口指纹／轨迹并在差异处停止。三组学生使用同一份新教师。

仓库不含RL/VLM大模型、数据集、地图、完整教师缓存或已训练学生。完整教师目标约414GB；建议额外预留至少600GB工作空间。第三批大扩库的全部定义／代码已归档，额外拟合资产约12GB不属于当前R2／H/T/HT重跑依赖。

历史教师Oracle、开发集诊断与新A800学生成绩分别报告。本发布不宣称已完成8×A800全量训练，也不以旧教师上限证明蒸馏有效。
