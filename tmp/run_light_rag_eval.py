from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "docs" / "light_rag_corpus.json"
DATASET_PATH = ROOT / "docs" / "light_rag_eval_dataset.json"
RESULT_JSON_PATH = ROOT / "tmp" / "light_rag_eval_results.json"
RESULT_MD_PATH = ROOT / "tmp" / "light_rag_eval_results.md"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def tokenize(text: str) -> list[str]:
    lowered = text.lower()
    word_tokens = re.findall(r"[a-z0-9\-\_]+", lowered)
    chinese_chars = [ch for ch in lowered if "\u4e00" <= ch <= "\u9fff"]
    return word_tokens + chinese_chars


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def score_entry(query: str, entry: dict[str, Any]) -> float:
    query_norm = normalize_text(query)
    query_tokens = set(tokenize(query))
    haystack_parts = [
        entry.get("title", ""),
        entry.get("summary", ""),
        " ".join(entry.get("keywords", []) or []),
        entry.get("id", ""),
    ]
    haystack = " ".join(haystack_parts)
    haystack_tokens = set(tokenize(haystack))

    overlap = len(query_tokens.intersection(haystack_tokens))
    score = float(overlap)

    for keyword in entry.get("keywords", []) or []:
        keyword_norm = normalize_text(str(keyword))
        if keyword_norm and keyword_norm in query_norm:
            score += 3.0
        else:
            keyword_tokens = set(tokenize(str(keyword)))
            if keyword_tokens:
                score += 0.25 * len(query_tokens.intersection(keyword_tokens))

    title_norm = normalize_text(entry.get("title", ""))
    if title_norm and title_norm in query_norm:
        score += 4.0

    entry_id = normalize_text(entry.get("id", ""))
    if entry_id and entry_id.split(".")[-1] in query_norm:
        score += 2.0

    if entry.get("type") == "rule_doc":
        if any(token in query_norm for token in ("why", "difference", "rule", "rules", "interface", "architecture", "bridge")):
            score += 0.2
    elif entry.get("type") == "case":
        if any(token in query_norm for token in ("case", "example", "regression", "tc")):
            score += 0.2

    return score


def rank_entries(query: str, corpus_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = []
    for entry in corpus_entries:
        score = score_entry(query, entry)
        ranked.append(
            {
                "id": entry["id"],
                "type": entry["type"],
                "title": entry["title"],
                "score": round(score, 4),
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["id"]))
    return ranked


def reciprocal_rank(ranked_ids: list[str], expected_ids: set[str]) -> float:
    for index, entry_id in enumerate(ranked_ids, start=1):
        if entry_id in expected_ids:
            return 1.0 / index
    return 0.0


def precision_at_k(ranked_ids: list[str], expected_ids: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top_ids = ranked_ids[:k]
    if not top_ids:
        return 0.0
    hits = sum(1 for entry_id in top_ids if entry_id in expected_ids)
    return hits / len(top_ids)


def recall_at_k(ranked_ids: list[str], expected_ids: set[str], k: int) -> float:
    if not expected_ids:
        return 1.0
    hits = sum(1 for entry_id in ranked_ids[:k] if entry_id in expected_ids)
    return hits / len(expected_ids)


def evaluate(corpus: dict[str, Any], dataset: dict[str, Any], k_values: tuple[int, ...] = (1, 3, 5)) -> dict[str, Any]:
    entries = corpus["entries"]
    samples = dataset["samples"]

    overall_metrics: dict[str, list[float]] = defaultdict(list)
    category_metrics: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    per_sample_results: list[dict[str, Any]] = []

    for sample in samples:
        expected_ids = set(sample.get("expected_rule_ids", []) + sample.get("expected_case_ids", []))
        ranked = rank_entries(sample["query"], entries)
        ranked_ids = [item["id"] for item in ranked]

        sample_result = {
            "id": sample["id"],
            "category": sample["category"],
            "query": sample["query"],
            "expected_ids": sorted(expected_ids),
            "top_hits": ranked[:5],
            "metrics": {},
        }

        rr = reciprocal_rank(ranked_ids, expected_ids)
        overall_metrics["mrr"].append(rr)
        category_metrics[sample["category"]]["mrr"].append(rr)
        sample_result["metrics"]["mrr"] = round(rr, 4)

        for k in k_values:
            hit = 1.0 if any(entry_id in expected_ids for entry_id in ranked_ids[:k]) else 0.0
            precision = precision_at_k(ranked_ids, expected_ids, k)
            recall = recall_at_k(ranked_ids, expected_ids, k)

            overall_metrics[f"hit_rate@{k}"].append(hit)
            overall_metrics[f"precision@{k}"].append(precision)
            overall_metrics[f"recall@{k}"].append(recall)

            category_metrics[sample["category"]][f"hit_rate@{k}"].append(hit)
            category_metrics[sample["category"]][f"precision@{k}"].append(precision)
            category_metrics[sample["category"]][f"recall@{k}"].append(recall)

            sample_result["metrics"][f"hit_rate@{k}"] = round(hit, 4)
            sample_result["metrics"][f"precision@{k}"] = round(precision, 4)
            sample_result["metrics"][f"recall@{k}"] = round(recall, 4)

        per_sample_results.append(sample_result)

    def summarize(metric_lists: dict[str, list[float]]) -> dict[str, float]:
        return {
            name: round(sum(values) / len(values), 4) if values else 0.0
            for name, values in sorted(metric_lists.items())
        }

    category_summary = {
        category: summarize(metrics)
        for category, metrics in sorted(category_metrics.items())
    }

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "corpus_size": len(entries),
        "sample_count": len(samples),
        "k_values": list(k_values),
        "overall": summarize(overall_metrics),
        "by_category": category_summary,
        "samples": per_sample_results,
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Lightweight RAG Eval Results")
    lines.append("")
    lines.append(f"- Generated at (UTC): `{result['generated_at_utc']}`")
    lines.append(f"- Corpus size: `{result['corpus_size']}`")
    lines.append(f"- Sample count: `{result['sample_count']}`")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    for metric, value in result["overall"].items():
        lines.append(f"- `{metric}`: `{value}`")
    lines.append("")
    lines.append("## By Category")
    lines.append("")
    for category, metrics in result["by_category"].items():
        lines.append(f"### {category}")
        for metric, value in metrics.items():
            lines.append(f"- `{metric}`: `{value}`")
        lines.append("")
    lines.append("## Sample Highlights")
    lines.append("")
    for sample in result["samples"][:8]:
        lines.append(f"### {sample['id']} - {sample['category']}")
        lines.append(f"- Query: {sample['query']}")
        lines.append(f"- Expected: {', '.join(sample['expected_ids'])}")
        lines.append(
            "- Top 3: "
            + ", ".join(f"{item['id']} ({item['score']})" for item in sample["top_hits"][:3])
        )
        lines.append(f"- MRR: `{sample['metrics']['mrr']}`")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    corpus = load_json(CORPUS_PATH)
    dataset = load_json(DATASET_PATH)
    result = evaluate(corpus, dataset)

    RESULT_JSON_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    RESULT_MD_PATH.write_text(render_markdown(result), encoding="utf-8")

    print("Lightweight RAG evaluation finished.")
    print(f"Corpus size: {result['corpus_size']}")
    print(f"Sample count: {result['sample_count']}")
    for metric, value in result["overall"].items():
        print(f"{metric}: {value}")
    print(f"Saved JSON: {RESULT_JSON_PATH}")
    print(f"Saved Markdown: {RESULT_MD_PATH}")


if __name__ == "__main__":
    main()
