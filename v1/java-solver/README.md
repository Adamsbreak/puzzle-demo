# Java Solver

这个目录是 `v1` 的 Java 求解器工程。

当前状态：

- 已有 Maven 工程骨架
- 已有 JSON 输入输出契约
- 已有 `SolverMain` 标准输入/输出入口
- 已实现第一版静态 BFS 求解器

## 目录

- [pom.xml](/C:/Users/admin/Downloads/puzzle/v1/java-solver/pom.xml)
- [request-example.json](/C:/Users/admin/Downloads/puzzle/v1/java-solver/request-example.json)
- [SolverMain.java](/C:/Users/admin/Downloads/puzzle/v1/java-solver/src/main/java/com/puzzle/v1/SolverMain.java)
- [StaticSolver.java](/C:/Users/admin/Downloads/puzzle/v1/java-solver/src/main/java/com/puzzle/v1/StaticSolver.java)
- [PuzzleRequest.java](/C:/Users/admin/Downloads/puzzle/v1/java-solver/src/main/java/com/puzzle/v1/model/PuzzleRequest.java)
- [PuzzleResponse.java](/C:/Users/admin/Downloads/puzzle/v1/java-solver/src/main/java/com/puzzle/v1/model/PuzzleResponse.java)
- [SolutionStep.java](/C:/Users/admin/Downloads/puzzle/v1/java-solver/src/main/java/com/puzzle/v1/model/SolutionStep.java)

## 当前能力

第一版 Java 求解器已经支持：

- 静态谜题
- 最少操作步数 BFS
- 内部终点
- 边缘终点
- `full / partial` 终点判定
- 目标物与障碍物共同参与搜索
- 目标轨道、障碍物轨道、横向/纵向轨道

## 输入输出方式

推荐保持这一条链路：

1. 网页导出 `PuzzleRequest` JSON
2. Node 桥接层调用 Java 程序
3. Java 从标准输入读取 JSON
4. Java 把 `PuzzleResponse` JSON 输出到标准输出

## 运行方式

等你本机装好 `Java 17+` 和 `Maven` 之后，可以在这个目录里运行：

```powershell
cd C:\Users\admin\Downloads\puzzle\v1\java-solver
mvn -q -DskipTests compile
mvn -q exec:java < request-example.json
```

## 说明

这台当前开发机器上还没有安装 `java` 和 `mvn`，所以这次我已经完成了代码迁移，但还没法在本机实际编译验证。
