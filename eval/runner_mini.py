"""Mini eval runner for a subset of review_analysis records.

Used to sanity-check the language-agnostic judge prompt when the full 102-record
eval is blocked by upstream model-provider instability.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from eval.runner import EvalRunner


async def main() -> None:
    dataset = Path(__file__).parent / "dataset.jsonl"
    records = []
    with dataset.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    review_records = [r for r in records if r.get("type") == "review_analysis"][:3]
    print(f"Running mini eval on {len(review_records)} review_analysis records...")

    runner = EvalRunner()
    results = []
    for record in review_records:
        result = await runner.evaluate_record(record)
        results.append(result)
        print(
            f"[{result.id}] recall={result.recall_at_k:.3f} "
            f"answer={result.answer_score:.3f} hallucination={result.hallucination_score:.3f}"
        )

    avg_answer = sum(r.answer_score for r in results if r.answer_score is not None) / len(results)
    avg_hallu = sum(r.hallucination_score for r in results if r.hallucination_score is not None) / len(results)
    print(f"\nMini avg: answer={avg_answer:.3f} hallucination={avg_hallu:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
