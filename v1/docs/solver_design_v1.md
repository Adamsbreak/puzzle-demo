# Solver Design V1

这份文档定义 `v1` 当前阶段的求解器设计目标、规则边界、状态结构和后续扩展方向。

当前版本的定位是：

- 面向静态谜题
- 优先支持当前 `v1` 编辑器已经具备的元素
- 为 Node 桥接、Java 求解器和未来 AI 扩展提供统一规则语义

## 1. 目标

`v1` 的求解器第一阶段只解决静态谜题。

这里的“静态”指：

- 玩家执行一步操作
- 棋盘不会自动继续变化
- 没有风、重力、自动传送带、周期变化等环境结算

当前求解器目标：

- 判断谜题是否可解
- 给出最少操作步数的解
- 与编辑器验证模式共用同一套合法移动语义

当前不纳入第一阶段：

- 风
- 重力
- 自动机关
- 开关连锁
- 自动传送带推进
- 随机性

## 2. 系统边界

求解器不直接操作 UI。

三层职责应保持分离：

- UI 层
  负责拖拽、红框/绿框预览、步骤展示
- 规则层
  负责判断这一步是否合法、是否到达终点
- 求解器层
  负责搜索最优解

这意味着：

- 红框/绿框本身不属于求解器
- 但红框/绿框依赖的合法性判断必须和求解器共用

## 3. 当前技术结构

当前 `v1` 已经形成了下面这条链路：

- 前端页面负责谜题设计与验证
- Node 作为本地桥接层
- Java 作为求解器核心

对应位置：

- 页面入口：[index.html](/C:/Users/admin/Downloads/puzzle/v1/index.html)
- Node 桥接：[server.mjs](/C:/Users/admin/Downloads/puzzle/v1/node-bridge/server.mjs)
- Java 求解器：[StaticSolver.java](/C:/Users/admin/Downloads/puzzle/v1/java-solver/src/main/java/com/puzzle/v1/StaticSolver.java)
- 规则说明：[static_solver_rules.md](/C:/Users/admin/Downloads/puzzle/v1/docs/static_solver_rules.md)

## 4. 谜题状态

一个求解状态至少包含：

- 棋盘尺寸
- 每个格子的标签
- 所有物体的位置、尺寸、类型、移动规则
- 所有区域的位置、尺寸、角色
- 终点判定模式

当前静态版不需要记录：

- 时间相位
- 回合数
- 环境状态
- 机关状态

可以抽象成：

```ts
type PuzzleState = {
  board: BoardState
  pieces: PieceState[]
  zones: ZoneState[]
}
```

## 5. 基础元素

### 5.1 格子标签

当前静态版基础格子标签：

- `free`
- `blocked`
- `horizontal`
- `vertical`
- `target-lane`
- `block-lane`

格子允许多标签共存。

### 5.2 物体类型

当前基础物体类型：

- `target`
- `block`
- `fixed`

定义如下：

- `target`
  目标物，可触发终点判定
- `block`
  可移动障碍物
- `fixed`
  固定障碍物，不可移动

### 5.3 区域类型

当前求解器关注两类区域：

- `spawn`
- `goal`

`goal` 同时支持：

- 内部矩形终点
- 边缘终点

## 6. 终点判定

当前终点模式支持两种：

- `full`
- `partial`

定义如下：

- `full`
  目标物必须完整进入终点区域
- `partial`
  目标物只要部分进入终点区域即可

这两种模式都适用于：

- 内部终点
- 边缘终点

示例：

- `2x2` 目标物进入 `1x2` 边缘终点
- 在 `full` 下不成立
- 在 `partial` 下成立

## 7. 移动规则

### 7.1 基础规则

一次操作只移动一个物体，并且：

- 只能沿单一方向移动
- 不能斜向移动
- 不能与其他物体重叠
- 不能进入 `blocked`
- `fixed` 不可移动

### 7.2 大物体规则

大于 `1x1` 的物体必须作为整体移动。

这意味着：

- 不允许拆分
- 不允许旋转
- 移动和碰撞都以整体 footprint 为单位计算

### 7.3 操作定义

当前求解器的“一步”建议定义为：

- 某个物体沿某个方向移动到一个合法停点

而不是：

- 只移动一格

这样更接近玩家理解的“操作步数”，也更适合后续展示“最优步骤”。

## 8. 轨道规则

### 8.1 普通运动轨道

普通运动轨道包括：

- `horizontal`
- `vertical`

含义：

- `horizontal`
  物体在这里优先按横向移动
- `vertical`
  物体在这里优先按纵向移动

### 8.2 角色专属轨道

角色专属轨道包括：

- `target-lane`
- `block-lane`

含义：

- `target-lane`
  主要约束目标物
- `block-lane`
  主要约束障碍物

### 8.3 轨道优先级

当前静态版的优先级约定为：

1. 对 `target` 来说，`target-lane` 优先级最高
2. 对非 `target` 物体来说，普通运动轨道优先
   即 `horizontal / vertical`
3. 角色专属轨道其次
   即 `block-lane`
4. 未标记格最后

举例：

- 如果目标物处在 `target-lane + horizontal` 的交汇格
- 应优先遵守 `target-lane`

- 如果障碍物处在 `block-lane + vertical` 的交汇格
- 应优先遵守 `vertical`

## 9. 边缘终点规则

边缘终点不是普通棋盘外区域，而是对匹配目标物开放的延伸合法区域。

规则如下：

- 只有被定义为边缘 `goal zone` 的外圈区域可进入
- 只有匹配的目标物可进入
- 障碍物不能进入边缘终点
- 其他边缘外区域仍然不可进入

额外规则：

- 目标物进入边缘终点的最后一步，不应因为普通轨道标签缺失而被阻挡

这样可以保证：

- 目标轨道连接到出口时
- 最后一步可以正常进入边缘终点区

## 10. 求解器共用接口

无论最终求解器是 JS、Java 还是以后别的语言，都应该复用同一组规则语义。

建议统一成下面三类接口：

### 10.1 放置是否合法

```ts
canOccupyFootprint(state, piece, row, col, width, height)
```

负责：

- 是否越界
- 是否重叠
- 是否进入 `blocked`
- 是否允许进入边缘终点

### 10.2 移动是否合法

```ts
canMovePiece(state, piece, row, col, fromRow, fromCol)
```

负责：

- 方向是否合法
- 是否符合普通轨道规则
- 是否符合目标轨道或障碍物轨道
- 是否允许目标物进入边缘终点

### 10.3 是否达成终点

```ts
evaluateGoals(state)
```

负责：

- 内部终点判定
- 边缘终点判定
- `full / partial` 判定

### 10.4 规则包扩展接口

为了后续接入新的规则、配置位和 AI agent，`v1` 基础层预留了统一接口入口。

当前规则包中的求解器配置建议通过下面这些字段表达：

```ts
solver: {
  behavior: {
    targetLanePriority: "absolute",
    edgeGoalRelaxation: "final-step-only",
    stopGeneration: "all-legal-stops"
  },
  interfaces: {
    movePolicy: "static-v1",
    goalPolicy: "static-v1",
    validator: "static-v1"
  },
  extensionConfig: {}
}
```

含义：

- `behavior`
  当前规则的固定语义
- `interfaces`
  当前规则包绑定了哪一套实现接口
- `extensionConfig`
  将来为 AI agent 或自定义规则预留的附加配置

基础层当前预留了这三类可注册接口：

- `movePolicies`
- `goalPolicies`
- `validators`

对应入口在：

- [contracts.js](/C:/Users/admin/Downloads/puzzle/v1/foundation/core/contracts.js)

后续无论是你手动扩展，还是 AI agent 生成新规则，最好都通过这些接口绑定，而不是直接改搜索主循环。

## 11. 搜索模型

当前静态求解器使用 BFS。

核心结构：

- 状态：`PuzzleState`
- 动作：枚举所有合法移动
- 转移：执行一步移动得到新状态
- 目标：`evaluateGoals(state).solved === true`
- 去重：序列化状态

当前优化目标：

- 最少操作步数

不是：

- 最少移动格数
- 最短欧式距离
- 最少时间

## 12. 校验与求解的区别

需要明确区分：

### 12.1 结构校验

负责检查：

- 是否有目标物
- 是否有终点
- 谜题结构是否合法

它不回答：

- 是否一定可解

### 12.2 求解

负责回答：

- 是否可解
- 最优步骤是什么

这两者不能混用。

## 13. 当前实现路线

当前推荐的实现路线已经明确：

- 前端继续负责设计器和验证模式
- Node 继续作为桥接层
- Java 继续作为正式求解器

这样做的好处：

- 前端不需要直接管 Java 进程
- Node 可以统一承接未来 AI、图片识别和 Java 调用
- Java 专注在搜索性能和求解规则实现

## 14. 后续扩展原则

如果后面加入新规则，不应直接推翻当前架构。

### 14.1 开关

如果加入开关，主要扩展：

- 运行时状态
- 状态转移
- 状态序列化

影响会是中等，但不应该重写搜索框架。

### 14.2 传送带

如果传送带是静态跳转型：

- 可作为状态转移扩展继续接入

如果传送带是自动推进型：

- 就会从静态求解升级到“玩家动作 + 环境结算”模式

这会要求扩展：

- 状态推进接口
- 结算逻辑
- 循环检测

但仍然不需要推翻整个求解器。

## 15. 当前阶段结论

`v1` 当前最合理的路线是：

1. 固定静态求解规则
2. 用小样例逐条验证规则
3. 修正 Java 求解器实现
4. 后续再扩展开关、传送带和 AI

一句话总结：

当前阶段求解器最重要的不是继续加功能，而是把“静态谜题规则”固定成统一标准，并让前端验证、Node 桥接和 Java 求解器都严格对齐这套标准。
