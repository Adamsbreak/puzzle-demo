package com.puzzle.v1;

import com.puzzle.v1.model.PuzzleRequest;
import com.puzzle.v1.model.PuzzleResponse;
import com.puzzle.v1.model.SolutionStep;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.Set;

public final class StaticSolver {
  private static final int DEFAULT_MAX_NODES = 50_000;
  private static final int TARGET_MOVE_BONUS = 1000;
  private static final int RELEVANT_MOVE_BONUS = 250;
  private static final int NEAR_TARGET_MOVE_BONUS = 90;
  private static final int DISTANCE_IMPROVEMENT_WEIGHT = 120;
  private static final int DISTANCE_REGRESSION_WEIGHT = 40;
  private static final int CORRIDOR_CLEAR_BONUS = 220;
  private static final int CORRIDOR_ENTER_PENALTY = 140;

  private StaticSolver() {}

  public static PuzzleResponse solve(PuzzleRequest request) {
    PuzzleResponse response = baseResponse(request);
    ValidationResult validation = validatePuzzle(request);
    if (!validation.valid) {
      response.status = "invalid-puzzle";
      response.summary = "Puzzle structure is invalid: " + String.join("; ", validation.findings);
      response.steps = new ArrayList<>();
      return response;
    }

    SearchState initial = createInitialState(request);
    if (isObviouslyHopeless(initial)) {
      response.status = "no-solution";
      response.summary = "No solution found under the current static rules.";
      response.exploredNodes = 0;
      response.steps = new ArrayList<>();
      return response;
    }

    GoalState initialGoal = evaluateGoals(initial);
    if (initialGoal.solved) {
      response.status = "solved";
      response.summary = "The current layout already satisfies the goal.";
      response.exploredNodes = 1;
      response.stepCount = 0;
      response.steps = new ArrayList<>();
      return response;
    }

    int maxNodes = resolveMaxNodes(request);
    String initialKey = serializeState(initial);
    int initialH = estimateHeuristic(initial);
    long insertionOrder = 0L;

    PriorityQueue<SearchNode> openSet =
        new PriorityQueue<>(
            Comparator.comparingInt((SearchNode node) -> node.f)
                .thenComparingInt(node -> node.h)
                .thenComparingInt(node -> node.g)
                .thenComparingLong(node -> node.order));

    Map<String, Integer> bestCostByState = new HashMap<>();
    bestCostByState.put(initialKey, 0);
    openSet.add(
        new SearchNode(
            initial, new ArrayList<>(), 0, initialH, initialKey, insertionOrder, null));

    int exploredNodes = 0;
    while (!openSet.isEmpty()) {
      SearchNode current = openSet.poll();
      Integer bestKnown = bestCostByState.get(current.stateKey);
      if (bestKnown != null && current.g > bestKnown) {
        continue;
      }

      exploredNodes += 1;
      if (exploredNodes > maxNodes) {
        response.status = "search-limit";
        response.summary = "Search node limit reached before finding a solution.";
        response.exploredNodes = exploredNodes;
        response.steps = new ArrayList<>();
        return response;
      }

      List<SolutionStep> moves = enumerateMoves(current.state);
      for (SolutionStep move : moves) {
        if (isImmediateReverseMove(current.lastStep, move)) {
          continue;
        }

        SearchState next = applyMove(current.state, move);
        String nextKey = serializeState(next);
        if (current.stateKey.equals(nextKey)) {
          continue;
        }
        if (isObviouslyHopeless(next)) {
          continue;
        }

        int nextG = current.g + 1;
        Integer previousBest = bestCostByState.get(nextKey);
        if (previousBest != null && nextG >= previousBest) {
          continue;
        }

        ArrayList<SolutionStep> nextSteps = new ArrayList<>(current.steps);
        SolutionStep copiedMove = copyStep(move);
        nextSteps.add(copiedMove);

        GoalState goalState = evaluateGoals(next);
        if (goalState.solved) {
          response.status = "solved";
          response.summary = "Solved with A* under the current static rules.";
          response.exploredNodes = exploredNodes;
          response.stepCount = nextSteps.size();
          response.steps = nextSteps;
          return response;
        }

        int nextH = estimateHeuristic(next);
        bestCostByState.put(nextKey, nextG);
        insertionOrder += 1;
        openSet.add(
            new SearchNode(
                next, nextSteps, nextG, nextH, nextKey, insertionOrder, copiedMove));
      }
    }

    response.status = "no-solution";
    response.summary = "No solution found under the current static rules.";
    response.exploredNodes = exploredNodes;
    response.steps = new ArrayList<>();
    return response;
  }

  private static PuzzleResponse baseResponse(PuzzleRequest request) {
    PuzzleResponse response = new PuzzleResponse();
    response.rulePackId =
        request != null && request.rulePack != null && request.rulePack.id != null
            ? request.rulePack.id
            : request != null && request.meta != null ? request.meta.rulePackId : null;
    response.puzzleTitle = request != null && request.meta != null ? request.meta.title : null;
    response.steps = new ArrayList<>();
    return response;
  }

  private static int resolveMaxNodes(PuzzleRequest request) {
    if (request != null
        && request.rulePack != null
        && request.rulePack.solver != null
        && request.rulePack.solver.maxNodes != null
        && request.rulePack.solver.maxNodes > 0) {
      return request.rulePack.solver.maxNodes;
    }
    return DEFAULT_MAX_NODES;
  }

  private static ValidationResult validatePuzzle(PuzzleRequest request) {
    ArrayList<String> findings = new ArrayList<>();
    if (request == null || request.board == null || request.board.cells == null) {
      findings.add("Board is required.");
      return new ValidationResult(false, findings);
    }

    List<PuzzleRequest.Piece> pieces = safeList(request.pieces);
    List<PuzzleRequest.Zone> zones = safeList(request.zones);

    long targetCount = pieces.stream().filter(piece -> "target".equals(piece.role)).count();
    if (targetCount == 0) {
      findings.add("At least one target piece is required.");
    }

    boolean hasGoal = zones.stream().anyMatch(zone -> "goal".equals(zone.role));
    if (!hasGoal) {
      findings.add("At least one goal zone is required.");
    }

    return new ValidationResult(findings.isEmpty(), findings);
  }

  private static SearchState createInitialState(PuzzleRequest request) {
    return new SearchState(
        request.board,
        clonePieces(request.pieces),
        safeList(request.zones),
        resolveBehavior(request));
  }

  private static SolverBehavior resolveBehavior(PuzzleRequest request) {
    PuzzleRequest.Behavior behavior =
        request != null && request.rulePack != null && request.rulePack.solver != null
            ? request.rulePack.solver.behavior
            : null;

    return new SolverBehavior(
        behavior != null && behavior.targetLanePriority != null
            ? behavior.targetLanePriority
            : "absolute",
        behavior != null && behavior.edgeGoalRelaxation != null
            ? behavior.edgeGoalRelaxation
            : "final-step-only",
        behavior != null && behavior.stopGeneration != null
            ? behavior.stopGeneration
            : "all-legal-stops");
  }

  private static List<PuzzleRequest.Piece> clonePieces(List<PuzzleRequest.Piece> pieces) {
    ArrayList<PuzzleRequest.Piece> copy = new ArrayList<>();
    for (PuzzleRequest.Piece piece : safeList(pieces)) {
      copy.add(copyPiece(piece));
    }
    return copy;
  }

  private static PuzzleRequest.Piece copyPiece(PuzzleRequest.Piece source) {
    PuzzleRequest.Piece piece = new PuzzleRequest.Piece();
    piece.id = source.id;
    piece.name = source.name;
    piece.typeId = source.typeId;
    piece.role = source.role;
    piece.row = source.row;
    piece.col = source.col;
    piece.w = source.w;
    piece.h = source.h;
    piece.moveRule = source.moveRule;
    piece.movable = source.movable;
    return piece;
  }

  private static SolutionStep copyStep(SolutionStep source) {
    SolutionStep step = new SolutionStep();
    step.pieceId = source.pieceId;
    step.pieceName = source.pieceName;
    step.direction = source.direction;
    step.fromRow = source.fromRow;
    step.fromCol = source.fromCol;
    step.toRow = source.toRow;
    step.toCol = source.toCol;
    return step;
  }

  private static boolean isBoardCell(PuzzleRequest.Board board, int row, int col) {
    return row >= 0 && row < board.rows && col >= 0 && col < board.cols;
  }

  private static PuzzleRequest.Cell cellAt(PuzzleRequest.Board board, int row, int col) {
    if (board.cells == null || row < 0 || row >= board.cells.size()) {
      return null;
    }
    List<PuzzleRequest.Cell> rowCells = board.cells.get(row);
    if (rowCells == null || col < 0 || col >= rowCells.size()) {
      return null;
    }
    return rowCells.get(col);
  }

  private static EdgeSlot logicalCellToEdgeSlot(PuzzleRequest.Board board, int row, int col) {
    if (row == -1 && col >= 0 && col < board.cols) return new EdgeSlot("top", col);
    if (row == board.rows && col >= 0 && col < board.cols) return new EdgeSlot("bottom", col);
    if (col == -1 && row >= 0 && row < board.rows) return new EdgeSlot("left", row);
    if (col == board.cols && row >= 0 && row < board.rows) return new EdgeSlot("right", row);
    return null;
  }

  private static int zoneSpanOnSide(PuzzleRequest.Zone zone, String side) {
    return ("top".equals(side) || "bottom".equals(side)) ? zone.w : zone.h;
  }

  private static boolean zoneMatchesPiece(PuzzleRequest.Zone zone, PuzzleRequest.Piece piece) {
    Map<String, List<String>> filter = zone.targetFilter;
    if (filter == null || filter.isEmpty()) {
      return true;
    }

    List<String> roles = filter.get("roles");
    if (roles != null && !roles.isEmpty() && !roles.contains(piece.role)) {
      return false;
    }

    List<String> pieceTypeIds = filter.get("pieceTypeIds");
    if (pieceTypeIds != null && !pieceTypeIds.isEmpty() && !pieceTypeIds.contains(piece.typeId)) {
      return false;
    }

    return true;
  }

  private static PuzzleRequest.Zone edgeGoalAtCell(
      SearchState state, PuzzleRequest.Piece piece, int row, int col) {
    if (piece == null || !"target".equals(piece.role)) {
      return null;
    }

    EdgeSlot edge = logicalCellToEdgeSlot(state.board, row, col);
    if (edge == null) {
      return null;
    }

    for (PuzzleRequest.Zone zone : state.zones) {
      if (!"goal".equals(zone.role) || !"edge".equals(zone.shapeKind)) {
        continue;
      }
      if (!zoneMatchesPiece(zone, piece)) {
        continue;
      }
      int span = zoneSpanOnSide(zone, zone.side);
      int startIndex = safeInt(zone.index);
      if (Objects.equals(zone.side, edge.side)
          && edge.index >= startIndex
          && edge.index < startIndex + span) {
        return zone;
      }
    }

    return null;
  }

  private static boolean destinationTouchesEdgeGoal(
      SearchState state, PuzzleRequest.Piece piece, int row, int col, int width, int height) {
    if (piece == null || !"target".equals(piece.role)) {
      return false;
    }
    for (int r = row; r < row + height; r += 1) {
      for (int c = col; c < col + width; c += 1) {
        if (!isBoardCell(state.board, r, c) && edgeGoalAtCell(state, piece, r, c) != null) {
          return true;
        }
      }
    }
    return false;
  }

  private static boolean overlap(Rect a, Rect b) {
    return a.row < b.row + b.h
        && a.row + a.h > b.row
        && a.col < b.col + b.w
        && a.col + a.w > b.col;
  }

  private static int rectDistance(Rect a, Rect b) {
    int verticalGap = intervalGap(a.row, a.row + a.h, b.row, b.row + b.h);
    int horizontalGap = intervalGap(a.col, a.col + a.w, b.col, b.col + b.w);
    return verticalGap + horizontalGap;
  }

  private static int intervalGap(int aStart, int aEnd, int bStart, int bEnd) {
    if (aEnd <= bStart) {
      return bStart - aEnd;
    }
    if (bEnd <= aStart) {
      return aStart - bEnd;
    }
    return 0;
  }

  private static int containmentGap(int innerStart, int innerEnd, int outerStart, int outerEnd) {
    if (innerEnd - innerStart > outerEnd - outerStart) {
      return Integer.MAX_VALUE / 8;
    }
    int gap = 0;
    if (innerStart < outerStart) {
      gap += outerStart - innerStart;
    }
    if (innerEnd > outerEnd) {
      gap += innerEnd - outerEnd;
    }
    return gap;
  }

  private static boolean directionAllowedByTags(List<String> tags, int deltaRow, int deltaCol) {
    if (tags == null || tags.isEmpty()) return true;
    if (deltaRow == 0 && deltaCol == 0) return true;
    if (tags.contains("horizontal") && !tags.contains("vertical") && deltaRow != 0) return false;
    if (tags.contains("vertical") && !tags.contains("horizontal") && deltaCol != 0) return false;
    return true;
  }

  private static boolean cellAllowsPiece(
      SearchState state, PuzzleRequest.Piece piece, int row, int col) {
    PuzzleRequest.Cell cell = cellAt(state.board, row, col);
    if (cell == null) return false;
    List<String> tags = safeList(cell.tags);
    if (tags.contains("blocked")) return false;
    if (tags.contains("block-lane")
        && "target".equals(piece.role)
        && !tags.contains("target-lane")) {
      return false;
    }

    String moveRule = piece.moveRule != null ? piece.moveRule : "free";
    if ("target-lane".equals(moveRule)) return tags.contains("target-lane");
    if ("block-lane".equals(moveRule)) return tags.contains("block-lane");
    return true;
  }

  private static boolean canOccupyFootprint(
      SearchState state, PuzzleRequest.Piece piece, int row, int col, int width, int height) {
    String outsideSide = null;
    boolean matchedOutsideGoal = false;

    for (int r = row; r < row + height; r += 1) {
      for (int c = col; c < col + width; c += 1) {
        if (isBoardCell(state.board, r, c)) {
          if (!cellAllowsPiece(state, piece, r, c)) return false;
          continue;
        }

        EdgeSlot edge = logicalCellToEdgeSlot(state.board, r, c);
        if (edge == null) return false;
        if (outsideSide != null && !outsideSide.equals(edge.side)) return false;
        outsideSide = edge.side;

        PuzzleRequest.Zone goal = edgeGoalAtCell(state, piece, r, c);
        if (goal != null) {
          matchedOutsideGoal = true;
          continue;
        }
        return false;
      }
    }

    if (outsideSide != null && !matchedOutsideGoal) return false;
    return true;
  }

  private static boolean canPlace(
      SearchState state, PuzzleRequest.Piece piece, int row, int col, int width, int height) {
    if (!canOccupyFootprint(state, piece, row, col, width, height)) return false;

    Rect candidate = new Rect(row, col, width, height);
    for (PuzzleRequest.Piece other : state.pieces) {
      if (Objects.equals(other.id, piece.id)) continue;
      if (overlap(candidate, new Rect(other.row, other.col, other.w, other.h))) return false;
    }
    return true;
  }

  private static Set<String> collectSourceTags(
      SearchState state, PuzzleRequest.Piece piece, int fromRow, int fromCol) {
    Set<String> tags = new HashSet<>();
    for (int r = fromRow; r < fromRow + piece.h; r += 1) {
      for (int c = fromCol; c < fromCol + piece.w; c += 1) {
        if (!isBoardCell(state.board, r, c)) continue;
        PuzzleRequest.Cell cell = cellAt(state.board, r, c);
        if (cell == null || cell.tags == null) continue;
        tags.addAll(cell.tags);
      }
    }
    return tags;
  }

  private static boolean canMovePiece(
      SearchState state, PuzzleRequest.Piece piece, int row, int col, int fromRow, int fromCol) {
    int rowDiff = row - fromRow;
    int colDiff = col - fromCol;
    if (rowDiff != 0 && colDiff != 0) return false;
    if (rowDiff == 0 && colDiff == 0) return false;

    Set<String> sourceTags = collectSourceTags(state, piece, fromRow, fromCol);
    int deltaRow = Integer.compare(rowDiff, 0);
    int deltaCol = Integer.compare(colDiff, 0);
    boolean targetLaneDominates =
        "target".equals(piece.role)
            && sourceTags.contains("target-lane")
            && "absolute".equals(state.behavior.targetLanePriority);
    boolean targetLaneSourceBased =
        "target".equals(piece.role)
            && sourceTags.contains("target-lane")
            && "source-based".equals(state.behavior.targetLanePriority);
    boolean requireHorizontalTrack =
        !targetLaneDominates
            && sourceTags.contains("horizontal")
            && !sourceTags.contains("vertical");
    boolean requireVerticalTrack =
        !targetLaneDominates
            && sourceTags.contains("vertical")
            && !sourceTags.contains("horizontal");
    boolean requireTargetLane = targetLaneDominates || targetLaneSourceBased;
    boolean requireBlockLane = !"target".equals(piece.role) && sourceTags.contains("block-lane");

    int steps = Math.max(Math.abs(rowDiff), Math.abs(colDiff));
    for (int step = 1; step <= steps; step += 1) {
      int nextRow = fromRow + deltaRow * step;
      int nextCol = fromCol + deltaCol * step;
      if (!canPlace(state, piece, nextRow, nextCol, piece.w, piece.h)) return false;
      boolean stepTouchesEdgeGoal =
          destinationTouchesEdgeGoal(state, piece, nextRow, nextCol, piece.w, piece.h);
      boolean relaxForThisStep =
          stepTouchesEdgeGoal
              && ("full-path".equals(state.behavior.edgeGoalRelaxation)
                  || ("final-step-only".equals(state.behavior.edgeGoalRelaxation)
                      && step == steps));

      for (int r = nextRow; r < nextRow + piece.h; r += 1) {
        for (int c = nextCol; c < nextCol + piece.w; c += 1) {
          if (!isBoardCell(state.board, r, c)) continue;
          PuzzleRequest.Cell cell = cellAt(state.board, r, c);
          List<String> tags = cell != null ? safeList(cell.tags) : Collections.emptyList();
          if (!relaxForThisStep) {
            if (!requireTargetLane && !directionAllowedByTags(tags, deltaRow, deltaCol))
              return false;
            if (requireHorizontalTrack && !tags.contains("horizontal")) return false;
            if (requireVerticalTrack && !tags.contains("vertical")) return false;
            if (requireTargetLane && !tags.contains("target-lane")) return false;
            if (requireBlockLane && !tags.contains("block-lane")) return false;
          }
        }
      }
    }

    return true;
  }

  private static List<Direction> allowedDirections(PuzzleRequest.Piece piece) {
    String moveRule = piece.moveRule != null ? piece.moveRule : "free";
    boolean movable = piece.movable == null || piece.movable;
    if (!movable || "blocked".equals(moveRule)) return Collections.emptyList();

    ArrayList<Direction> directions = new ArrayList<>();
    if ("horizontal".equals(moveRule)) {
      directions.add(new Direction(0, -1, "left"));
      directions.add(new Direction(0, 1, "right"));
      return directions;
    }
    if ("vertical".equals(moveRule)) {
      directions.add(new Direction(-1, 0, "up"));
      directions.add(new Direction(1, 0, "down"));
      return directions;
    }

    directions.add(new Direction(-1, 0, "up"));
    directions.add(new Direction(1, 0, "down"));
    directions.add(new Direction(0, -1, "left"));
    directions.add(new Direction(0, 1, "right"));
    return directions;
  }

  private static List<SolutionStep> enumerateMoves(SearchState state) {
    Set<String> relevantPieceIds = findRelevantPieceIds(state);
    ArrayList<MoveCandidate> candidates = new ArrayList<>();
    long order = 0L;

    for (int pass = 0; pass < 2; pass += 1) {
      boolean relevantPass = pass == 0;
      for (PuzzleRequest.Piece piece : state.pieces) {
        boolean relevant = relevantPieceIds.contains(piece.id);
        if (relevantPass != relevant) {
          continue;
        }

        for (Direction direction : allowedDirections(piece)) {
          int step = 1;
          SolutionStep farthestMove = null;
          long farthestOrder = order;
          while (true) {
            int nextRow = piece.row + direction.dr * step;
            int nextCol = piece.col + direction.dc * step;
            if (!canMovePiece(state, piece, nextRow, nextCol, piece.row, piece.col)) {
              break;
            }

            SolutionStep move = new SolutionStep();
            move.pieceId = piece.id;
            move.pieceName = piece.name;
            move.direction = direction.name;
            move.fromRow = piece.row;
            move.fromCol = piece.col;
            move.toRow = nextRow;
            move.toCol = nextCol;

            if ("farthest-only".equals(state.behavior.stopGeneration)) {
              farthestMove = move;
              farthestOrder = order;
            } else {
              candidates.add(
                  new MoveCandidate(
                      move, scoreMove(state, move, relevantPieceIds), relevant, order));
            }

            order += 1;
            step += 1;
          }

          if (farthestMove != null) {
            candidates.add(
                new MoveCandidate(
                    farthestMove,
                    scoreMove(state, farthestMove, relevantPieceIds),
                    relevant,
                    farthestOrder));
          }
        }
      }
    }

    candidates.sort(
        Comparator.comparingInt((MoveCandidate candidate) -> candidate.score)
            .reversed()
            .thenComparing((MoveCandidate candidate) -> candidate.relevant ? 0 : 1)
            .thenComparingLong(candidate -> candidate.order));

    ArrayList<SolutionStep> moves = new ArrayList<>();
    for (MoveCandidate candidate : candidates) {
      moves.add(candidate.move);
    }
    return moves;
  }

  private static SearchState applyMove(SearchState state, SolutionStep move) {
    ArrayList<PuzzleRequest.Piece> pieces = new ArrayList<>();
    for (PuzzleRequest.Piece piece : state.pieces) {
      PuzzleRequest.Piece copy = copyPiece(piece);
      if (Objects.equals(copy.id, move.pieceId)) {
        copy.row = move.toRow;
        copy.col = move.toCol;
      }
      pieces.add(copy);
    }
    return new SearchState(state.board, pieces, state.zones, state.behavior);
  }

  private static String serializeState(SearchState state) {
    ArrayList<PuzzleRequest.Piece> pieces = new ArrayList<>(state.pieces);
    pieces.sort(Comparator.comparing(piece -> piece.id));

    StringBuilder builder = new StringBuilder();
    for (int i = 0; i < pieces.size(); i += 1) {
      PuzzleRequest.Piece piece = pieces.get(i);
      if (i > 0) builder.append('|');
      builder
          .append(piece.id)
          .append(':')
          .append(piece.row)
          .append(':')
          .append(piece.col)
          .append(':')
          .append(piece.w)
          .append(':')
          .append(piece.h)
          .append(':')
          .append(piece.moveRule != null ? piece.moveRule : "free")
          .append(':')
          .append(piece.role);
    }
    return builder.toString();
  }

  private static int estimateHeuristic(SearchState state) {
    GoalState goalState = evaluateGoals(state);
    if (goalState.solved) {
      return 0;
    }

    int distanceEstimate = 0;
    for (PuzzleRequest.Piece piece : state.pieces) {
      if (!"target".equals(piece.role)) {
        continue;
      }
      distanceEstimate += estimateTargetDistanceToGoal(state, piece);
    }

    int blockingPenalty = estimateBlockingPenalty(state);
    return Math.max(0, distanceEstimate + blockingPenalty);
  }

  private static int estimateBlockingPenalty(SearchState state) {
    for (PuzzleRequest.Piece piece : state.pieces) {
      if (!"target".equals(piece.role)) {
        continue;
      }
      if (targetAlreadySatisfied(state, piece)) {
        continue;
      }
      if (hasAdjacentBlockingPiece(state, piece)) {
        return 1;
      }
    }
    return 0;
  }

  private static int estimateTargetDistanceToGoal(SearchState state, PuzzleRequest.Piece piece) {
    int best = Integer.MAX_VALUE / 8;
    for (PuzzleRequest.Zone zone : state.zones) {
      if (!"goal".equals(zone.role) || !zoneMatchesPiece(zone, piece)) {
        continue;
      }
      best = Math.min(best, estimatePieceDistanceToZone(state, piece, zone));
    }
    return best == Integer.MAX_VALUE / 8 ? state.board.rows + state.board.cols : best;
  }

  private static int estimatePieceDistanceToZone(
      SearchState state, PuzzleRequest.Piece piece, PuzzleRequest.Zone zone) {
    if (isPieceInZone(state, piece, zone)) {
      return 0;
    }

    if ("rect".equals(zone.shapeKind)) {
      String mode = zone.goalMode != null ? zone.goalMode : "full";
      Rect pieceRect = new Rect(piece.row, piece.col, piece.w, piece.h);
      Rect zoneRect = new Rect(safeInt(zone.row), safeInt(zone.col), zone.w, zone.h);
      if ("partial".equals(mode)) {
        return estimateRectPartialCost(pieceRect, zoneRect);
      }
      return estimateRectFullCost(pieceRect, zoneRect);
    }

    return estimateEdgeGoalCost(state, piece, zone);
  }

  private static int estimateRectPartialCost(Rect pieceRect, Rect zoneRect) {
    int verticalGap = intervalGap(pieceRect.row, pieceRect.row + pieceRect.h, zoneRect.row, zoneRect.row + zoneRect.h);
    int horizontalGap =
        intervalGap(pieceRect.col, pieceRect.col + pieceRect.w, zoneRect.col, zoneRect.col + zoneRect.w);
    int moves = 0;
    if (verticalGap > 0) moves += 1;
    if (horizontalGap > 0) moves += 1;
    return moves;
  }

  private static int estimateRectFullCost(Rect pieceRect, Rect zoneRect) {
    int rowGap =
        containmentGap(pieceRect.row, pieceRect.row + pieceRect.h, zoneRect.row, zoneRect.row + zoneRect.h);
    int colGap =
        containmentGap(pieceRect.col, pieceRect.col + pieceRect.w, zoneRect.col, zoneRect.col + zoneRect.w);

    int moves = 0;
    if (rowGap > 0) moves += 1;
    if (colGap > 0) moves += 1;
    return moves == 0 ? 0 : moves;
  }

  private static int estimateEdgeGoalCost(
      SearchState state, PuzzleRequest.Piece piece, PuzzleRequest.Zone zone) {
    String mode = zone.goalMode != null ? zone.goalMode : "full";
    int moves = 1;

    if ("left".equals(zone.side) || "right".equals(zone.side)) {
      int zoneStart = safeInt(zone.index);
      int zoneEnd = zoneStart + zone.h;
      int pieceStart = piece.row;
      int pieceEnd = piece.row + piece.h;
      int alignmentCost =
          "partial".equals(mode)
              ? (intervalGap(pieceStart, pieceEnd, zoneStart, zoneEnd) > 0 ? 1 : 0)
              : (containmentGap(pieceStart, pieceEnd, zoneStart, zoneEnd) > 0 ? 1 : 0);
      return moves + alignmentCost;
    }

    int zoneStart = safeInt(zone.index);
    int zoneEnd = zoneStart + zone.w;
    int pieceStart = piece.col;
    int pieceEnd = piece.col + piece.w;
    int alignmentCost =
        "partial".equals(mode)
            ? (intervalGap(pieceStart, pieceEnd, zoneStart, zoneEnd) > 0 ? 1 : 0)
            : (containmentGap(pieceStart, pieceEnd, zoneStart, zoneEnd) > 0 ? 1 : 0);
    return moves + alignmentCost;
  }

  private static int scoreMove(
      SearchState state, SolutionStep move, Set<String> relevantPieceIds) {
    PuzzleRequest.Piece piece = pieceById(state, move.pieceId);
    if (piece == null) {
      return Integer.MIN_VALUE / 4;
    }

    int score = 0;
    if ("target".equals(piece.role)) {
      score += TARGET_MOVE_BONUS;
      int before = estimateTargetDistanceToGoal(state, piece);
      PuzzleRequest.Piece moved = copyPiece(piece);
      moved.row = move.toRow;
      moved.col = move.toCol;
      int after = estimateTargetDistanceToGoal(state, moved);
      if (after < before) {
        score += (before - after) * DISTANCE_IMPROVEMENT_WEIGHT;
      } else if (after > before) {
        score -= (after - before) * DISTANCE_REGRESSION_WEIGHT;
      }
    } else {
      if (relevantPieceIds.contains(piece.id)) {
        score += RELEVANT_MOVE_BONUS;
      }
      if (isNearAnyTarget(state, piece, 1)) {
        score += NEAR_TARGET_MOVE_BONUS;
      }
      score += scoreCorridorUnblockingMove(state, piece, move);
    }

    if (moveTouchesMatchingEdgeGoal(state, piece, move)) {
      score += 300;
    }
    if (movesTowardNearestGoal(state, piece, move)) {
      score += 120;
    }

    return score;
  }

  private static int scoreCorridorUnblockingMove(
      SearchState state, PuzzleRequest.Piece piece, SolutionStep move) {
    int score = 0;
    Rect beforeRect = new Rect(piece.row, piece.col, piece.w, piece.h);
    Rect afterRect = new Rect(move.toRow, move.toCol, piece.w, piece.h);

    for (PuzzleRequest.Piece target : targetPieces(state)) {
      if (targetAlreadySatisfied(state, target)) {
        continue;
      }
      PuzzleRequest.Zone bestGoal = bestGoalForPiece(state, target);
      if (bestGoal == null) {
        continue;
      }
      Rect influence = goalInfluenceRect(state, bestGoal);
      Rect corridor = corridorRect(new Rect(target.row, target.col, target.w, target.h), influence);

      boolean blocksBefore = overlap(beforeRect, corridor);
      boolean blocksAfter = overlap(afterRect, corridor);

      if (blocksBefore && !blocksAfter) {
        score += CORRIDOR_CLEAR_BONUS;
      } else if (!blocksBefore && blocksAfter) {
        score -= CORRIDOR_ENTER_PENALTY;
      }
    }

    return score;
  }

  private static Set<String> findRelevantPieceIds(SearchState state) {
    Set<String> relevant = new HashSet<>();
    List<PuzzleRequest.Piece> targets = targetPieces(state);
    for (PuzzleRequest.Piece target : targets) {
      relevant.add(target.id);
    }

    for (PuzzleRequest.Piece piece : state.pieces) {
      if (relevant.contains(piece.id)) {
        continue;
      }
      for (PuzzleRequest.Piece target : targets) {
        if (isNear(piece, target, 1)) {
          relevant.add(piece.id);
          break;
        }
      }
    }

    for (PuzzleRequest.Piece target : targets) {
      PuzzleRequest.Zone bestGoal = bestGoalForPiece(state, target);
      if (bestGoal == null) {
        continue;
      }
      Rect influence = goalInfluenceRect(state, bestGoal);
      Rect corridor = corridorRect(new Rect(target.row, target.col, target.w, target.h), influence);
      for (PuzzleRequest.Piece piece : state.pieces) {
        if (Objects.equals(piece.id, target.id)) {
          continue;
        }
        Rect pieceRect = new Rect(piece.row, piece.col, piece.w, piece.h);
        if (rectDistance(pieceRect, influence) <= 1 || rectDistance(pieceRect, corridor) <= 1) {
          relevant.add(piece.id);
        }
      }
    }

    return relevant;
  }

  private static boolean isImmediateReverseMove(SolutionStep previous, SolutionStep next) {
    if (previous == null || next == null) {
      return false;
    }
    if (!Objects.equals(previous.pieceId, next.pieceId)) {
      return false;
    }
    return previous.fromRow == next.toRow
        && previous.fromCol == next.toCol
        && previous.toRow == next.fromRow
        && previous.toCol == next.fromCol
        && isOppositeDirection(previous.direction, next.direction);
  }

  private static boolean isOppositeDirection(String first, String second) {
    if (first == null || second == null) {
      return false;
    }
    return ("left".equals(first) && "right".equals(second))
        || ("right".equals(first) && "left".equals(second))
        || ("up".equals(first) && "down".equals(second))
        || ("down".equals(first) && "up".equals(second));
  }

  private static boolean isObviouslyHopeless(SearchState state) {
    for (PuzzleRequest.Piece piece : state.pieces) {
      if (!"target".equals(piece.role)) {
        continue;
      }
      if (!hasPotentialGoalForTarget(state, piece)) {
        return true;
      }
    }
    return false;
  }

  private static boolean hasPotentialGoalForTarget(SearchState state, PuzzleRequest.Piece piece) {
    for (PuzzleRequest.Zone zone : state.zones) {
      if (!"goal".equals(zone.role) || !zoneMatchesPiece(zone, piece)) {
        continue;
      }

      String mode = zone.goalMode != null ? zone.goalMode : "full";
      if (!"full".equals(mode)) {
        return true;
      }

      if ("rect".equals(zone.shapeKind)) {
        if (piece.w <= zone.w && piece.h <= zone.h) {
          return true;
        }
      } else if ("edge".equals(zone.shapeKind)) {
        int span = zoneSpanOnSide(zone, zone.side);
        if ("left".equals(zone.side) || "right".equals(zone.side)) {
          if (piece.h <= span) {
            return true;
          }
        } else if (piece.w <= span) {
          return true;
        }
      }
    }
    return false;
  }

  private static boolean hasAdjacentBlockingPiece(SearchState state, PuzzleRequest.Piece target) {
    Rect expanded =
        new Rect(target.row - 1, target.col - 1, target.w + 2, target.h + 2);
    Rect targetRect = new Rect(target.row, target.col, target.w, target.h);
    for (PuzzleRequest.Piece piece : state.pieces) {
      if (Objects.equals(piece.id, target.id)) {
        continue;
      }
      Rect pieceRect = new Rect(piece.row, piece.col, piece.w, piece.h);
      if (overlap(expanded, pieceRect) && !overlap(targetRect, pieceRect)) {
        return true;
      }
    }
    return false;
  }

  private static boolean targetAlreadySatisfied(SearchState state, PuzzleRequest.Piece piece) {
    for (PuzzleRequest.Zone zone : state.zones) {
      if ("goal".equals(zone.role) && isPieceInZone(state, piece, zone)) {
        return true;
      }
    }
    return false;
  }

  private static boolean isNearAnyTarget(
      SearchState state, PuzzleRequest.Piece piece, int buffer) {
    for (PuzzleRequest.Piece target : targetPieces(state)) {
      if (Objects.equals(target.id, piece.id)) {
        continue;
      }
      if (isNear(piece, target, buffer)) {
        return true;
      }
    }
    return false;
  }

  private static boolean isNear(
      PuzzleRequest.Piece first, PuzzleRequest.Piece second, int buffer) {
    Rect expanded =
        new Rect(first.row - buffer, first.col - buffer, first.w + buffer * 2, first.h + buffer * 2);
    Rect secondRect = new Rect(second.row, second.col, second.w, second.h);
    return overlap(expanded, secondRect);
  }

  private static List<PuzzleRequest.Piece> targetPieces(SearchState state) {
    ArrayList<PuzzleRequest.Piece> targets = new ArrayList<>();
    for (PuzzleRequest.Piece piece : state.pieces) {
      if ("target".equals(piece.role)) {
        targets.add(piece);
      }
    }
    return targets;
  }

  private static PuzzleRequest.Piece pieceById(SearchState state, String pieceId) {
    for (PuzzleRequest.Piece piece : state.pieces) {
      if (Objects.equals(piece.id, pieceId)) {
        return piece;
      }
    }
    return null;
  }

  private static PuzzleRequest.Zone bestGoalForPiece(
      SearchState state, PuzzleRequest.Piece piece) {
    PuzzleRequest.Zone bestZone = null;
    int bestDistance = Integer.MAX_VALUE / 8;
    for (PuzzleRequest.Zone zone : state.zones) {
      if (!"goal".equals(zone.role) || !zoneMatchesPiece(zone, piece)) {
        continue;
      }
      int distance = estimatePieceDistanceToZone(state, piece, zone);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestZone = zone;
      }
    }
    return bestZone;
  }

  private static boolean moveTouchesMatchingEdgeGoal(
      SearchState state, PuzzleRequest.Piece piece, SolutionStep move) {
    return "target".equals(piece.role)
        && destinationTouchesEdgeGoal(state, piece, move.toRow, move.toCol, piece.w, piece.h);
  }

  private static boolean movesTowardNearestGoal(
      SearchState state, PuzzleRequest.Piece piece, SolutionStep move) {
    PuzzleRequest.Zone zone = bestGoalForPiece(state, piece);
    if (zone == null) {
      return false;
    }

    PuzzleRequest.Piece moved = copyPiece(piece);
    moved.row = move.toRow;
    moved.col = move.toCol;
    int before = estimatePieceDistanceToZone(state, piece, zone);
    int after = estimatePieceDistanceToZone(state, moved, zone);
    return after < before;
  }

  private static Rect goalInfluenceRect(SearchState state, PuzzleRequest.Zone zone) {
    if ("rect".equals(zone.shapeKind)) {
      return new Rect(safeInt(zone.row), safeInt(zone.col), zone.w, zone.h);
    }

    int index = safeInt(zone.index);
    if ("left".equals(zone.side)) {
      return new Rect(index, 0, 1, zone.h);
    }
    if ("right".equals(zone.side)) {
      return new Rect(index, Math.max(0, state.board.cols - 1), 1, zone.h);
    }
    if ("top".equals(zone.side)) {
      return new Rect(0, index, zone.w, 1);
    }
    return new Rect(Math.max(0, state.board.rows - 1), index, zone.w, 1);
  }

  private static Rect corridorRect(Rect from, Rect to) {
    int row = Math.min(from.row, to.row);
    int col = Math.min(from.col, to.col);
    int bottom = Math.max(from.row + from.h, to.row + to.h);
    int right = Math.max(from.col + from.w, to.col + to.w);
    return new Rect(row, col, Math.max(1, right - col), Math.max(1, bottom - row));
  }

  private static List<CellRef> buildEdgeZoneCells(SearchState state, PuzzleRequest.Zone zone) {
    ArrayList<CellRef> cells = new ArrayList<>();
    int span = zoneSpanOnSide(zone, zone.side);
    for (int offset = 0; offset < span; offset += 1) {
      if ("top".equals(zone.side)) cells.add(new CellRef(-1, safeInt(zone.index) + offset));
      else if ("bottom".equals(zone.side)) {
        cells.add(new CellRef(state.board.rows, safeInt(zone.index) + offset));
      } else if ("left".equals(zone.side)) {
        cells.add(new CellRef(safeInt(zone.index) + offset, -1));
      } else {
        cells.add(new CellRef(safeInt(zone.index) + offset, state.board.cols));
      }
    }
    return cells;
  }

  private static List<CellRef> pieceCells(PuzzleRequest.Piece piece) {
    ArrayList<CellRef> cells = new ArrayList<>();
    for (int row = piece.row; row < piece.row + piece.h; row += 1) {
      for (int col = piece.col; col < piece.col + piece.w; col += 1) {
        cells.add(new CellRef(row, col));
      }
    }
    return cells;
  }

  private static boolean isPieceInZone(
      SearchState state, PuzzleRequest.Piece piece, PuzzleRequest.Zone zone) {
    if (!"goal".equals(zone.role) || !zoneMatchesPiece(zone, piece)) return false;

    if ("rect".equals(zone.shapeKind)) {
      String mode = zone.goalMode != null ? zone.goalMode : "full";
      Rect zoneRect = new Rect(safeInt(zone.row), safeInt(zone.col), zone.w, zone.h);
      Rect pieceRect = new Rect(piece.row, piece.col, piece.w, piece.h);
      if ("partial".equals(mode)) return overlap(pieceRect, zoneRect);
      return pieceRect.row >= zoneRect.row
          && pieceRect.col >= zoneRect.col
          && pieceRect.row + pieceRect.h <= zoneRect.row + zoneRect.h
          && pieceRect.col + pieceRect.w <= zoneRect.col + zoneRect.w;
    }

    Set<String> zoneKeys = new HashSet<>();
    for (CellRef cell : buildEdgeZoneCells(state, zone)) {
      zoneKeys.add(cell.row + ":" + cell.col);
    }

    int matched = 0;
    List<CellRef> cells = pieceCells(piece);
    for (CellRef cell : cells) {
      if (zoneKeys.contains(cell.row + ":" + cell.col)) {
        matched += 1;
      }
    }

    String mode = zone.goalMode != null ? zone.goalMode : "full";
    if ("partial".equals(mode)) {
      return matched > 0;
    }
    return matched == cells.size() && !cells.isEmpty();
  }

  private static GoalState evaluateGoals(SearchState state) {
    ArrayList<String> satisfied = new ArrayList<>();
    ArrayList<String> unsatisfied = new ArrayList<>();

    ArrayList<PuzzleRequest.Zone> goalZones = new ArrayList<>();
    for (PuzzleRequest.Zone zone : state.zones) {
      if ("goal".equals(zone.role)) {
        goalZones.add(zone);
      }
    }

    for (PuzzleRequest.Piece piece : state.pieces) {
      if (!"target".equals(piece.role)) continue;

      boolean hit = false;
      for (PuzzleRequest.Zone zone : goalZones) {
        if (isPieceInZone(state, piece, zone)) {
          hit = true;
          break;
        }
      }

      if (hit) satisfied.add(piece.id);
      else unsatisfied.add(piece.id);
    }

    return new GoalState(!satisfied.isEmpty() && unsatisfied.isEmpty(), satisfied, unsatisfied);
  }

  private static int safeInt(Integer value) {
    return value != null ? value : 0;
  }

  private static <T> List<T> safeList(List<T> value) {
    return value != null ? value : Collections.emptyList();
  }

  private static final class SearchNode {
    final SearchState state;
    final List<SolutionStep> steps;
    final int g;
    final int h;
    final int f;
    final String stateKey;
    final long order;
    final SolutionStep lastStep;

    SearchNode(
        SearchState state,
        List<SolutionStep> steps,
        int g,
        int h,
        String stateKey,
        long order,
        SolutionStep lastStep) {
      this.state = state;
      this.steps = steps;
      this.g = g;
      this.h = h;
      this.f = g + h;
      this.stateKey = stateKey;
      this.order = order;
      this.lastStep = lastStep;
    }
  }

  private static final class SearchState {
    final PuzzleRequest.Board board;
    final List<PuzzleRequest.Piece> pieces;
    final List<PuzzleRequest.Zone> zones;
    final SolverBehavior behavior;

    SearchState(
        PuzzleRequest.Board board,
        List<PuzzleRequest.Piece> pieces,
        List<PuzzleRequest.Zone> zones,
        SolverBehavior behavior) {
      this.board = board;
      this.pieces = pieces;
      this.zones = zones;
      this.behavior = behavior;
    }
  }

  private static final class SolverBehavior {
    final String targetLanePriority;
    final String edgeGoalRelaxation;
    final String stopGeneration;

    SolverBehavior(String targetLanePriority, String edgeGoalRelaxation, String stopGeneration) {
      this.targetLanePriority = targetLanePriority;
      this.edgeGoalRelaxation = edgeGoalRelaxation;
      this.stopGeneration = stopGeneration;
    }
  }

  private static final class MoveCandidate {
    final SolutionStep move;
    final int score;
    final boolean relevant;
    final long order;

    MoveCandidate(SolutionStep move, int score, boolean relevant, long order) {
      this.move = move;
      this.score = score;
      this.relevant = relevant;
      this.order = order;
    }
  }

  private static final class ValidationResult {
    final boolean valid;
    final List<String> findings;

    ValidationResult(boolean valid, List<String> findings) {
      this.valid = valid;
      this.findings = findings;
    }
  }

  private static final class GoalState {
    final boolean solved;
    final List<String> satisfiedPieceIds;
    final List<String> unsatisfiedPieceIds;

    GoalState(boolean solved, List<String> satisfiedPieceIds, List<String> unsatisfiedPieceIds) {
      this.solved = solved;
      this.satisfiedPieceIds = satisfiedPieceIds;
      this.unsatisfiedPieceIds = unsatisfiedPieceIds;
    }
  }

  private static final class EdgeSlot {
    final String side;
    final int index;

    EdgeSlot(String side, int index) {
      this.side = side;
      this.index = index;
    }
  }

  private static final class CellRef {
    final int row;
    final int col;

    CellRef(int row, int col) {
      this.row = row;
      this.col = col;
    }
  }

  private static final class Rect {
    final int row;
    final int col;
    final int w;
    final int h;

    Rect(int row, int col, int w, int h) {
      this.row = row;
      this.col = col;
      this.w = w;
      this.h = h;
    }
  }

  private static final class Direction {
    final int dr;
    final int dc;
    final String name;

    Direction(int dr, int dc, String name) {
      this.dr = dr;
      this.dc = dc;
      this.name = name;
    }
  }
}
