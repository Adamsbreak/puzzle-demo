package com.puzzle.v1;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.puzzle.v1.model.PuzzleRequest;
import com.puzzle.v1.model.PuzzleResponse;
import java.io.IOException;

public final class SolverMain {
  private SolverMain() {}

  public static void main(String[] args) throws IOException {
    ObjectMapper mapper =
        new ObjectMapper()
            .enable(SerializationFeature.INDENT_OUTPUT)
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
    PuzzleRequest request = mapper.readValue(System.in, PuzzleRequest.class);
    PuzzleResponse response = StaticSolver.solve(request);
    mapper.writeValue(System.out, response);
  }
}
