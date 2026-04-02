# Solver + Zone Architecture

## 核心判断

这个项目的求解本质上是路径规划，不应该把“静态求解器”和“动态求解器”拆成两套完全独立的系统。

更稳定的抽象是：

- 搜索框架始终只有一套，负责在状态图上做 BFS/最短路
- 静态与动态的差别，不在搜索器本身，而在“玩家动作之后，环境如何继续演化”
- 每个动态障碍物都可以看成一个状态函数的一部分

也就是说，真正的搜索节点应该是：

- 棋盘尺寸与固定格子
- 所有可交互物体的位置
- 运行时状态 `runtime`

其中 `runtime` 不只是风，还应该容纳：

- `tick`: 当前时间步
- `flags`: 额外规则开关
- `entities`: 动态障碍物或环境对象的内部状态

## 两类动态

### 1. 静态

玩家动作后，环境不再自动变化。

流程：

`玩家动作 -> 下一状态`

适合：

- 纯推箱
- 固定轨道移动
- 只依赖当前布局的谜题

### 2. 动态

玩家动作后，环境还会根据状态函数继续变化。

动态又可以分成两种推进方式：

- `settle`
  玩家动作后，环境持续结算，直到稳定
- `tick`
  玩家动作后，只推进一个离散时间步

适合：

- `settle`: 风推动、重力下落、滑冰直到停住、机关连锁
- `tick`: 周期运动、时间开关、巡逻障碍、节拍机关

## 统一接口

当前代码已经改成下面这个方向：

```ts
interface EnvironmentRule {
  id: string;
  mode: "settle" | "tick";
  step(state: PuzzleSnapshot): PuzzleSnapshot;
  isActive?(state: PuzzleSnapshot): boolean;
  isStable?(state: PuzzleSnapshot): boolean;
}

interface RuleEngine {
  mode: "static" | "settle" | "tick";
  deterministic: boolean;
  listPlayerActions(state: PuzzleSnapshot): SolverMove[];
  applyPlayerAction(state: PuzzleSnapshot, move: SolverMove): PuzzleSnapshot;
  advanceEnvironment?(state: PuzzleSnapshot): PuzzleSnapshot;
  isGoal(state: PuzzleSnapshot): boolean;
  serializeState(state: PuzzleSnapshot): string;
}
```

这里最关键的是 `advanceEnvironment`。

搜索器不再关心“这是风、重力还是巡逻敌人”，只关心：

1. 玩家走一步
2. 环境往后演化
3. 得到新的完整状态
4. 把这个状态继续放进搜索

## 为什么这更适合“状态函数”

你说的判断非常关键：动态障碍物本质上都有一个状态函数。

这个函数可能是：

- 只依赖自己和时间
  例子：每 4 tick 循环移动一次
- 依赖自己与其他障碍物的相互作用
  例子：被风吹动，但前方有挡板就停止
- 依赖额外规则状态
  例子：开关激活后改变可通行性

把这些都放进 `EnvironmentRule + runtime` 后，搜索器只需要把“完整状态”作为节点。

换句话说：

- 路径规划没有变
- 变的是状态转移函数更复杂了

## 当前实现策略

现在仓库里的实现已经做了这几件事：

- 保留原来的 BFS 搜索器
- 把风从“求解器特判”提升为一个 `EnvironmentRule`
- 引入统一的 `advanceEnvironment`
- 给 `runtime` 增加了 `tick / flags / entities`
- 支持先做 `settle`，再做 `tick`，必要时再做一次 `settle`

这意味着后面要扩展动态规则时，优先做的是：

1. 为新规则补一个 `EnvironmentRule`
2. 把它需要的状态放进 `runtime`
3. 在 `resolveEnvironmentRules` 里启用它

而不是再写一套新的求解器。

## 对后续建模的建议

如果接下来要正式支持“周期运动障碍物”或“交互触发障碍物”，推荐这样落：

- 把“障碍物的内部状态”放进 `runtime.entities`
- 把“是否开启、阶段、方向、剩余步数”等信息放进 `flags` 或实体 `data`
- 把“每一步如何更新实体状态和棋盘占用”写进 `EnvironmentRule.step`
- 如果规则是自动结算型，就补 `isStable`

这样静态、风、周期、联动都还能共用同一个求解器。
