"""Versioned prompt templates for the three PawPilot scenarios.

Each prompt is a function returning a system message and a user message so that the generation
layer can log/audit them deterministically.
"""

from __future__ import annotations

from typing import Any

PromptPair = tuple[str, str]


def policy_qa_prompt(query: str, context_chunks: list[dict[str, Any]]) -> PromptPair:
    context = _format_context(context_chunks)
    system = (
        "You are PawPilot, an Amazon pet-supplies operations assistant. Answer the user's "
        "question using ONLY the provided knowledge base excerpts. Cite the source document "
        "and section for each key fact using [source: doc_id, section]. If the answer is not "
        "in the context, say so clearly. Do not make up policies, numbers, or URLs."
    )
    user = f"Question: {query}\n\nContext excerpts:\n{context}\n\nProvide a concise, factual answer with citations."
    return system, user


def listing_generation_prompt(product_info: dict[str, Any], rules: list[dict[str, Any]]) -> PromptPair:
    rules_context = _format_context(rules)
    system = (
        "You are an Amazon listing copywriter for the Pet Supplies category. Generate an "
        "English product listing (title, 5 bullets, backend keywords, and a short description) "
        "from the product information below. Then review your draft against Amazon's listing "
        "style and prohibited-word rules. Output structured JSON with fields: title, bullets "
        "(list), backend_keywords (string), description, compliance_issues (list)."
    )
    user = (
        f"Product information:\n{_format_product_info(product_info)}\n\n"
        f"Amazon rules to follow:\n{rules_context}\n\n"
        "Generate the listing in valid JSON."
    )
    return system, user


def review_analysis_prompt(
    asin: str,
    reviews_summary: str,
    knowledge_chunks: list[dict[str, Any]],
) -> PromptPair:
    context = _format_context(knowledge_chunks)
    system = (
        "You are a customer-insights analyst for an Amazon pet-supplies brand. Analyze the "
        "provided review summary for the ASIN, classify themes, estimate sentiment share, and "
        "recommend concrete action items. Ground your recommendations in the provided company "
        "SOP and knowledge base when possible. Output structured JSON."
    )
    user = (
        f"ASIN: {asin}\n\nReview summary:\n{reviews_summary}\n\n"
        f"Reference knowledge:\n{context}\n\n"
        "Output JSON with fields: themes (list of {theme, count, sentiment, sample_quotes}), "
        "top_issues, recommended_actions (list of {action, owner, expected_impact, source})."
    )
    return system, user


def compliance_check_prompt(draft_text: str, rules: list[dict[str, Any]]) -> PromptPair:
    rules_context = _format_context(rules)
    system = (
        "You are an Amazon listing compliance checker. Review the draft listing text against "
        "the provided rules. Identify any prohibited words, unsupported claims, or policy "
        "violations. Suggest concrete rewrites. Output JSON with fields: passed (bool), "
        "issues (list of {severity, field, word_or_phrase, reason, suggested_rewrite})."
    )
    user = f"Draft listing text:\n{draft_text}\n\nRules:\n{rules_context}\n\nOutput JSON only."
    return system, user


def _format_context(chunks: list[dict[str, Any]]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        doc_id = chunk.get("doc_id", "unknown")
        section = chunk.get("section", "unknown")
        text = chunk.get("text", "").strip()
        parts.append(f"[{i}] Source: {doc_id} | Section: {section}\n{text}")
    return "\n\n".join(parts)


def _format_product_info(info: dict[str, Any]) -> str:
    lines = []
    for key, value in info.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)
