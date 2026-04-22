"""
Python translation of `src/core/solver.ts` for interview study.

This file is intentionally written as a teaching version:
- it keeps the same solver stages as the TypeScript code
- it adds comments explaining why each step exists
- it uses plain dict/list data so it feels close to JS/TS objects

Recommended reading order:
1. `serialize_state`
2. `list_legal_moves`
3. `apply_move`
4. `solve_puzzle`
5. environment helpers such as `step_wind` / `settle_until_stable`
"""

from __future__ import annotations

from copy import deepcopy


DIRECTION_DELTAS = {
    "north": {"dr": -1, "dc": 0},
    "south": {"dr": 1, "dc": 0},
    "west": {"dr": 0, "dc": -1},
    "east": {"dr": 0, "dc": 1},
}


def clone_puzzle_state(state):
    """
    Equivalent to TS `clonePuzzleState`.

    Why clone?
    Search algorithms must treat old states as immutable snapshots.
    If we modify the current state in place, the queue/visited states
    will all be corrupted.
    """

    return deepcopy(state)


def get_cell(state, row, col):
    if row < 0 or row >= state["rows"]:
        return None
    if col < 0 or col >= state["cols"]:
        return None
    return state["cells"][row][col]


def overlap(piece_a, piece_b):
    return not (
        piece_a["col"] + piece_a["w"] <= piece_b["col"]
        or piece_b["col"] + piece_b["w"] <= piece_a["col"]
        or piece_a["row"] + piece_a["h"] <= piece_b["row"]
        or piece_b["row"] + piece_b["h"] <= piece_a["row"]
    )


def in_bounds(state, row, col, width, height):
    return (
        row >= 0
        and col >= 0
        and row + height <= state["rows"]
        and col + width <= state["cols"]
    )


def matches_zone_filter(piece, zone):
    """
    The current TS rules allow a goal zone to optionally restrict
    which piece can enter.
    """

    target_filter = zone.get("targetFilter")
    if not target_filter:
        return piece["role"] == "target"

    piece_ids = target_filter.get("pieceIds") or []
    if piece_ids and piece["id"] not in piece_ids:
        return False

    piece_roles = target_filter.get("pieceRoles") or []
    if piece_roles and piece["role"] not in piece_roles:
        return False

    return True


def piece_inside_rect_zone(piece, zone):
    zone_row = zone.get("row", 0)
    zone_col = zone.get("col", 0)
    return (
        piece["row"] >= zone_row
        and piece["col"] >= zone_col
        and piece["row"] + piece["h"] <= zone_row + zone["h"]
        and piece["col"] + piece["w"] <= zone_col + zone["w"]
    )


def rect_matches_edge_goal_placement(state, rect, zone):
    """
    The main TS solver allows target pieces to extend outside the board
    only when the destination matches an edge goal zone.
    """

    index = zone.get("index", 0)

    if zone.get("side") == "left":
        return (
            rect["col"] < 0
            and rect["row"] >= index
            and rect["row"] + rect["h"] <= index + zone["h"]
        )

    if zone.get("side") == "right":
        return (
            rect["col"] + rect["w"] > state["cols"]
            and rect["row"] >= index
            and rect["row"] + rect["h"] <= index + zone["h"]
        )

    if zone.get("side") == "top":
        return (
            rect["row"] < 0
            and rect["col"] >= index
            and rect["col"] + rect["w"] <= index + zone["w"]
        )

    return (
        rect["row"] + rect["h"] > state["rows"]
        and rect["col"] >= index
        and rect["col"] + rect["w"] <= index + zone["w"]
    )


def matches_edge_goal_placement(state, piece, row, col, width, height):
    if piece["role"] != "target":
        return False

    rect = {
        **piece,
        "row": row,
        "col": col,
        "w": width,
        "h": height,
    }

    for zone in state["zones"]:
        if zone["role"] != "goal":
            continue
        if zone["shapeKind"] != "edge":
            continue
        if not matches_zone_filter(piece, zone):
            continue
        if rect_matches_edge_goal_placement(state, rect, zone):
            return True
    return False


def cell_allows(state, piece, row, col, dx, dy):
    """
    This mirrors `src/core/rules.ts`.

    Meaning:
    - blocked cells are forbidden
    - target pieces may use `free` or `target-zone`
    - horizontal/vertical tags constrain movement direction
    """

    cell = get_cell(state, row, col)
    tags = set((cell or {}).get("tags", []))

    if "blocked" in tags:
        return False

    has_free = "free" in tags
    if piece["role"] == "target" and not has_free and "target-zone" not in tags:
        return False

    if has_free:
        return True

    if piece["moveRule"] == "free":
        return True

    has_horizontal = "horizontal" in tags
    has_vertical = "vertical" in tags

    if has_horizontal and not has_vertical and dy != 0:
        return False
    if has_vertical and not has_horizontal and dx != 0:
        return False

    return True


def can_place(state, piece, row, col, width=None, height=None, ignore_id=None):
    """
    This is the core legality check.

    BFS itself is simple.
    The hard part in puzzle questions is usually here:
    "from one state, which next states are legal?"
    """

    width = piece["w"] if width is None else width
    height = piece["h"] if height is None else height
    ignore_id = piece["id"] if ignore_id is None else ignore_id

    inside_board = in_bounds(state, row, col, width, height)
    if not inside_board and not matches_edge_goal_placement(state, piece, row, col, width, height):
        return False

    dx = col - piece["col"]
    dy = row - piece["row"]

    if inside_board:
        for next_row in range(row, row + height):
            for next_col in range(col, col + width):
                if not cell_allows(state, piece, next_row, next_col, dx, dy):
                    return False

    if piece["moveRule"] == "blocked" and (dx or dy):
        return False
    if piece["moveRule"] == "horizontal" and dy:
        return False
    if piece["moveRule"] == "vertical" and dx:
        return False

    candidate_rect = {
        **piece,
        "row": row,
        "col": col,
        "w": width,
        "h": height,
    }

    for other_piece in state["pieces"]:
        if other_piece["id"] == ignore_id:
            continue
        if overlap(candidate_rect, other_piece):
            return False

    return True


def piece_matches_zone(state, piece, zone):
    if zone["shapeKind"] == "rect":
        return piece_inside_rect_zone(piece, zone)
    return rect_matches_edge_goal_placement(state, piece, zone)


def piece_on_target_tagged_cells(state, piece):
    """
    In the current TS solver, if there is no explicit goal zone but the board
    contains `target-zone`, a target can also be considered solved when all of
    its covered cells are on `target-zone`.
    """

    for row in range(piece["row"], piece["row"] + piece["h"]):
        for col in range(piece["col"], piece["col"] + piece["w"]):
            cell = get_cell(state, row, col)
            tags = set((cell or {}).get("tags", []))
            if "target-zone" not in tags:
                return False
    return True


def has_target_cells(state):
    for row in state["cells"]:
        for cell in row:
            if "target-zone" in cell.get("tags", []):
                return True
    return False


def is_solved_state(state):
    """
    Goal test used by BFS.

    In every search question, remember this separation:
    - BFS decides *how* to search
    - is_goal decides *when to stop*
    """

    targets = [piece for piece in state["pieces"] if piece["role"] == "target"]
    if not targets:
        return False

    goal_zones = [zone for zone in state["zones"] if zone["role"] == "goal"]

    for piece in targets:
        matching_zones = [zone for zone in goal_zones if matches_zone_filter(piece, zone)]
        if matching_zones:
            if not any(piece_matches_zone(state, piece, zone) for zone in matching_zones):
                return False
        elif has_target_cells(state):
            if not piece_on_target_tagged_cells(state, piece):
                return False
        else:
            return False

    return True


def serialize_state(state):
    """
    This is the visited-set key.

    BFS must de-duplicate states, or it will revisit the same board over and over.
    The current TS solver uses:
    - all piece positions
    - runtime state
    """

    pieces_key = "|".join(
        sorted(f'{piece["id"]}:{piece["row"]},{piece["col"]}' for piece in state["pieces"])
    )
    runtime_key = str(state.get("runtime", {}))
    return f"{pieces_key}#{runtime_key}"


def build_move(piece, next_row, next_col, direction):
    return {
        "pieceId": piece["id"],
        "pieceName": piece["name"],
        "fromRow": piece["row"],
        "fromCol": piece["col"],
        "toRow": next_row,
        "toCol": next_col,
        "direction": direction,
    }


def candidate_directions(piece):
    if piece["moveRule"] == "blocked":
        return []
    if piece["moveRule"] == "horizontal":
        return ["west", "east"]
    if piece["moveRule"] == "vertical":
        return ["north", "south"]
    return ["north", "south", "west", "east"]


def list_legal_moves(state):
    """
    Equivalent to TS `listLegalMoves`.

    Interview summary:
    - enumerate each movable piece
    - enumerate each legal direction
    - if the destination is legal, add it as a neighbor
    """

    moves = []
    for piece in state["pieces"]:
        for direction in candidate_directions(piece):
            delta = DIRECTION_DELTAS[direction]
            next_row = piece["row"] + delta["dr"]
            next_col = piece["col"] + delta["dc"]

            if can_place(state, piece, next_row, next_col):
                moves.append(build_move(piece, next_row, next_col, direction))

    return moves


def apply_move(state, move):
    """
    Equivalent to TS `applyMove`.

    Given one state and one move, build the next state.
    """

    next_state = clone_puzzle_state(state)
    for piece in next_state["pieces"]:
        if piece["id"] == move["pieceId"]:
            piece["row"] = move["toRow"]
            piece["col"] = move["toCol"]
            break
    return next_state


def is_rule_active(rule, state):
    if "isActive" not in rule or rule["isActive"] is None:
        return True
    return rule["isActive"](state)


def step_wind(state):
    """
    The TS solver supports a settle-mode environment rule.
    After the player moves, wind may push some pieces further.
    """

    next_state = clone_puzzle_state(state)
    wind = next_state["runtime"].get("wind")
    if not wind or not wind.get("active"):
        return next_state

    delta = DIRECTION_DELTAS[wind["direction"]]
    pieces = [piece for piece in next_state["pieces"] if piece.get("affectedByWind")]

    if wind["direction"] == "east":
        pieces.sort(key=lambda item: item["col"], reverse=True)
    elif wind["direction"] == "west":
        pieces.sort(key=lambda item: item["col"])
    elif wind["direction"] == "south":
        pieces.sort(key=lambda item: item["row"], reverse=True)
    else:
        pieces.sort(key=lambda item: item["row"])

    for piece in pieces:
        next_row = piece["row"] + delta["dr"]
        next_col = piece["col"] + delta["dc"]
        if can_place(next_state, piece, next_row, next_col):
            piece["row"] = next_row
            piece["col"] = next_col

    return next_state


def is_wind_stable(state):
    wind = state["runtime"].get("wind")
    if not wind or not wind.get("active"):
        return True

    delta = DIRECTION_DELTAS[wind["direction"]]
    for piece in state["pieces"]:
        if not piece.get("affectedByWind"):
            continue
        if can_place(state, piece, piece["row"] + delta["dr"], piece["col"] + delta["dc"]):
            return False
    return True


def create_wind_rule():
    return {
        "id": "wind",
        "mode": "settle",
        "isActive": lambda state: bool(state["runtime"].get("wind", {}).get("active")),
        "step": step_wind,
        "isStable": is_wind_stable,
    }


def apply_environment_rules_once(state, rules):
    current = clone_puzzle_state(state)
    for rule in rules:
        if is_rule_active(rule, current):
            current = rule["step"](current)
    return current


def settle_until_stable(state, rules, max_steps=64):
    """
    Settle-mode environment:
    keep applying environment rules until no further change happens.
    """

    current = clone_puzzle_state(state)
    seen = {serialize_state(current)}

    for _ in range(max_steps):
        pending_rules = [rule for rule in rules if is_rule_active(rule, current)]
        if not pending_rules:
            return current

        stable = True
        for rule in pending_rules:
            checker = rule.get("isStable")
            if checker is not None and not checker(current):
                stable = False
                break

        if stable:
            return current

        next_state = apply_environment_rules_once(current, pending_rules)
        key = serialize_state(next_state)
        if key in seen:
            return next_state

        seen.add(key)
        current = next_state

    return current


def advance_runtime_tick(state):
    next_state = clone_puzzle_state(state)
    next_state["runtime"]["tick"] += 1
    return next_state


def determine_solver_mode(rules):
    if any(rule["mode"] == "tick" for rule in rules):
        return "tick"
    if any(rule["mode"] == "settle" for rule in rules):
        return "settle"
    return "static"


def advance_environment_with_rules(state, rules):
    if not rules:
        return clone_puzzle_state(state)

    settle_rules = [rule for rule in rules if rule["mode"] == "settle"]
    tick_rules = [rule for rule in rules if rule["mode"] == "tick"]

    current = clone_puzzle_state(state)

    if settle_rules:
        current = settle_until_stable(current, settle_rules)

    if tick_rules:
        current = advance_runtime_tick(current)
        current = apply_environment_rules_once(current, tick_rules)

    if settle_rules:
        current = settle_until_stable(current, settle_rules)

    return current


def resolve_environment_rules(state):
    rules = []
    wind = state["runtime"].get("wind")
    if wind and wind.get("active"):
        rules.append(create_wind_rule())
    return rules


def create_rule_engine(state):
    rules = resolve_environment_rules(state)
    mode = determine_solver_mode(rules)

    return {
        "mode": mode,
        "listPlayerActions": list_legal_moves,
        "applyPlayerAction": apply_move,
        "advanceEnvironment": (
            (lambda snapshot: advance_environment_with_rules(snapshot, rules)) if rules else None
        ),
        "isGoal": is_solved_state,
        "serializeState": serialize_state,
    }


def solve_puzzle(initial_state, max_nodes=30000, rule_engine=None):
    """
    This is the BFS core.

    Important interview idea:
    queue stores states in layers.
    Therefore the first time we reach the goal, we have found the
    minimum number of moves.
    """

    engine = rule_engine or create_rule_engine(initial_state)
    start = clone_puzzle_state(initial_state)

    # Queue element = one board snapshot + the path used to reach it.
    queue = [{"state": start, "steps": []}]

    # `seen` is the standard BFS visited set.
    seen = {engine["serializeState"](start)}
    explored = 0

    while queue:
        current = queue.pop(0)
        explored += 1

        # BFS stop condition:
        # the first goal found is the shortest path in an unweighted graph.
        if engine["isGoal"](current["state"]):
            return {
                "solvable": True,
                "steps": current["steps"],
                "explored": explored,
                "truncated": False,
                "mode": engine["mode"],
            }

        if explored >= max_nodes:
            return {
                "solvable": False,
                "steps": [],
                "explored": explored,
                "truncated": True,
                "mode": engine["mode"],
            }

        # Expand all neighbors of the current state.
        for move in engine["listPlayerActions"](current["state"]):
            next_state = engine["applyPlayerAction"](current["state"], move)

            # If the puzzle has environment logic, settle it after the player move.
            if engine.get("advanceEnvironment"):
                next_state = engine["advanceEnvironment"](next_state)

            key = engine["serializeState"](next_state)
            if key in seen:
                continue

            # Mark as visited when enqueuing.
            # This is the usual BFS pattern for shortest-path problems.
            seen.add(key)
            queue.append(
                {
                    "state": next_state,
                    "steps": current["steps"] + [move],
                }
            )

    return {
        "solvable": False,
        "steps": [],
        "explored": explored,
        "truncated": False,
        "mode": engine["mode"],
    }


"""
Interview cheat sheet
=====================

1. State
   Use a hashable representation for visited de-duplication.
   In this project that idea is `serialize_state(state)`.

2. Neighbor generation
   The BFS skeleton is easy.
   The real domain logic is usually in `list_legal_moves()` and `can_place()`.

3. Transition
   `apply_move()` builds the next state.

4. Goal test
   `is_solved_state()` decides when BFS can stop.

5. BFS guarantee
   Because every move has equal cost = 1, BFS returns the minimum-step solution.

6. Why this project also stores `steps`
   Because the UI needs the actual move sequence, not only yes/no solvable.
"""
