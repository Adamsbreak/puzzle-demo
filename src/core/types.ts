export type CellTag = "horizontal" | "vertical" | "target-zone" | "blocked";
export type PieceRole = "normal" | "target";
export type MoveRule = "free" | "horizontal" | "vertical" | "blocked";
export type PaintMode = "add" | "remove" | "clear";
export type MainMode = "cells" | "objects";
export type Direction = "north" | "south" | "west" | "east";
export type ZoneSide = "top" | "bottom" | "left" | "right";
export type ZoneRole = "spawn" | "goal" | "portal";
export type ZoneShapeKind = "edge" | "rect";
export type SolverMode = "static" | "settle" | "tick";

export interface CellState {
  tags: CellTag[];
}

export interface Piece {
  id: string;
  type: "piece";
  name: string;
  role: PieceRole;
  row: number;
  col: number;
  w: number;
  h: number;
  moveRule: MoveRule;
  color: string;
  affectedByWind?: boolean;
  blocksWind?: boolean;
  spawnZoneId?: string | null;
}

export interface ZoneTargetFilter {
  pieceIds?: string[];
  pieceRoles?: PieceRole[];
}

export interface Zone {
  id: string;
  type: "zone";
  name: string;
  role: ZoneRole;
  shapeKind: ZoneShapeKind;
  side?: ZoneSide;
  index?: number;
  row?: number;
  col?: number;
  w: number;
  h: number;
  color: string;
  targetFilter?: ZoneTargetFilter | null;
}

export type RuntimeScalar = string | number | boolean | null;

export interface RuntimeEntityState {
  id: string;
  kind: string;
  active?: boolean;
  row?: number;
  col?: number;
  phase?: number;
  direction?: Direction;
  blocksMovement?: boolean;
  data?: Record<string, RuntimeScalar>;
}

export interface RuntimeState {
  tick: number;
  wind: null | {
    direction: Direction;
    active: boolean;
  };
  flags: Record<string, RuntimeScalar>;
  entities: RuntimeEntityState[];
}

export interface Stats {
  operations: number;
  distance: number;
}

export interface DragState {
  id: string;
  offsetX: number;
  offsetY: number;
  startRow: number;
  startCol: number;
}

export type ClipboardState =
  | { kind: "piece"; data: Piece }
  | { kind: "zone"; data: Zone }
  | null;

export interface EditorState {
  rows: number;
  cols: number;
  cellSize: number;
  showCoords: boolean;
  mainMode: MainMode;
  paintMode: PaintMode;
  selectedTag: CellTag;
  cells: CellState[][];
  pieces: Piece[];
  zones: Zone[];
  runtime: RuntimeState;
  selectedPieceId: string | null;
  clipboard: ClipboardState;
  nextPieceId: number;
  nextZoneId: number;
  dragging: DragState | null;
  stats: Stats;
}

export interface PuzzleSnapshot {
  rows: number;
  cols: number;
  cellSize: number;
  cells: CellState[][];
  pieces: Piece[];
  zones: Zone[];
  runtime: RuntimeState;
}

export interface SolverMove {
  pieceId: string;
  pieceName: string;
  fromRow: number;
  fromCol: number;
  toRow: number;
  toCol: number;
  direction: Direction;
}

export interface SolverResult {
  solvable: boolean;
  steps: SolverMove[];
  explored: number;
  truncated: boolean;
  mode: SolverMode;
}

export interface EnvironmentRule {
  id: string;
  mode: Exclude<SolverMode, "static">;
  step(state: EditorState | PuzzleSnapshot): PuzzleSnapshot;
  isActive?(state: EditorState | PuzzleSnapshot): boolean;
  isStable?(state: EditorState | PuzzleSnapshot): boolean;
}

export interface RuleEngine {
  mode: SolverMode;
  deterministic: boolean;
  listPlayerActions(state: EditorState | PuzzleSnapshot): SolverMove[];
  applyPlayerAction(
    state: EditorState | PuzzleSnapshot,
    action: SolverMove,
  ): PuzzleSnapshot;
  isGoal(state: EditorState | PuzzleSnapshot): boolean;
  serializeState(state: EditorState | PuzzleSnapshot): string;
  advanceEnvironment?(state: PuzzleSnapshot): PuzzleSnapshot;
}
