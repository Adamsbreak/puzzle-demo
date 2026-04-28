# RAG Plan B

This document describes the fuller source-backed RAG path for the Puzzle V1 project.

## Scope

Plan A provided:

- a curated corpus manifest
- a lightweight offline dataset
- a lexical evaluation script

Plan B keeps those assets but moves retrieval into backend modules that can be reused by HTTP routes and future agent stages.

## Modules

- `backend/ai/retrieval.py`
  Shared lexical retrieval primitives, corpus entries, hit formatting, and context assembly.
- `backend/ai/rules_rag.py`
  Loads rule knowledge from `docs/light_rag_corpus.json`, with a fallback path that can split raw markdown sources into sections.
- `backend/ai/case_rag.py`
  Builds case entries directly from `v1/java-solver/manual-cases/*.json` and merges them with curated manifest summaries when available.
- `backend/ai/rag_service.py`
  Unified service that merges rule and case hits, builds agent-ready context, and evaluates retrieval quality against `docs/light_rag_eval_dataset.json`.
- `backend/ai/orchestrator.py`
  Minimal source-backed orchestrator that keeps `/api/ai/level-agent` runnable and injects RAG search results into deterministic level analysis.

## HTTP Endpoints

- `POST /api/ai/rag/search`
  Query rules and cases together and return merged hits plus a compact context block.
- `POST /api/ai/rag/evaluate`
  Run the current backend retriever against the lightweight evaluation dataset.
- `POST /api/ai/level-agent`
  Deterministic analysis fallback that now includes retrieved rule and case grounding.

## Current Retrieval Style

The backend retriever is still lexical and intentionally lightweight:

- token overlap
- keyword exact-match boosts
- title and id-tail boosts
- rule/case type hints

This keeps the system easy to inspect and leaves a clean seam for later upgrades such as:

- synonym expansion
- reranking
- embedding-based retrieval
- query rewriting
- planner / generator / critic specific retrieval policies

## Evaluation

Two evaluation entry points now exist:

- `tmp/run_light_rag_eval.js`
  Existing offline lexical baseline in Node.
- `tmp/run_backend_rag_eval.py`
  Backend-oriented Python entry point that exercises `PuzzleRAGService.evaluate()`.

## Next Step Ideas

1. Split broad rule chunks like `entities_and_tags` into smaller topic-specific chunks.
2. Add synonym dictionaries for phrases such as "middle stop", "final-step-only", and "can't pass through".
3. Add query intent routing so analysis, diagnosis, and edit requests use different retrieval mixes.
4. Feed `rag_service.search(...).context` into future planner / critic prompts instead of relying on a single generic context block.
