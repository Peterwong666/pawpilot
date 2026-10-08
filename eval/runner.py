"""Lightweight evaluation runner.

Supports:
- Retrieval metrics: Recall@k, MRR, nDCG@k (deterministic).
- Generation metrics: LLM-as-judge answer accuracy and hallucination score.
- Comparison across chunking strategies, retrieval modes, and LLM providers.

Outputs JSONL detail + Markdown report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.rag.generation.generator import Generator
from app.rag.retrieval.hybrid import HybridRetriever
from eval.metrics import mrr, ndcg_at_k, recall_at_k


@dataclass
class EvalResult:
    id: str
    q_type: str
    question: str
    gold_answer: str
    gold_doc_ids: list[str]
    retrieved_doc_ids: list[str]
    predicted_answer: str
    recall_at_k: float
    mrr: float
    ndcg_at_k: float
    answer_score: float | None
    hallucination_score: float | None


class EvalRunner:
    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        generator: Generator | None = None,
        top_k: int = 6,
    ) -> None:
        self.retriever = retriever or HybridRetriever()
        self.generator = generator or Generator(provider="deepseek")
        self.top_k = top_k

    def load_dataset(self, path: Path) -> list[dict[str, Any]]:
        records = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    async def evaluate_record(self, record: dict[str, Any]) -> EvalResult:
        import time

        t_start = time.perf_counter()
        question = record["question"]
        q_type = record["type"]
        gold_doc_ids = record["gold_doc_ids"]
        chunks = await self.retriever.retrieve_texts(question, final_top_k=self.top_k)
        # Deduplicate by doc_id while preserving retrieval order; RAG answers are grounded
        # in documents, not individual chunks.
        seen: set[str] = set()
        retrieved_doc_ids = []
        for c in chunks:
            doc_id = c["doc_id"]
            if doc_id not in seen:
                seen.add(doc_id)
                retrieved_doc_ids.append(doc_id)

        if q_type == "policy_qa":
            gen_result = await self.generator.answer_policy_question(question, chunks)
            predicted = gen_result["answer"]
        elif q_type == "listing_compliance":
            gen_result = await self.generator.check_compliance(question, chunks)
            predicted = json.dumps(gen_result.get("compliance", {}), ensure_ascii=False)
        elif q_type == "review_analysis":
            gen_result = await self.generator.analyze_reviews(
                record.get("sku", "PP-RT-102"), question, chunks
            )
            predicted = json.dumps(gen_result.get("analysis", {}), ensure_ascii=False)
        else:
            predicted = ""
            gen_result = {}

        rec = recall_at_k(gold_doc_ids, retrieved_doc_ids)
        mrr_score = mrr(gold_doc_ids, retrieved_doc_ids)
        ndcg = ndcg_at_k(gold_doc_ids, retrieved_doc_ids, self.top_k)
        answer_score = None
        hallucination_score = None
        if predicted:
            judge = await self._judge(question, record["gold_answer"], predicted)
            answer_score = judge.get("answer_score")
            hallucination_score = judge.get("hallucination_score")

        elapsed = time.perf_counter() - t_start
        print(f"[eval] {record['id']} ({q_type}) done in {elapsed:.1f}s", flush=True)
        return EvalResult(
            id=record["id"],
            q_type=q_type,
            question=question,
            gold_answer=record["gold_answer"],
            gold_doc_ids=gold_doc_ids,
            retrieved_doc_ids=retrieved_doc_ids,
            predicted_answer=predicted,
            recall_at_k=rec,
            mrr=mrr_score,
            ndcg_at_k=ndcg,
            answer_score=answer_score,
            hallucination_score=hallucination_score,
        )

    async def _judge(
        self, question: str, gold_answer: str, predicted_answer: str
    ) -> dict[str, float | None]:
        prompt = (
            "You are an evaluation judge. Compare the predicted answer to the gold answer for "
            "the following question. Output JSON with two fields: answer_score (0-1, where 1 "
            "means fully correct and complete) and hallucination_score (0-1, where 1 means "
            "significant unsupported claims).\n\n"
            "IMPORTANT: The predicted answer may be written in Chinese or English (or mix both). "
            "Judge semantic correctness only, regardless of language. Do NOT penalize the answer "
            "for being in a different language than the gold answer — a Chinese answer that "
            "conveys the same meaning as the English gold answer should score 1.0.\n\n"
            f"Question: {question}\n\n"
            f"Gold answer: {gold_answer}\n\n"
            f"Predicted answer: {predicted_answer}\n\n"
            "Output JSON only."
        )
        try:
            content, _ = await self.generator._chat(
                "You are an evaluation judge.",
                prompt,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            parsed = self.generator._safe_json_parse(content)
            return {
                "answer_score": float(parsed.get("answer_score", 0.0)),
                "hallucination_score": float(parsed.get("hallucination_score", 0.0)),
            }
        except Exception:
            return {"answer_score": None, "hallucination_score": None}

    async def run(self, dataset_path: Path, output_dir: Path) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        records = self.load_dataset(dataset_path)
        results: list[EvalResult] = []
        for record in records:
            result = await self.evaluate_record(record)
            results.append(result)

        detail_path = output_dir / "eval_detail.jsonl"
        with detail_path.open("w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r.__dict__, ensure_ascii=False) + "\n")

        metrics = self._aggregate(results)
        metrics["n"] = len(results)
        report_path = output_dir / "report.json"
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
        return metrics

    def _aggregate(self, results: list[EvalResult]) -> dict[str, Any]:
        if not results:
            return {}

        def avg(values: list[float | None]) -> float:
            clean = [v for v in values if v is not None]
            return sum(clean) / len(clean) if clean else 0.0

        overall = {
            "recall_at_k": avg([r.recall_at_k for r in results]),
            "mrr": avg([r.mrr for r in results]),
            "ndcg_at_k": avg([r.ndcg_at_k for r in results]),
            "answer_score": avg([r.answer_score for r in results]),
            "hallucination_score": avg([r.hallucination_score for r in results]),
        }
        grouped: dict[str, list[EvalResult]] = {}
        for r in results:
            grouped.setdefault(r.q_type, []).append(r)
        by_type: dict[str, dict[str, float]] = {}
        for q_type, group in grouped.items():
            by_type[q_type] = {
                "recall_at_k": avg([r.recall_at_k for r in group]),
                "mrr": avg([r.mrr for r in group]),
                "ndcg_at_k": avg([r.ndcg_at_k for r in group]),
                "answer_score": avg([r.answer_score for r in group]),
                "hallucination_score": avg([r.hallucination_score for r in group]),
            }
        return {"overall": overall, "by_type": by_type}


async def main() -> None:
    dataset = Path(__file__).parent / "dataset.jsonl"
    output = Path(__file__).parent / "reports"
    runner = EvalRunner()
    metrics = await runner.run(dataset, output)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
