# Java Solver Contract

这个文档定义 `v1` 网页侧和 Java 求解器之间的最小契约。

## 请求

网页侧传给 Java 的 JSON 顶层结构：

```json
{
  "meta": {},
  "rulePack": {},
  "board": {},
  "pieces": [],
  "zones": []
}
```

关键字段：

- `meta.title`
- `meta.rulePackId`
- `rulePack.solver.maxNodes`
- `board.rows`
- `board.cols`
- `board.cells[*][*].tags`
- `pieces[*].row / col / w / h / role / moveRule / movable`
- `zones[*].role / shapeKind / row / col / side / index / w / h / goalMode / targetFilter`

## 响应

Java 返回：

```json
{
  "status": "solved | no-solution | invalid-puzzle | not-implemented",
  "summary": "string",
  "rulePackId": "basic-static",
  "puzzleTitle": "example",
  "exploredNodes": 12,
  "stepCount": 3,
  "steps": [
    {
      "pieceId": "p1",
      "pieceName": "T",
      "direction": "right",
      "fromRow": 0,
      "fromCol": 0,
      "toRow": 0,
      "toCol": 2
    }
  ]
}
```
