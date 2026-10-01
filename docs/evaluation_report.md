# PawPilot Evaluation Report

Reproducible offline evaluation of the PawPilot RAG + Agent stack.

- **Dataset**: `eval/dataset.jsonl`, 102 QA pairs (policy QA / listing compliance / review analysis).
- **Runner**: `eval/runner.py`
- **Raw output**: `eval/reports/report.json` (aggregates), `eval/reports/eval_detail.jsonl` (per-question traces).

## How to reproduce

```bash
# 1. Populate the knowledge base (requires SILICONFLOW_API_KEY)
uv run python scripts/ingest.py --reset

# 2. Run the full evaluation
uv run python eval/runner.py
```

## Metrics

| Metric | Meaning |
|---|---|
| `recall_at_k` | Fraction of gold documents present in the top-k retrieved documents. |
| `mrr` | Mean reciprocal rank of the first relevant document. |
| `ndcg_at_k` | Ranking quality weighted by position. |
| `answer_score` | LLM-as-judge score (0–1) for answer correctness vs. gold answer. |
| `hallucination_score` | LLM-as-judge score (0–1); lower is better. |

## Results (n = 102, k = 6)

### Overall

| Metric | Value |
|---|---|
| Recall@6 | 0.863 |
| MRR | 0.823 |
| nDCG@6 | 0.793 |
| Answer score | 0.875 |
| Hallucination score | 0.176 |

### By scenario

| Scenario | Recall@6 | MRR | nDCG@6 | Answer | Hallucination |
|---|---|---|---|---|---|
| Policy QA | 0.976 | 0.896 | 0.907 | 0.934 | 0.148 |
| Listing compliance | 0.700 | 0.567 | 0.559 | 0.920 | 0.080 |
| Review analysis | 0.675 | 0.854 | 0.675 | 0.645 | 0.360 |

## Reading the numbers

- **Policy QA is the strongest scenario.** The knowledge base has dense, well-structured
  English policy documents, so both retrieval and generation score high.
- **Listing compliance has lower retrieval but high answer quality.** Its questions map to
  multiple rule documents at once, so a single gold `doc_id` list under-credits partially
  correct retrievals. Answer correctness stays high because the generator sees enough context.
- **Review analysis is the weakest.** It depends on *simulated* operational data (DuckDB)
  rather than the document index, so retrieval recall is inherently limited and the
  hallucination score is highest. This is expected and documented as a known limitation.

## Known limitations

1. `gold_doc_ids` are curated per question; some questions are legitimately answerable from
   more than one document, which penalizes recall.
2. Review-analysis evaluation mixes document retrieval with structured-data reasoning; the
   current metrics only score the retrieval half.
3. LLM-as-judge scores vary run-to-run; absolute values should be compared across
   configurations (chunking strategy, with/without rerank), not treated as fixed truths.
