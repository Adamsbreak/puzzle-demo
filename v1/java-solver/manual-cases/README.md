# Manual Cases

这组样例是 `v1` 静态求解器的基础回归题库。

## 当前样例

- `tc01_multiple_legal_stops.json`
  同一方向多个合法停点
- `tc02_fixed_adjacent_blocks.json`
  被 `fixed` 紧邻阻挡
- `tc03_stop_mid_opens_path.json`
  中间停点改变后续可解性
- `tc04_large_piece_footprint.json`
  大物体整体 footprint 检查
- `tc05_horizontal_forbids_vertical.json`
  `horizontal` 禁止纵向移动
- `tc06_edge_goal_full.json`
  边缘 goal 的 `full`
- `tc06_edge_goal_partial.json`
  边缘 goal 的 `partial`
- `tc07_block_cannot_enter_edge_goal.json`
  `block` 不可进入边缘 goal
- `tc08_shortest_operation_count.json`
  BFS 最少操作步数
- `tc03_target_lane_priority.json`
  `target-lane` 最高优先级回归
- `tc07_edge_goal_last_step_only.json`
  边缘 goal 只放宽最后一步

## 一次跑完整组

在 [java-solver](/C:/Users/admin/Downloads/puzzle/v1/java-solver) 目录运行：

```powershell
.\manual-cases\run-manual-cases.ps1
```

## 单独运行

例如：

```powershell
Get-Content .\manual-cases\tc01_multiple_legal_stops.json -Raw | mvn -q exec:java
```

```powershell
Get-Content .\manual-cases\tc08_shortest_operation_count.json -Raw | mvn -q exec:java
```
