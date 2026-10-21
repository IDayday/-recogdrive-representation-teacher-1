# 两条表征观察路线：最终状态

**均已按正确定义完成并验收，没有待续跑计算。** 正式报告为`../doc/work-output/1016-rl_representation_analysis/representation_observation.html`，完整验收为`provenance/TWO_ROUTE_FINAL_VERIFICATION.json`，具体完成矩阵见PLAN末尾及报告。

路线一使用全103288个自然S0输出：90153高质量、2288失败、10847中间。2个DLC各16卡精确重放，全部轨迹与原S0一致；提取五步×19阶段×8token，760单元真实类别SVD/残差、共同坐标分布、连续PDMS和1520项会话级FDR已完成。拟合74900自然成功/1850失败，留出15253成功/438失败，中间全部用于连续质量。数据与结果`runs/natural_s0_repr_20261016T080905Z/`、`analysis/natural_route1_v1/`。

路线二使用2288个失败与GT配对续采的45760候选，原GT<=90不预筛；最终<70/>90后作差分SVD和配对残差。均值、协方差、重叠、绝对与场景内连续质量、独立碰撞/出界/TTC空间和跨类噪声迁移均完成。进度类仅1个有效探索对，覆盖不足已如实记录。数据与结果`runs/paired_formal_20261016T0728Z/`、`analysis/observation_v1/`、`analysis/paired_route2_completion_v2/`、`analysis/temporal_v1/`。

原先把路线二全部候选的global_class_residual误归路线一，现已更正；它仍是路线二内部候选池对照。旧报告和范围声明归档于`provenance/route-definition-correction/`。

32个自然捕获进程退出0，两个新DLC与Pods均Succeeded/exit0；全部原始分块hash及moments交叉验收通过。监控89752、投影/评价57027、配对补齐37377、最终审计32146均已结束。初版CPU投影路径类型错误记录保留，仅后两阶段由v2接续，未重跑采集/合并/SVD。

下一轮只以用户新指令推进，不自动训练或干预表征。
