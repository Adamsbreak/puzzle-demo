package com.puzzle.v1;

import com.puzzle.v1.model.PuzzleRequest;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public final class StaticSolverRuleCaseHarness {
  private static final Method CREATE_INITIAL_STATE = findMethod("createInitialState", 1);
  private static final Method CAN_MOVE_PIECE = findMethod("canMovePiece", 6);
  private static final Method EVALUATE_GOALS = findMethod("evaluateGoals", 1);

  private StaticSolverRuleCaseHarness() {}

  public static void main(String[] args) throws Exception {
    List<CaseResult> results = new ArrayList<>();
    results.add(runCaseA());
    results.add(runCaseB());
    results.add(runCaseC1());
    results.add(runCaseC2());
    results.add(runCaseD1());
    results.add(runCaseD2());

    boolean failed = false;
    for (CaseResult result : results) {
      System.out.println(result.format());
      if (!result.passed) {
        failed = true;
      }
    }

    if (failed) {
      throw new IllegalStateException("One or more rule regression cases failed.");
    }
  }

  private static CaseResult runCaseA() throws Exception {
    String[] blockerRoles = {"block", "fixed", "target"};
    List<String> checks = new ArrayList<>();

    for (String blockerRole : blockerRoles) {
      PuzzleRequest request =
          request(
              board(row("free", "free", "free", "free", "free")),
              pieces(
                  piece("m1", "block", 0, 0, 1, 1, "free", true),
                  piece(
                      "x1",
                      blockerRole,
                      0,
                      2,
                      1,
                      1,
                      "fixed".equals(blockerRole) ? "blocked" : "free",
                      !"fixed".equals(blockerRole))),
              zones());

      boolean allowed = canMove(request, "m1", 0, 3);
      checks.add(blockerRole + "=" + allowed);
      if (allowed) {
        return CaseResult.failed("Case A", "Expected path collision with " + blockerRole + " to block movement.");
      }
    }

    return CaseResult.passed("Case A", "Intermediate occupancy is checked for block/fixed/target: " + checks);
  }

  private static CaseResult runCaseB() throws Exception {
    PuzzleRequest moveRequest =
        request(
            board(row("free", "free", "free")),
            pieces(
                piece("b1", "block", 0, 0, 1, 1, "free", true),
                piece("t1", "target", 0, 2, 1, 1, "free", true)),
            zones(rectGoal("g1", 0, 1, 1, 1, "full")));

    PuzzleRequest solvedRequest =
        request(
            board(row("free", "free", "free")),
            pieces(
                piece("b1", "block", 0, 1, 1, 1, "free", true),
                piece("t1", "target", 0, 2, 1, 1, "free", true)),
            zones(rectGoal("g1", 0, 1, 1, 1, "full")));

    boolean allowed = canMove(moveRequest, "b1", 0, 1);
    GoalView goal = evaluate(solvedRequest);

    if (!allowed) {
      return CaseResult.failed("Case B", "Block should be able to enter an internal goal cell under current code.");
    }
    if (goal.solved) {
      return CaseResult.failed("Case B", "A block inside an internal goal must not satisfy goal evaluation.");
    }

    return CaseResult.passed(
        "Case B",
        "Block can enter an internal goal cell, but evaluateGoals still ignores it for solved state.");
  }

  private static CaseResult runCaseC1() throws Exception {
    PuzzleRequest moveRequest =
        request(
            board(row("free", "free"), row("free", "free")),
            pieces(piece("t1", "target", 0, 0, 2, 2, "free", true)),
            zones(edgeGoal("g1", "right", 0, 1, 2, "partial")));

    PuzzleRequest partialSolvedRequest =
        request(
            board(row("free", "free"), row("free", "free")),
            pieces(piece("t1", "target", 0, 1, 2, 2, "free", true)),
            zones(edgeGoal("g1", "right", 0, 1, 2, "partial")));

    PuzzleRequest fullSolvedRequest =
        request(
            board(row("free", "free"), row("free", "free")),
            pieces(piece("t1", "target", 0, 1, 2, 2, "free", true)),
            zones(edgeGoal("g1", "right", 0, 1, 2, "full")));

    PuzzleRequest badFootprintRequest =
        request(
            board(row("free", "free"), row("free", "free")),
            pieces(piece("t1", "target", 0, 0, 2, 2, "free", true)),
            zones(edgeGoal("g1", "right", 0, 1, 1, "partial")));

    boolean allowed = canMove(moveRequest, "t1", 0, 1);
    boolean badFootprintAllowed = canMove(badFootprintRequest, "t1", 0, 1);
    GoalView partialGoal = evaluate(partialSolvedRequest);
    GoalView fullGoal = evaluate(fullSolvedRequest);

    if (!allowed) {
      return CaseResult.failed("Case C1", "Large target should be able to enter edge goal without target-lane.");
    }
    if (badFootprintAllowed) {
      return CaseResult.failed("Case C1", "Edge goal admission should validate the entire large-piece footprint.");
    }
    if (!partialGoal.solved) {
      return CaseResult.failed("Case C1", "Partial edge goal should solve after large target overlaps the edge goal.");
    }
    if (fullGoal.solved) {
      return CaseResult.failed("Case C1", "Full edge goal should not solve when only part of a large target exits.");
    }

    return CaseResult.passed(
        "Case C1",
        "No target-lane required; entry allowed, partial=true, full=false, and footprint is checked as a whole.");
  }

  private static CaseResult runCaseC2() throws Exception {
    PuzzleRequest moveRequest =
        request(
            board(
                row("target-lane", "target-lane", "target-lane"),
                row("target-lane", "target-lane", "target-lane")),
            pieces(piece("t1", "target", 0, 0, 2, 2, "free", true)),
            zones(edgeGoal("g1", "right", 0, 1, 2, "partial")));

    PuzzleRequest partialSolvedRequest =
        request(
            board(
                row("target-lane", "target-lane", "target-lane"),
                row("target-lane", "target-lane", "target-lane")),
            pieces(piece("t1", "target", 0, 2, 2, 2, "free", true)),
            zones(edgeGoal("g1", "right", 0, 1, 2, "partial")));

    PuzzleRequest fullSolvedRequest =
        request(
            board(
                row("target-lane", "target-lane", "target-lane"),
                row("target-lane", "target-lane", "target-lane")),
            pieces(piece("t1", "target", 0, 2, 2, 2, "free", true)),
            zones(edgeGoal("g1", "right", 0, 1, 2, "full")));

    PuzzleRequest badFootprintRequest =
        request(
            board(
                row("target-lane", "target-lane", "target-lane"),
                row("target-lane", "target-lane", "target-lane")),
            pieces(piece("t1", "target", 0, 0, 2, 2, "free", true)),
            zones(edgeGoal("g1", "right", 0, 1, 1, "partial")));

    boolean allowed = canMove(moveRequest, "t1", 0, 2);
    boolean badFootprintAllowed = canMove(badFootprintRequest, "t1", 0, 2);
    GoalView partialGoal = evaluate(partialSolvedRequest);
    GoalView fullGoal = evaluate(fullSolvedRequest);

    if (!allowed) {
      return CaseResult.failed("Case C2", "Large target should be able to follow target-lane into edge goal.");
    }
    if (badFootprintAllowed) {
      return CaseResult.failed("Case C2", "Large target admission should reject partial edge coverage for the footprint.");
    }
    if (!partialGoal.solved) {
      return CaseResult.failed("Case C2", "Partial edge goal should solve for large target on target-lane path.");
    }
    if (fullGoal.solved) {
      return CaseResult.failed("Case C2", "Full edge goal should remain unsolved when only part of the large target exits.");
    }

    return CaseResult.passed(
        "Case C2",
        "Target-lane path reaches edge goal correctly; partial=true, full=false, and footprint is still whole-piece based.");
  }

  private static CaseResult runCaseD1() throws Exception {
    PuzzleRequest moveRequest =
        request(
            board(row("target-lane", "target-lane", "free", "free")),
            pieces(piece("t1", "target", 0, 0, 2, 1, "free", true)),
            zones(rectGoal("g1", 0, 2, 2, 1, "full")));

    PuzzleRequest solvedRequest =
        request(
            board(row("target-lane", "target-lane", "free", "free")),
            pieces(piece("t1", "target", 0, 2, 2, 1, "free", true)),
            zones(rectGoal("g1", 0, 2, 2, 1, "full")));

    boolean allowed = canMove(moveRequest, "t1", 0, 2);
    GoalView goal = evaluate(solvedRequest);

    if (allowed) {
      return CaseResult.failed("Case D1", "Internal full goal without target-lane should be blocked by lane requirement.");
    }
    if (!goal.solved) {
      return CaseResult.failed("Case D1", "Full goal evaluation itself should succeed once the target is placed inside.");
    }

    return CaseResult.passed(
        "Case D1",
        "Movement into non-lane internal full goal is blocked, but goal evaluation would solve if the target were placed there.");
  }

  private static CaseResult runCaseD2() throws Exception {
    PuzzleRequest moveRequest =
        request(
            board(row("target-lane", "target-lane", "free")),
            pieces(piece("t1", "target", 0, 0, 2, 1, "free", true)),
            zones(rectGoal("g1", 0, 2, 1, 1, "partial")));

    PuzzleRequest solvedRequest =
        request(
            board(row("target-lane", "target-lane", "free")),
            pieces(piece("t1", "target", 0, 1, 2, 1, "free", true)),
            zones(rectGoal("g1", 0, 2, 1, 1, "partial")));

    boolean allowed = canMove(moveRequest, "t1", 0, 1);
    GoalView goal = evaluate(solvedRequest);

    if (allowed) {
      return CaseResult.failed("Case D2", "Internal partial goal without target-lane should still be blocked by lane requirement.");
    }
    if (!goal.solved) {
      return CaseResult.failed("Case D2", "Partial goal evaluation itself should succeed once the target overlaps the zone.");
    }

    return CaseResult.passed(
        "Case D2",
        "Movement into non-lane internal partial goal is blocked, but partial goal evaluation itself is correct.");
  }

  private static boolean canMove(PuzzleRequest request, String pieceId, int toRow, int toCol)
      throws Exception {
    Object state = CREATE_INITIAL_STATE.invoke(null, request);
    PuzzleRequest.Piece piece = findPiece(request, pieceId);
    return (boolean) CAN_MOVE_PIECE.invoke(null, state, piece, toRow, toCol, piece.row, piece.col);
  }

  private static GoalView evaluate(PuzzleRequest request) throws Exception {
    Object state = CREATE_INITIAL_STATE.invoke(null, request);
    Object goalState = EVALUATE_GOALS.invoke(null, state);
    boolean solved = (boolean) readField(goalState, "solved");
    @SuppressWarnings("unchecked")
    List<String> satisfied = (List<String>) readField(goalState, "satisfiedPieceIds");
    @SuppressWarnings("unchecked")
    List<String> unsatisfied = (List<String>) readField(goalState, "unsatisfiedPieceIds");
    return new GoalView(solved, satisfied, unsatisfied);
  }

  private static PuzzleRequest request(
      PuzzleRequest.Board board, List<PuzzleRequest.Piece> pieces, List<PuzzleRequest.Zone> zones) {
    PuzzleRequest request = new PuzzleRequest();
    request.meta = new PuzzleRequest.Meta();
    request.meta.title = "Rule case";
    request.meta.rulePackId = "basic-static";

    request.rulePack = new PuzzleRequest.RulePack();
    request.rulePack.id = "basic-static";
    request.rulePack.solver = new PuzzleRequest.Solver();
    request.rulePack.solver.maxNodes = 1000;
    request.rulePack.solver.behavior = new PuzzleRequest.Behavior();
    request.rulePack.solver.behavior.targetLanePriority = "absolute";
    request.rulePack.solver.behavior.edgeGoalRelaxation = "final-step-only";
    request.rulePack.solver.behavior.stopGeneration = "all-legal-stops";

    request.board = board;
    request.pieces = pieces;
    request.zones = zones;
    return request;
  }

  private static PuzzleRequest.Board board(String[]... rows) {
    PuzzleRequest.Board board = new PuzzleRequest.Board();
    board.rows = rows.length;
    board.cols = rows[0].length;
    board.cellSize = 64;
    board.cells = new ArrayList<>();

    for (String[] row : rows) {
      ArrayList<PuzzleRequest.Cell> cells = new ArrayList<>();
      for (String cellSpec : row) {
        PuzzleRequest.Cell cell = new PuzzleRequest.Cell();
        if (cellSpec == null || cellSpec.isBlank()) {
          cell.tags = Collections.emptyList();
        } else {
          cell.tags = Arrays.asList(cellSpec.split("\\+"));
        }
        cells.add(cell);
      }
      board.cells.add(cells);
    }

    return board;
  }

  private static String[] row(String... specs) {
    return specs;
  }

  private static List<PuzzleRequest.Piece> pieces(PuzzleRequest.Piece... pieces) {
    return new ArrayList<>(Arrays.asList(pieces));
  }

  private static List<PuzzleRequest.Zone> zones(PuzzleRequest.Zone... zones) {
    return new ArrayList<>(Arrays.asList(zones));
  }

  private static PuzzleRequest.Piece piece(
      String id, String role, int row, int col, int w, int h, String moveRule, boolean movable) {
    PuzzleRequest.Piece piece = new PuzzleRequest.Piece();
    piece.id = id;
    piece.name = id;
    piece.typeId = role;
    piece.role = role;
    piece.row = row;
    piece.col = col;
    piece.w = w;
    piece.h = h;
    piece.moveRule = moveRule;
    piece.movable = movable;
    return piece;
  }

  private static PuzzleRequest.Zone rectGoal(
      String id, int row, int col, int w, int h, String goalMode) {
    PuzzleRequest.Zone zone = new PuzzleRequest.Zone();
    zone.id = id;
    zone.name = id;
    zone.role = "goal";
    zone.shapeKind = "rect";
    zone.row = row;
    zone.col = col;
    zone.w = w;
    zone.h = h;
    zone.goalMode = goalMode;
    zone.targetFilter = Collections.singletonMap("roles", Collections.singletonList("target"));
    return zone;
  }

  private static PuzzleRequest.Zone edgeGoal(
      String id, String side, int index, int w, int h, String goalMode) {
    PuzzleRequest.Zone zone = new PuzzleRequest.Zone();
    zone.id = id;
    zone.name = id;
    zone.role = "goal";
    zone.shapeKind = "edge";
    zone.side = side;
    zone.index = index;
    zone.w = w;
    zone.h = h;
    zone.goalMode = goalMode;
    zone.targetFilter = Collections.singletonMap("roles", Collections.singletonList("target"));
    return zone;
  }

  private static PuzzleRequest.Piece findPiece(PuzzleRequest request, String pieceId) {
    for (PuzzleRequest.Piece piece : request.pieces) {
      if (pieceId.equals(piece.id)) {
        return piece;
      }
    }
    throw new IllegalArgumentException("Unknown piece: " + pieceId);
  }

  private static Method findMethod(String name, int paramCount) {
    for (Method method : StaticSolver.class.getDeclaredMethods()) {
      if (method.getName().equals(name) && method.getParameterCount() == paramCount) {
        method.setAccessible(true);
        return method;
      }
    }
    throw new IllegalStateException("Method not found: " + name + "/" + paramCount);
  }

  private static Object readField(Object target, String fieldName) throws Exception {
    Field field = target.getClass().getDeclaredField(fieldName);
    field.setAccessible(true);
    return field.get(target);
  }

  private static final class GoalView {
    final boolean solved;
    final List<String> satisfiedPieceIds;
    final List<String> unsatisfiedPieceIds;

    GoalView(boolean solved, List<String> satisfiedPieceIds, List<String> unsatisfiedPieceIds) {
      this.solved = solved;
      this.satisfiedPieceIds = satisfiedPieceIds;
      this.unsatisfiedPieceIds = unsatisfiedPieceIds;
    }
  }

  private static final class CaseResult {
    final String name;
    final boolean passed;
    final String detail;

    private CaseResult(String name, boolean passed, String detail) {
      this.name = name;
      this.passed = passed;
      this.detail = detail;
    }

    static CaseResult passed(String name, String detail) {
      return new CaseResult(name, true, detail);
    }

    static CaseResult failed(String name, String detail) {
      return new CaseResult(name, false, detail);
    }

    String format() {
      return (passed ? "PASS " : "FAIL ") + name + " :: " + detail;
    }
  }
}
