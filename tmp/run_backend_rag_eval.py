from __future__ import annotations

import json
from pathlib import Path

from backend.ai.rag_service import PuzzleRAGService


ROOT = Path(__file__).resolve().parents[1]
RESULT_JSON_PATH = ROOT / "tmp" / "backend_rag_eval_results.json"
RESULT_MD_PATH = ROOT / "tmp" / "backend_rag_eval_results.md"


def render_markdown(result: dict[str, object]) -> str:
    lines: list[str] = []
    lines.append("# Backend RAG Eval Results")
    lines.append("")
    lines.append(f"- Generated at (UTC): `{result['generated_at_utc']}`")
    lines.append(f"- Rule corpus size: `{result['rule_corpus_size']}`")
    lines.append(f"- Case corpus size: `{result['case_corpus_size']}`")
    lines.append(f"- Sample count: `{result['sample_count']}`")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    overall = result["overall"]
    for metric, value in overall.items():
        lines.append(f"- `{metric}`: `{value}`")
    lines.append("")
    lines.append("## By Category")
    lines.append("")
    for category, metrics in result["by_category"].items():
        lines.append(f"### {category}")
        for metric, value in metrics.items():
            lines.append(f"- `{metric}`: `{value}`")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    service = PuzzleRAGService()
    result = service.evaluate()
    RESULT_JSON_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    RESULT_MD_PATH.write_text(render_markdown(result), encoding="utf-8")
    print("Backend RAG evaluation finished.")
    print(f"Saved JSON: {RESULT_JSON_PATH}")
    print(f"Saved Markdown: {RESULT_MD_PATH}")


if __name__ == "__main__":
    main()
