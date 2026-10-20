"""Reusable deterministic stand-ins for the LLM generator and retriever.

Two consumers share these implementations:

1. Demo mode (``PAWPILOT_DEMO_MODE=1``): a zero-cost offline path — no API key,
   no Postgres, no network — that still exercises the full scenario pipeline.
2. The hermetic test-suite, which proves the deterministic tool layer never
   depends on LLM output.

``DemoGenerator`` mirrors the ``Generator`` method surface and return shapes;
``StaticDemoRetriever`` returns a fixed SOP chunk; ``LocalHashEmbedder`` provides
deterministic local embeddings (jieba tokens hashed into a fixed-dim vector) so
retrieval works without an embedding API.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any

import jieba


class DemoGenerator:
    """Stand-in for Generator: canned deterministic Chinese narration, recorded calls."""

    provider = "demo"
    model = "demo-model"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._latency_seconds = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _record(self, method: str, input_text: str, output_text: str, latency: float) -> None:
        self.calls.append(method)
        self._calls += 1
        # Deterministic rough token estimate (no tokenizer dependency).
        self._input_tokens += len(input_text) // 4
        self._output_tokens += len(output_text) // 4
        self._latency_seconds += latency

    def _snapshot(self) -> dict[str, Any]:
        return {
            "calls": self._calls,
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
            "latency_seconds": round(self._latency_seconds, 3),
        }

    def _meta(self, latency: float) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model, "latency": latency}

    # ------------------------------------------------------------------
    # Generator-compatible surface
    # ------------------------------------------------------------------
    async def answer_policy_question(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        start = time.perf_counter()
        if context_chunks:
            top = context_chunks[0]
            title = top.get("title") or top.get("doc_id") or "示例知识库"
            lines = [
                f"根据知识库《{title}》（{top.get('section') or '全文'}）：",
                "",
                (top.get("text") or "").strip()[:400],
            ]
            if len(context_chunks) > 1:
                others = "、".join(
                    f"《{c.get('title') or c.get('doc_id')}》" for c in context_chunks[1:3]
                )
                lines += ["", f"相关内容另见：{others}。"]
            lines += ["", "> Demo 模式：以上答案由本地检索结果直接拼接，未调用 LLM。"]
            answer = "\n".join(lines)
        else:
            answer = (
                "未在示例知识库中检索到相关内容。Demo 语料仅覆盖 Listing 规则、违禁词、"
                "差评回复 SOP 与 Demo 说明四类主题，请换个相关问题；配置真实 API key 后"
                "可使用完整知识库。"
            )
        latency = time.perf_counter() - start
        self._record("answer_policy_question", query, answer, latency)
        return {
            "answer": answer,
            "sources": [
                {"doc_id": c.get("doc_id"), "section": c.get("section"), "text": c.get("text")}
                for c in context_chunks
            ],
            "meta": self._meta(latency),
            "usage": self._snapshot(),
        }

    async def generate_listing(
        self,
        product_info: dict[str, Any],
        rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        start = time.perf_counter()
        product_type = product_info.get("product_type", "pet product")
        key_feature = product_info.get("key_feature", "durable design")
        material = product_info.get("material", "")
        size = product_info.get("size", "")
        brand = "PawPilot"
        title = f"{brand} {key_feature.title()} {product_type.title()}"
        if material:
            title += f", {material}"
        if size:
            title += f", {size}"
        listing = {
            "title": title[:180],
            "bullets": [
                f"DURABLE DESIGN: {key_feature} — built to outlast everyday play.",
                f"PET-SAFE MATERIALS: {material or 'carefully selected materials'}, gentle on teeth and gums.",
                f"RIGHT SIZE: {size or 'multiple sizes'} — check the size chart before ordering.",
                "EASY TO CLEAN: rinse with water and air-dry for daily hygiene.",
                "PAWPILOT QUALITY: designed by pet owners, backed by responsive support.",
            ],
            "description": (
                f"The {brand} {product_type} combines {key_feature} with "
                f"{material or 'quality materials'} for safe, everyday fun."
            ),
            "backend_keywords": f"{product_type}, {key_feature}, dog toy, pet supplies",
        }
        output = json.dumps(listing, ensure_ascii=False)
        latency = time.perf_counter() - start
        self._record("generate_listing", json.dumps(product_info, ensure_ascii=False), output, latency)
        return {"listing": listing, "meta": self._meta(latency), "usage": self._snapshot()}

    async def check_compliance(
        self,
        draft_text: str,
        rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        start = time.perf_counter()
        # The deterministic rule engine does the real audit; the demo "LLM
        # semantic check" simply reports nothing further.
        compliance = {"issues": [], "note": "demo mode: semantic check skipped (no LLM call)"}
        latency = time.perf_counter() - start
        self._record("check_compliance", draft_text, json.dumps(compliance), latency)
        return {"compliance": compliance, "meta": self._meta(latency), "usage": self._snapshot()}

    async def summarize_ops_digest(
        self, digest: dict[str, Any], knowledge: list[dict[str, Any]]
    ) -> dict[str, Any]:
        start = time.perf_counter()
        assert digest["alerts"], "digest must contain alerts before narration"
        summary = f"今日需优先处理 {len(digest['alerts'])} 项告警……"
        latency = time.perf_counter() - start
        self._record("summarize_ops_digest", json.dumps(digest, ensure_ascii=False), summary, latency)
        return {"summary": summary, "meta": self._meta(latency), "usage": self._snapshot()}

    async def narrate_sales_diagnosis(
        self, sku: str, diagnosis: dict[str, Any], knowledge: list[dict[str, Any]]
    ) -> dict[str, Any]:
        start = time.perf_counter()
        if diagnosis.get("status") == "normal":
            narrative = f"{sku} 各项指标处于正常波动区间，暂无需干预，建议持续观察。"
        else:
            narrative = f"{sku} 销量下滑的主要原因是评分下滑与广告暂停……"
        latency = time.perf_counter() - start
        self._record(
            "narrate_sales_diagnosis", json.dumps(diagnosis, ensure_ascii=False), narrative, latency
        )
        return {"narrative": narrative, "meta": self._meta(latency), "usage": self._snapshot()}

    async def synthesize_product_dev(
        self,
        product_type: str,
        voc: dict[str, Any],
        product_context: str,
        knowledge: list[dict[str, Any]],
    ) -> dict[str, Any]:
        start = time.perf_counter()
        assert voc["themes"], "VOC themes must be aggregated before synthesis"
        report = "竞品最集中的未满足需求是……建议改进规格……"
        latency = time.perf_counter() - start
        self._record("synthesize_product_dev", json.dumps(voc, ensure_ascii=False), report, latency)
        return {"report": report, "meta": self._meta(latency), "usage": self._snapshot()}


class StaticDemoRetriever:
    """Minimal stand-in retriever: always returns one fixed SOP chunk."""

    async def retrieve_texts(self, query: str, final_top_k: int = 5) -> list[dict[str, Any]]:
        return [
            {"doc_id": "negative_review_response_sop", "section": "Templates", "text": "模板 T1..."},
        ]


class LocalHashEmbedder:
    """Deterministic offline embedder aligned with the EmbeddingClient interface.

    jieba tokens are hashed (MD5, non-cryptographic) into a fixed-dimension
    signed feature vector, then L2-normalised. Identical text always yields an
    identical vector, so demo-mode retrieval is fully reproducible.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _vectorize(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in jieba.lcut(text):
            token = token.strip()
            if not token:
                continue
            digest = hashlib.md5(token.encode("utf-8"), usedforsecurity=False).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            vec[idx] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vectorize(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vectorize(text)
