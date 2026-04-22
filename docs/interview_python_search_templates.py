from collections import deque
import heapq


def restore_path(parent, end_state):
    path = []
    cur = end_state
    while parent[cur][0] is not None:
        prev_state, move = parent[cur]
        path.append(move)
        cur = prev_state
    path.reverse()
    return path


def bfs_shortest_path(start, is_goal, neighbors, max_nodes=30000):
    queue = deque([start])
    parent = {start: (None, None)}
    explored = 0

    while queue:
        state = queue.popleft()
        explored += 1

        if is_goal(state):
            return {
                "found": True,
                "steps": restore_path(parent, state),
                "explored": explored,
            }

        if explored >= max_nodes:
            return {"found": False, "steps": [], "explored": explored, "truncated": True}

        for next_state, move in neighbors(state):
            if next_state in parent:
                continue
            parent[next_state] = (state, move)
            queue.append(next_state)

    return {"found": False, "steps": [], "explored": explored, "truncated": False}


def astar_shortest_path(start, is_goal, neighbors, heuristic, max_nodes=30000):
    h0 = heuristic(start)
    heap = [(h0, h0, 0, 0, start, None)]
    best_g = {start: 0}
    parent = {start: (None, None)}
    explored = 0
    order = 0

    while heap:
        f, h, g, _, state, last_move = heapq.heappop(heap)
        if g > best_g.get(state, float("inf")):
            continue

        explored += 1
        if is_goal(state):
            return {
                "found": True,
                "steps": restore_path(parent, state),
                "explored": explored,
            }

        if explored >= max_nodes:
            return {"found": False, "steps": [], "explored": explored, "truncated": True}

        for next_state, move in neighbors(state):
            next_g = g + 1
            if next_g >= best_g.get(next_state, float("inf")):
                continue

            best_g[next_state] = next_g
            parent[next_state] = (state, move)
            next_h = heuristic(next_state)
            order += 1
            heapq.heappush(
                heap,
                (next_g + next_h, next_h, next_g, order, next_state, move),
            )

    return {"found": False, "steps": [], "explored": explored, "truncated": False}


def freeze_positions(pieces, runtime=None):
    runtime = runtime or {}
    pieces_key = tuple(sorted((p["id"], p["row"], p["col"]) for p in pieces))
    runtime_key = tuple(sorted(runtime.items()))
    return pieces_key, runtime_key


def grid_bfs_example(grid, start, target):
    rows, cols = len(grid), len(grid[0])
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    def is_goal(state):
        return state == target

    def neighbors(state):
        r, c = state
        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] != "#":
                yield (nr, nc), (nr, nc)

    return bfs_shortest_path(start, is_goal, neighbors)


"""
面试速记：

1. BFS 模板
   - queue 用 deque
   - visited / parent 去重
   - 每次弹出一个状态，扩展所有邻居
   - BFS 天然保证第一次到终点就是最短步数

2. A* 模板
   - heap 用 heapq
   - 堆里放 (f, h, g, order, state)
   - f = g + h
   - best_g[state] 记录当前找到的最小代价
   - 如果启发式 h=0，A* 就退化成 Dijkstra

3. 你的项目怎么套进来
   - state: 用“所有 piece 的位置”做成可哈希元组
   - neighbors(state): 对应你现在的 listLegalMoves + applyMove
   - is_goal(state): 对应你现在的 isSolvedState
   - visited key: 对应你现在的 serializeState

4. 你当前仓库对应关系
   - TS BFS: src/core/solver.ts
   - Java A*: v1/java-solver/src/main/java/com/puzzle/v1/StaticSolver.java
"""
