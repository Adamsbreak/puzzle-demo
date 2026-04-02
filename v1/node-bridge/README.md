# Puzzle V1 Node Bridge

这个目录提供 `v1` 网页和求解器之间的本地 Node 桥接层。

当前默认链路是：

- 网页导出当前谜题 JSON
- 浏览器通过 `fetch()` 调用本地 Node 服务
- Node 优先调用 Java 求解器
- 如果 Java 调用失败，Node 回退到内置 JS 静态 BFS

## 启动

```powershell
cd C:\Users\admin\Downloads\puzzle\v1\node-bridge
npm start
```

默认地址：

- `http://127.0.0.1:3210/health`
- `http://127.0.0.1:3210/solve`

## 接口

### `GET /health`

返回桥接层当前状态和当前求解引擎。

### `POST /solve`

请求体：

```json
{
  "puzzleSpec": {},
  "rulePack": {}
}
```

响应体：

```json
{
  "status": "solved",
  "summary": "Solved with the minimum number of operations.",
  "exploredNodes": 12,
  "stepCount": 3,
  "steps": []
}
```

## 当前求解引擎

默认是 `java`。

也可以通过环境变量切换：

```powershell
$env:PUZZLE_SOLVER_ENGINE='builtin'
node server.mjs
```

可选值：

- `java`
- `builtin`

## Java 调用方式

Node 会在 [java-solver](C:\Users\admin\Downloads\puzzle\v1\java-solver) 目录里执行：

```powershell
mvn -q exec:java
```

然后把 `PuzzleRequest` JSON 写入标准输入，再读取 `PuzzleResponse` JSON。

## 回退逻辑

如果 Java 求解器启动失败、超时或返回非法 JSON，Node 会自动回退到内置 JS 求解器，并在响应里的 `transport` 字段注明原因。
