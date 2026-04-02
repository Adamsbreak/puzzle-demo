# Puzzle V1

`v1` 是新的第一阶段重构目录，目标是先稳定支持静态谜题的设计、校验和后续扩展。

## 打开方式

这版使用普通脚本，不依赖模块加载，理论上可以直接双击打开：

- [index.html](C:\Users\admin\Downloads\puzzle\v1\index.html)

如果你已经在项目根目录启动了本地服务，也可以访问：

- [http://127.0.0.1:8000/v1/index.html](http://127.0.0.1:8000/v1/index.html)

## 三层结构

- `foundation/`
  基础层。这里放状态模型、运行时、求解器适配器、UI 框架。默认只由维护者修改。
- `rulepacks/`
  规则包层。当前内置了一套基础静态规则包，后面也可以继续添加外部规则包。
- `ai/`
  AI 预留层。现在只保留安全接口，未来 AI 应该通过这里生成规则包草稿或扩展草稿，而不是直接改基础层。

## 当前内置内容

- 一个可打开的网页入口
- 一套基础静态规则包
- 一个求解器占位适配器
- 一套基础 UI 壳

## 求解器接口

当前 `foundation/solver/adapter.js` 只是占位层，故意不写具体算法，方便你后面替换成 Java 或 Python。

推荐接法：

1. 保留网页和规则包在 `v1`
2. 用 Java 或 Python 实现独立求解核心
3. 通过本地接口或子进程把结果回传给网页
4. 只替换 `foundation/solver/adapter.js` 这一层，不改基础 UI 和规则包结构

## 后续建议

- 先继续完善静态规则包 schema
- 再让 UI 逐步变成“由规则包驱动”
- 求解器等规则包接口稳定后再接入 Java / Python 实现

## Java 求解器骨架

现在已经补了一套 Java 骨架，在：

- [README.md](/C:/Users/admin/Downloads/puzzle/v1/java-solver/README.md)
- [pom.xml](/C:/Users/admin/Downloads/puzzle/v1/java-solver/pom.xml)
- [SolverMain.java](/C:/Users/admin/Downloads/puzzle/v1/java-solver/src/main/java/com/puzzle/v1/SolverMain.java)
- [StaticSolver.java](/C:/Users/admin/Downloads/puzzle/v1/java-solver/src/main/java/com/puzzle/v1/StaticSolver.java)
- [java_solver_contract.md](/C:/Users/admin/Downloads/puzzle/v1/docs/java_solver_contract.md)

这一版先把：
- Maven 工程
- 输入输出 JSON 契约
- Java 主入口
- 静态求解器占位类

都搭起来了，后面可以逐步把当前 JS BFS 迁到 Java。

## Static Solver Rules

- [static_solver_rules.md](/C:/Users/admin/Downloads/puzzle/v1/docs/static_solver_rules.md)
## Node Bridge

- [README.md](/C:/Users/admin/Downloads/puzzle/v1/node-bridge/README.md)
- [server.mjs](/C:/Users/admin/Downloads/puzzle/v1/node-bridge/server.mjs)
- [static-solver.mjs](/C:/Users/admin/Downloads/puzzle/v1/node-bridge/lib/static-solver.mjs)
