# 在8×A800上重建教师并复现H/T/HT

按本次最终选择：**重建固定R2教师，学生从官方RL Base开始训练**。不续跑原PPU优化器，不依赖DLC、旧挂载或大文件平台。原始代码／配置保留原字节；适配在`continuation/`，输出在独立可写workspace。

## 1. 资产

| 资产 | 要求与来源 |
|---|---|
| RL规划checkpoint | 目标机现有官方`ReCogDrive_Diffusion_Planner_2B_RL.ckpt`，核对下方SHA |
| 配套VLM | 完整`ReCogDrive-VLM-2B`，含safetensors、tokenizer、配置、自定义模型代码；仅规划checkpoint不足以重建表征 |
| 数据／地图 | NAVSIM navtrain/trainval、navtest的logs与相机数据，配套nuPlan地图 |
| 冻结修复参数 | 仓库携带38文件，约493MB；无需重新拟合 |
| 教师身份 | 仓库携带103,288场景的R2选择、I/P/E、会话划分、原轨迹及接口指纹 |
| PDM缓存 | 从已有logs和地图重建，提供入口；完整训练／测试缓存约39GB |
| 完整教师H与轨迹 | 在目标机重建，约414GB；不需要下载原数百GB缓存 |
| 学生权重 | 在目标机训练，H/T/HT各5epoch、6670步 |

RL checkpoint SHA256：

```text
23fb949b10387efeff87e093703d5faf41b61b9e5ead16d4076661e3c7c08a20
```

建议额外空闲工作盘≥600GB，另加已有权重／数据集；其中还需保存评分缓存、训练checkpoint和日志。主存按目标机pilot实测峰值安排。

## 2. 环境与路径

使用Python3.10、适合A800的CUDA版Torch2.4.0／torchvision0.19.0及可运行的NAVSIM v1／nuPlan环境。原关键版本见`reference/environment.json`和`requirements-inference.txt`。已验证的参考路径使用transformers4.37.0；本机4.57实测在Qwen层续算时报维度错误。工具不因版本号不同直接拒绝，其他版本须通过真实pilot、数值比较和多卡反向验证。

在独立环境准备依赖。需要采用参考环境时，已有可用ReCogDrive/NAVSIM环境可建立私有venv并安装：

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install 'transformers==4.37.0' 'tokenizers==0.15.2'
```

没有基础推理环境时，先按原版本清单准备Torch、diffusers、timm、nuplan-devkit及普通NAVSIM依赖，再运行检查。FlashAttention须匹配CUDA/Torch，不在NVIDIA服务器安装PPU专用wheel。工具不自动安装依赖、下载模型或修改系统。

```bash
git clone --depth 1 https://github.com/IDayday/-recogdrive-representation-teacher-1.git
cd -- -recogdrive-representation-teacher-1
cp configs/paths.example.json paths.continuation.local.json
```

编辑模型、maps、logs、sensor、metric路径。评分缓存目录用自己可写的位置，如`/data/recogdrive-run/_data/metrics/navtrain`和`navtest`。

如果模型验收仅在`configuration_internvl_chat.py`处指纹不符，原服务器对应文件现已补入[`assets/vlm_source/`](../assets/vlm_source/README.md)。按该目录说明先备份目标机文件、安装源版本，再重新执行`doctor --models-only`。

目录层次：`navtrain_logs`下有`trainval/<log>.pkl`，`navtrain_sensor`下有`trainval/<log>/...`；测试对应`test/`。`navtrain_metric`下生成`<log>/unknown/<token>/metric_cache.pkl`。核对软链真实目标。

以下命令均在仓库根目录、同一个私有环境执行；每条的workspace替换为同一绝对路径。

## 3. 先验证3个真实场景

```bash
python -B -m continuation.reproduce --paths paths.continuation.local.json \
  --workspace /data/recogdrive-run --stage prepare
python -B -m unittest discover -s tests -v
python -B -m continuation.reproduce --paths paths.continuation.local.json \
  --workspace /data/recogdrive-run --stage pilot
python -B -m continuation.smoke --paths paths.continuation.local.json \
  --workspace /data/recogdrive-run --out /data/recogdrive-run/H_T_HT_SMOKE.json
```

prepare展开并校验冻结文件、权重。pilot仅为3个固定场景补评分缓存、重放已选R2，输出完整H和五条轨迹，覆盖I/P及训练／验证来源，不更新学生。

检查`PORTABLE_PILOT_ACCEPTANCE.json`、`runs/full_context_replay_v1/reference_diagnostics/`及case的`RESULT.json`：候选、完整token数、轨迹差异、分数、接口指纹。smoke在单卡验证H/T/HT真实目标的梯度、token与冻结参数，不做优化更新。默认record承认并记录跨后端差异，生成独立目标机教师版本，不为了接近原分数重新选候选。

严格数值复核可用`--reference-mode exact`，差异会停止并保留诊断；不同模式用不同workspace。`--max-pilot-trajectory-error`可指定自己的数值界限，默认不擅定跨硬件容差。pilot不证明全量精确复现。

## 4. 全量重建教师

```bash
python -B -m continuation.reproduce --paths paths.continuation.local.json \
  --workspace /data/recogdrive-run --stage cache --cpu-workers 16
python -B -m continuation.reproduce --paths paths.continuation.local.json \
  --workspace /data/recogdrive-run --stage teacher
```

cache按冻结清单重建navtrain PDM缓存，保留已有缓存。teacher使用8个单GPU分片进程，**仅重放每场景已经确定的R2分支及Base**；不重跑42候选搜索，不使用GT。

每场景保存完整padding上下文的FP32 H、五条同执行轨迹、token IDs、attention mask、position IDs、评分、残差统计和SHA。动作头使用padding，不能以旧valid-only接口替代。

已完成case可续跑，变化协议／环境时用新workspace。结束后核查103,288场景覆盖并生成新的教师验收和8卡配置。原I/P/E与曝光标签固定以维持数据身份；实际目标机分数另存。报告同时交代原／新后端差异。

## 5. 8卡依次训练H、T、HT

```bash
python -B -m continuation.reproduce --paths paths.continuation.local.json \
  --workspace /data/recogdrive-run --stage train
```

每组先做8个实际rank的前向／反向和冻结参数广播检查，随后重新从RL Base初始化正式训练。冒烟没有优化更新。8卡依次供三组使用；`--groups H`可只运行一组。重复入口跳过完成组，未完成组从自己的LATEST_CHECKPOINT恢复。

| 项目 | 保留的配方 |
|---|---|
| 学生 | 同一RL Base；视觉24层／语言28层广覆盖LoRA，两处投影全参 |
| 动作生成 | 参数冻结，T梯度穿原生完整DDIM链 |
| 训练 | exploration中I=49,472、P=35,867，共85,339；E不训练 |
| 验证 | 会话留出17,475，每epoch固定512场景开发面板 |
| 曝光 | 全局batch64、microbatch1；8卡累计8步；5epoch／6670优化步 |
| 噪声 | 原按场景seed，5epoch轮换S0—S4，每场景覆盖五噪声 |
| 优化器 | AdamW；LoRA LR5e-5，投影LR1e-4；原warmup与余弦调度 |
| H损失 | 完整token／坐标MSE，含padding |
| T损失 | 原归一化位置SmoothL1＋周期航向损失 |
| 实际权重(H,T) | H=(1,0)，T=(0,1)，HT=(1,80.21022962075446) |

原16卡每卡累计4步改为8卡累计8步，保持每优化步的场景集合与总预算，浮点归约／内核／随机数实现不保证逐位相同。原首版没有逐组LR搜索。

开发评价使用目标机的配对Base；适配层移除了旧开发器对全42评分矩阵的依赖，不把旧PPU分数混入A800增益。教师与学生环境不同则重新计算当前Base，而不直接套用旧缓存。正式比较以最终相同曝光checkpoint为主，开发选优为辅助。检查点保存优化器和rank随机数，可同后端恢复。

## 6. 评价

```bash
python -B -m continuation.reproduce --paths paths.continuation.local.json \
  --workspace /data/recogdrive-run --stage evaluate --allow-navtest
```

评价最终checkpoint：完整navtrain S0—S4、完整验证S5—S9、独立navtest S0—S9。先锁定测试模型；测试不进入监督或教师重选。必要时补测试PDM缓存。保存学生／目标机Base的真实轨迹与七项评分；按场景聚合后按会话bootstrap，报告PDMS、安全事件、I/P/E与保留分层及区间。T与HT都运行时，再生成逐场景配对的HT−T及区间；多个噪声不作为独立训练重复。

便携入口主报PDMS与安全；完整接口误差、行为拟合、原报告生成等代码也已归档，可继续扩展。先用`continuation.evaluate --development --limit 8`做小评价，正式计算去掉limit。原报告和旧开发分数不作为A800验收。

## 7. 后续开发定位

| 任务目录 | 内容 |
|---|---|
| 1016-rl_representation_analysis | RL基线、自然／配对观察、子空间、动作头及全VLM干预，完成 |
| 1018-representation_repair_batch2 | 专家化、独立拟合、路由／强度、验证／测试，完成；未确认稳定在线整体提分 |
| 1021-representation_repair_batch3 | 首42与教师快照完成；更大3762条目／123包扩库为后续工作 |
| 1021-representation_distillation_batch4 | H/T/HT、可微DDIM、DDP、训练、评价、诊断及报告代码 |

原代码在`research_snapshot/<目录>/code/`。INDEX保留SHA；大JSON用gzip存储，prepare还原原字节。旧DLC提交、节点、队列与恢复脚本是历史归档，不在新机直接执行。

额外扩库拟合资产清单在`research_snapshot/BULK_ASSETS.json`，约12GB，当前R2／H/T/HT不需要。继续原扩库可使用`continuation.expand`运行冻结pack，但先携带对应扩展参数；归档定义不等于自动重建其全部历史依赖。宽搜及GT逐场景特权优化仍是独立后续实验。

本地验证范围见`reference/continuation_20261022/PORTABLE_VALIDATION.json`。目标8×A800的实际多卡冒烟及全量成绩以新产物为准。
