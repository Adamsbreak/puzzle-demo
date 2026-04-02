package com.puzzle.v1.model;

import java.util.List;
import java.util.Map;

public class PuzzleRequest {
  public Meta meta;
  public RulePack rulePack;
  public Board board;
  public List<Piece> pieces;
  public List<Zone> zones;

  public static class Meta {
    public String title;
    public String rulePackId;
  }

  public static class RulePack {
    public String id;
    public Solver solver;
    public List<Goal> goals;
  }

  public static class Solver {
    public Boolean enabled;
    public String objective;
    public Integer maxNodes;
    public Behavior behavior;
    public Interfaces interfaces;
    public Map<String, Object> extensionConfig;
  }

  public static class Behavior {
    public String targetLanePriority;
    public String edgeGoalRelaxation;
    public String stopGeneration;
  }

  public static class Interfaces {
    public String movePolicy;
    public String goalPolicy;
    public String validator;
  }

  public static class Goal {
    public String type;
  }

  public static class Board {
    public int rows;
    public int cols;
    public int cellSize;
    public List<List<Cell>> cells;
  }

  public static class Cell {
    public List<String> tags;
  }

  public static class Piece {
    public String id;
    public String name;
    public String typeId;
    public String role;
    public int row;
    public int col;
    public int w;
    public int h;
    public String moveRule;
    public Boolean movable;
  }

  public static class Zone {
    public String id;
    public String name;
    public String role;
    public String shapeKind;
    public Integer row;
    public Integer col;
    public String side;
    public Integer index;
    public int w;
    public int h;
    public String goalMode;
    public Map<String, List<String>> targetFilter;
  }
}
