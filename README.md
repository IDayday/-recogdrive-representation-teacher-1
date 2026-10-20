# ReCogDrive 表征修复：第一批复现与离线教师导出

本仓库固定第一批 ReCogDrive-2B-RL 的 **11 个 VLM/接口修复策略 + Base**，提供种子、方法参数、原始模型/评分代码快照和运行入口。普通单卡服务器即可分片重放，不依赖阿里云、DLC、CPFS 或原 `/mnt/...` 挂载。显存与软件可用性仍需在目标服务器做冒烟验收。

有两个明确的用途：

| 入口 | 作用 | 输出身份 |
|---|---|---|
| `verify_oracle.py` / `run_teacher.py --mode historical` | 复现 12,146 个 navtest 场景、S0–S4 的 **+2.15188162887147 PDMS** | 使用真实评分事后选择的历史诊断上限 |
| `run_teacher.py --mode teacher` | 在 navtrain 上为每场景选同一真实分支，保存轨迹和动作接口表征 | 供后续轨迹监督与联合蒸馏使用的新教师数据 |

教师导出属于新用途，训练与最终泛化结果尚未验证。历史 +2.1519 不等于学生可获得的增分。

## 种子与“怎么修复”都固定了

- 种子公式：`int(sha256(f"{token}|20261008|{j}".encode()).hexdigest()[:8],16)`，`j=0,1,2,3,4` 对应 S0–S4。实现和样例见 `seeds.py`、`reference/seeds.json`。
- 不依赖 GPU编号、rank、进程数或 Python 的随机 `hash()`。每个场景、每个方法、每个采样开始前重置相同 RNG。
- 初始动作噪声为 `[1,8,3]` FP32，随后按顺序抽取五份同形状去噪噪声。原生 DDIM 时间为 `[80,60,40,20,0]`，eta=1，`deterministic=False`，步噪声按原模型裁剪。`noise_bank()` 提供同序参考生成，不改变模型的原生随机数调用。
- `reference/golden_noise_banks.npz` 另存了3个golden场景、S0–S4的实际参考噪声数组（初始噪声+五步噪声），可在冒烟时传 `--noise-bank reference/golden_noise_banks.npz`，排除异机随机数生成器差异。噪声一致仍需另外检查模型计算和评分是否一致；完整全量噪声库不在仓库内。
- RL 动作头 FP32、autocast关闭、batch size=1；VLM按原 BF16 路径运行。固定seed不能单独保证跨GPU/驱动/Torch版本逐位一致，先跑golden验收。
- `configs/methods.json` 固定每种修复的位置、token池化、子空间、算子、alpha、cap、内部门控；`fits/*.npz` 是对应的**冻结方法参数**，最大单文件约4.6MB，不是RL/VLM大模型权重。不要重新拟合后仍称为原实验复现。
- 11项中有物理重复方法。为保持原上限的候选顺序与平局规则，复现时保留它们。新增位置/方法/力度请写新catalog和新输出目录。

## 1. 配置师兄本地资产

先使用已有 ReCogDrive/NAVSIM 环境，原关键版本见 `reference/environment.json` 和 `requirements-inference.txt`。在独立环境补足依赖；本仓库不自动安装或下载。

```bash
git clone https://github.com/sjc786526-coder/-recogdrive-representation-teacher-1.git
cd -- -recogdrive-representation-teacher-1
cp configs/paths.example.json paths.local.json
# 编辑 paths.local.json，填本地模型、logs、sensor、metric-cache和地图路径
python -B check_assets.py --paths paths.local.json
python -B -m unittest discover -s tests -v
```

必须使用SHA匹配的RL checkpoint和配套VLM模型/配置/tokenizer/自定义模型代码。RL checkpoint SHA：`23fb949b10387efeff87e093703d5faf41b61b9e5ead16d4076661e3c7c08a20`。模型初始化只忽略明确的训练期 `action_head.old_policy.*`，其余有效参数严格加载。原权重指纹完整保留在配置中。

路径的目录层次：例如 `navtest_logs` 下面有 `test/<log>.pkl`，`navtest_sensor` 下面有 `test/<log>/...`；`navtest_metric` 下面有 `<log>/unknown/<token>/metric_cache.pkl`。训练集logs/sensor同理带 `trainval` 子目录。清单中保留每个评分缓存的SHA；缓存内容不同须重新校准，不能跳过验证强行套用原数字。无需旧的VLM特征缓存，程序从原始图像与历史观测重新运行VLM。

如果已有数据集但没有PDM评分缓存，先用配套NAVSIM v1环境生成缓存。若是重新序列化或重新生成的缓存，文件SHA可能不同；先运行 `python -B rescore_golden.py --paths paths.local.json --out outputs/cache_calibration.json`。保存轨迹的七项评分核对通过后，可以在新推理命令显式增加 `--cache-calibration outputs/cache_calibration.json`，记录新缓存SHA。此时全量分数仍需比较，少量golden通过不等于已证明全体缓存等价。

仓库仅含代码、小型冻结方法参数、压缩场景清单与9条golden轨迹；没有权重、原始图像、评分缓存或全量教师表征。

## 2. 先跑3场景golden

从 `reference/golden.json` 取3个token和两个非Base方法ID，以S0重放。下面一条命令会自动读取这些参数：

```bash
python -B smoke.py --paths paths.local.json --out outputs/golden
```

`smoke.py` 执行真实模型→轨迹→独立PDM评分，再与原9条记录比较。默认要求轨迹与评分逐位相同；异机有差异时，先保存误差和环境，并检查权重、预处理、有效token/池化、精度、DDIM参数及软件版本，随后再决定可接受的复现容差。仅仅进程跑通不算数值复现。

## 3. 精确复现 +2.1519

该数值是 **navtest，12,146场景×5次采样=60,730输出**。Base为90.4793124745，选择后92.6311941034。方法按场景固定，但每次采样是否用该方法，由该次Base PDMS是否<70决定。

对场景x、噪声j和方法m，先定义：Base失败则使用m，否则保留Base；再用这5次的平均真实PDMS选择场景固定m（包括Base）。平局保留Base或先出现的方法。保留方法内部已有门控；已去门控的实际分支也独立纳入。**不是每个噪声分别挑最优方法，也不是无条件地把场景五次都改成同一分支。**

```bash
CUDA_VISIBLE_DEVICES=0 python -B run_teacher.py --paths paths.local.json \
  --cohort navtest --subset all --mode historical --allow-navtest \
  --seeds 0,1,2,3,4 --out outputs/historical --rank 0 --world-size 1
python -B assemble_scores.py --input outputs/historical --cohort navtest \
  --output outputs/historical_scores.npy
python -B verify_oracle.py --scores outputs/historical_scores.npy --out outputs/oracle
```

多卡时每个进程只暴露自己的单卡，设置 `--rank 0 ... N-1 --world-size N`，所有进程共享同一输出目录；没有写死32卡。不在同一输出目录改变方法/噪声/筛选协议。已完成场景可续跑；失败场景会保留异常，修正后复跑。

若拿到本地原评分矩阵，也可只运行最后的CPU复算，无需GPU或NAVSIM。完整原矩阵约40.8MB，保留在原工作区本地，不进GitHub。

## 4. 生成可蒸馏的跨噪声教师

历史规则对同一输入可能混用原始和修复接口，不能直接当作一个统一的VLM目标。本入口对每场景评估所有噪声下的**真实完整分支**，选择同一分支和同一接口表征：

```bash
CUDA_VISIBLE_DEVICES=0 python -B run_teacher.py --paths paths.local.json \
  --cohort navtrain --subset exploration --mode teacher \
  --seeds 0,1,2,3,4 --teacher-selection teacher_safe \
  --teacher-min-pdms 90 --out outputs/teacher_exploration \
  --rank 0 --world-size 1
```

- `teacher_safe`：要求每个噪声下PDMS不低于Base，且不新增碰撞、出界或零分，再按平均PDMS选分支，包含不修复Base。它是保守的首版规则，可在独立开发配置中比较其他规则。
- `teacher_consistent`：同一场景所有噪声统一选平均PDMS最高的实际分支，也包含Base；不带上述逐次保持约束。两种协议不能混报。
- 原来只在Base失败时计算的方法，在教师模式中会重新评估所有噪声；它们的新无条件输出不是历史已算结果。
- `teacher_eligible=true` 要求所选分支**每次最终PDMS严格>90**。不合格记录保留用于覆盖审计，不直接当优质监督。
- 原轨迹、评分、全部候选及选择索引保存在每场景 `branches.npz`。只对最终合格分支重放并保存 `teacher_interface.npz`，确认轨迹与该分支第一次生成逐位一致，避免存所有候选的大表征。
- 统一对齐点为 `action_head.feature_encoder` **输出**，FP32 `[有效token数,384]`，保留token IDs、原attention mask和原形状。不同上游位置的修复都通过各自剩余计算到达这个接口；投影后直接修复则保存修改后的实际接口。默认FP32，可显式选FP16并记录量化误差。
- 接口在动作噪声采样前产生，所选方法固定后只需一份接口目标；不同噪声的轨迹可以不同，不对它们作简单坐标平均。
- navtrain的 `exploration` 与 `validation` 以原采集会话划分。学生只用探索会话学习，验证集决定配方，navtest历史上限数据不进入训练。

## 5. 学生训练交接

仓库提供教师生成与数据格式，**尚未提供或验收学生训练器**。推荐首先用完全相同的teacher样本/轨迹和训练预算，比较：轨迹监督、轨迹+接口表征监督，再检查不同蒸馏权重与Base成功回放。

轨迹监督沿用RL Base动作头原有归一化、动作编码与扩散训练目标；接口损失在有效token上对齐，尺度仅用训练集校准。若对齐接口投影后表征，至少需要开放接口投影或VLM末层参数；仅更新DiT、冻结接口之前所有参数，无法通过该接口损失更新上游。

学生从同一RL Base初始化，推理时使用自己的正常前向，不需要PDMS、事后选择器或干预hook。最终比较新场景PDMS、失败修复、原成功损伤、碰撞/出界/零分和跨噪声表现。固定场景方法仅在已用噪声上的一致性属于教师诊断；新噪声与新场景泛化需要另外验证。

## 复核与版本

`reference/source_snapshot.json` 固定必要源码SHA；`reference/provenance.json` 固定11条历史策略来源；`reference/expected.json` 固定原上限数字；`reference/golden.json` 为旧保存轨迹而非新生成参考。`vendor/`保留原算法，`portable_common.py`只适配本地路径、任务缓存和种子入口。完整笛卡尔子空间搜索不需为这11种教师重新运行；扩大候选库需要独立协议。
