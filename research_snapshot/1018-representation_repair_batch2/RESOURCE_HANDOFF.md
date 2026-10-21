## 最新资源收尾（2026-10-21北京时间，优先于下方历史）

用户明确仅释放self_0 `dlcrnshl7t4hcmoy` 与self_1 `dlcrxs2yz4ime2fe`，两台已在各44个worker安全落盘边界收尾后回读确认Stopped。其他运行节点及三个排队替补保留、共享队列开放。共享控制面现位于replacement_a1 `dlclfqx3fyywxyw3`，读取 `runs/discovery_v1/control_plane/LIVE.json` 的当前PID和migration_proof；不要沿用旧self_0控制进程。完整收尾与证据见 [RESOURCE_RELEASE_20261021.md](RESOURCE_RELEASE_20261021.md)。本批正式交付及冻结报告未变。

## 当前交付后资源状态（2026-10-21北京时间，优先于历史）

本批正式交付已完成，见STUDY_COMPLETE.md；节点和原开放队列保留，不StopJob、不释放、不停DLC主进程。完成时self0/self1/B2运行、共48物理卡；5个替补排队。只有B2无替补，其余严格按resources/replacements/20261020/FINAL_FIVE_NODE_REPLACEMENT_MAP.json按用户及原node-dir匹配。A1/A2/B1已平台72h到期、此前全部科学分片验收，不能重启旧worker。实时状态及剩余时限读resources/CLOUD_LATEST.json，不能沿用历史卡数。资源guard和DLC控制面继续记录，后续计算前复核实际多卡验收；不自动开始蒸馏。

# 第二批实验资源接续

记录日期：2026-10-18（北京时间）。第二批已在peer_a1／peer_a2／peer_b1三个既有节点启动，48卡工程验收通过；另三个节点排队。实时状态及剩余时限以resources/CLOUD_LATEST.json为准。

## 本人配额：已确认排队

当前身份来自DSW自动刷新的实例角色；地域 `cn-wulanchabu`，工作空间 `245760`，配额 `quotachw9oq5rg02`。GetJob已核验两个作业属于本人，未使用师兄凭据。

| 节点 | Job ID | 最新核验状态 | 配置 | 上限 |
| :---: | :--- | :---: | :---: | :---: |
| self node0 | dlcrnshl7t4hcmoy | Queuing | 1节点／16卡 | 4320分钟／72小时 |
| self node1 | dlcrxs2yz4ime2fe | Queuing | 1节点／16卡 | 4320分钟／72小时 |

两作业创建时间均为 `2026-10-17T20:34:44Z`；排队状态核验时间见各自CLOUD_STATUS。尚无运行开始时间、Pod或容器内验收，不能将提交成功称为节点已经可计算。平台负责后续自动调度，启动后进入常驻等待。

本次120小时请求被平台明确拒绝：`Workspace[245760] has enforced 4320min max running time`。用户随后明确回复“允许，先按72小时提交排队（推荐）”，先授权这两个作业使用72小时；用户随后已修改研究AGENTS，全部后续作业统一为72小时。原请求及拒绝记录保留在 `resources/self_20261017T203341Z/`。

生效请求、提交返回及云端回读在 `resources/self_20261017T203441Z/`，入口指针为 [resources/LATEST.json](resources/LATEST.json)。两个作业均回读核验了账号、挂载、16卡、运行时限与 `JobReservedMinutes=0`。

## 其余四个节点

以下节点均已通过当前实例角色实时GetJob核验；三个运行节点已通过可连接终端启动独立第二批程序。最新云端回读保存在resources/CLOUD_LATEST.json：

| Job ID | 用户报告状态 |
| :--- | :---: |
| dlcb46akrk2hji1u | Running |
| dlcgxxrm3yape59d | Running |
| dlcqdtslnqnytsc7 | Running |
| dlcwhkv0rt5t8crx | Queuing |

既有实例及原常驻主进程均保留，第二批使用独立代码与输出。本批合计目标为6节点：当前3个运行、3个排队；节点列表、设备及并发由resources/NODES.json配置。

## 后续操作

只查询本人两个新作业，不创建或停止实例：

```bash
python3 -u -B /mnt/workspace/ReCogDrive/1018-representation_repair_batch2/code/dlc_reserve_v2.py status
```

使用 `dlc_reserve_v2.py` 查询已提交的72小时作业；原 `dlc_reserve.py` 保留120小时请求实现与对应溯源。已提交记录防止重复创建，后续扩容须使用独立新身份。

容器启动入口为 `code/dlc_resident.py`，不自动加载模型或领取第一批队列。`node*/LIVE.json` 提供共享心跳，`node*/runtime/<job>/STARTUP.json` 提供容器、Python、挂载及CPU信息；运行身份须与SUBMITTED中的Job ID一致。默认60秒心跳，容器主进程常驻，不自动释放。

后续可在每节点独立的 `commands/pending/` 放置任务目录内脚本的运行请求：`expected_job`、相对 `code/` 脚本路径、`source_sha256` 和字符串 `arguments` 列表。运行器核验身份与源码指纹后执行，日志、领取回执及退出状态留在同节点commands目录。新程序启动前仍须完成实际卡数、依赖、真实模型推理→独立评分→落盘及多卡冒烟。

分配资源之后继续监控总运行时限；等待与接续程序不会重置作业额度。未经用户同意，不停止主进程或主动释放节点。第二批重计算正在运行；r2_resources.py以60秒轮询云端状态并自动接入新节点，r2_wait.py监控计算完成／异常，均使用工具托管后台终端。
