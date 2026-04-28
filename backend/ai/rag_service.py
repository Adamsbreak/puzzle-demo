from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from backend.ai.case_rag import CaseRAG
from backend.ai.retrieval import SearchHit, build_context_block
from backend.ai.rules_rag import RulesRAG


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = ROOT_DIR / "docs" / "light_rag_eval_dataset.json"


class PuzzleRAGService:
    def __init__(self, rules_rag: RulesRAG | None = None, case_rag: CaseRAG | None = None) -> None:
        self.rules_rag = rules_rag or RulesRAG()
        self.case_rag = case_rag or CaseRAG()

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        include_rules: bool = True,
        include_cases: bool = True,
        build_context: bool = True,
    ) -> dict[str, Any]:
        rule_hits = self.rules_rag.search(query, top_k=top_k) if include_rules else []
        case_hits = self.case_rag.search(query, top_k=top_k) if include_cases else []
        merged_hits = self._merge_hits(rule_hits, case_hits, top_k=top_k)
        source_counts = Counter(hit.type for hit in merged_hits)
        return {
            "query": query,
            "totalHits": len(merged_hits),
            "hits": [hit.as_dict() for hit in merged_hits],
            "context": build_context_block(query, rule_hits, case_hits) if build_context else None,
            "sourceCounts": dict(source_counts),
        }

    def evaluate(
        self,
        *,
        dataset_path: str | None = None,
        top_k_values: Iterable[int] = (1, 3, 5),
        include_rules: bool = True,
        include_cases: bool = True,
    ) -> dict[str, Any]:
        path = Path(dataset_path) if dataset_path else DEFAULT_DATASET_PATH
        dataset = json.loads(path.read_text(encoding="utf-8"))
        k_values = tuple(sorted({max(1, int(value)) for value in top_k_values}))

        overall_metrics: dict[str, list[float]] = defaultdict(list)
        category_metrics: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        samples: list[dict[str, Any]] = []

        max_k = max(k_values)
        for sample in dataset.get("samples", []):
            expected_ids = set(sample.get("expected_rule_ids", []) + sample.get("expected_case_ids", []))
            result = self.search(
                sample["query"],
                top_k=max_k,
                include_rules=include_rules,
                include_cases=include_cases,
                build_context=False,
            )
            ranked_ids = [hit["id"] for hit in result["hits"]]
            sample_metrics: dict[str, float] = {}
            rr = _reciprocal_rank(ranked_ids, expected_ids)
            overall_metrics["mrr"].append(rr)
            category_metrics[sample["category"]]["mrr"].append(rr)
            sample_metrics["mrr"] = round(rr, 4)

            for k in k_values:
                hit = 1.0 if any(entry_id in expected_ids for entry_id in ranked_ids[:k]) else 0.0
                precision = _precision_at_k(ranked_ids, expected_ids, k)
                recall = _recall_at_k(ranked_ids, expected_ids, k)

                overall_metrics[f"hit_rate@{k}"].append(hit)
                overall_metrics[f"precision@{k}"].append(precision)
                overall_metrics[f"recall@{k}"].append(recall)

                category_metrics[sample["category"]][f"hit_rate@{k}"].append(hit)
                category_metrics[sample["category"]][f"precision@{k}"].append(precision)
                category_metrics[sample["category"]][f"recall@{k}"].append(recall)

                sample_metrics[f"hit_rate@{k}"] = round(hit, 4)
                sample_metrics[f"precision@{k}"] = round(precision, 4)
                sample_metrics[f"recall@{k}"] = round(recall, 4)

            samples.append(
                {
                    "id": sample["id"],
                    "category": sample["category"],
                    "query": sample["query"],
                    "expected_ids": sorted(expected_ids),
                    "top_hits": result["hits"][:5],
                    "metrics": sample_metrics,
                }
            )

        return {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "dataset_path": str(path),
            "rule_corpus_size": len(self.rules_rag.entries),
            "case_corpus_size": len(self.case_rag.entries),
            "sample_count": len(samples),
            "k_values": list(k_values),
            "overall": _summarize_metric_lists(overall_metrics),
            "by_category": {
                category: _summarize_metric_lists(metric_lists)
                for category, metric_lists in sorted(category_metrics.items())
            },
            "samples": samples,
        }

    def _merge_hits(self, rule_hits: list[SearchHit], case_hits: list[SearchHit], *, top_k: int) -> list[SearchHit]:
        combined = list(rule_hits) + list(case_hits)
        combined.sort(key=lambda hit: (-hit.score, hit.id))
        return combined[:top_k]


def _reciprocal_rank(ranked_ids: list[str], expected_ids: set[str]) -> float:
    for index, entry_id in enumerate(ranked_ids, start=1):
        if entry_id in expected_ids:
            return 1.0 / index
    return 0.0


def _precision_at_k(ranked_ids: list[str], expected_ids: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top_ids = ranked_ids[:k]
    if not top_ids:
        return 0.0
    hits = sum(1 for entry_id in top_ids if entry_id in expected_ids)
    return hits / len(top_ids)


def _recall_at_k(ranked_ids: list[str], expected_ids: set[str], k: int) -> float:
    if not expected_ids:
        return 1.0
    hits = sum(1 for entry_id in ranked_ids[:k] if entry_id in expected_ids)
    return hits / len(expected_ids)


def _summarize_metric_lists(metric_lists: dict[str, list[float]]) -> dict[str, float]:
    return {
        name: round(sum(values) / len(values), 4) if values else 0.0
        for name, values in sorted(metric_lists.items())
    }
