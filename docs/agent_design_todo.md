# Agent Design TODO

## 1. Teach the agent to design puzzles, not only edit them

Goal: move from "modify an existing board" to "create or refine a playable puzzle from a blank or partial board".

Scope:
- Add a reliable seed-generation path for blank boards.
- Turn minimal validated puzzle cases into reusable design exemplars.
- Make the planner produce a design brief that separates generation instructions from review criteria.
- Let the generator work in stages: seed -> refine -> validate.

Deliverables:
- A canonical `DesignBrief` with generation goals and review rubric.
- A small curated case library of minimal valid puzzles.
- Retrieval hooks so planner/generator/critic can see similar past cases.
- A candidate search loop that keeps the best generated board instead of failing silently.

Acceptance:
- Blank-board requests can produce a playable candidate with at least one target and one goal zone.
- The generator can explain which seed pattern it used.
- The system can return a best-effort candidate even when the critic/controller is not fully satisfied.

## 2. Redesign the review layer

Goal: replace brittle all-or-nothing review gates with layered evaluation.

Scope:
- Keep hard constraints deterministic.
- Replace boolean soft-target checks with weighted scoring.
- Make the critic read planner-defined `review_rubric` instead of assuming tutorial-level goals.
- Distinguish `create` review from `modify` review.

Deliverables:
- Hard constraints: legality, solvability, board-size constraints.
- Soft scoring: difficulty shift, obstacle density, branching, readability, redundancy control, brief fit.
- Critic summary that explains why a candidate is promising even if it is not fully accepted.
- Controller logic that can return `proposed_with_warnings` for the best available candidate.

Acceptance:
- Complex or obstacle-heavy requests are not judged with tutorial-only standards.
- Rejected runs still expose the best candidate and the reasons it missed the target.
- Review output is useful for both debugging and future data collection.
