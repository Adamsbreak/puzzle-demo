package com.puzzle.v1.model;

import java.util.List;

public class PuzzleResponse {
  public String status;
  public String summary;
  public String rulePackId;
  public String puzzleTitle;
  public Integer exploredNodes;
  public Integer stepCount;
  public List<SolutionStep> steps;
}
