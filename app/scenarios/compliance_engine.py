"""Deterministic listing-compliance rule engine.

Complements the LLM-based compliance check with cheap, auditable, deterministic rules
extracted from the knowledge base:

- ``amazon_policies/prohibited_listing_words.md`` — medical / antimicrobial / FDA claims,
  auto-blocked marketing phrases, unqualified environmental claims, competitor references.
- ``amazon_policies/listing_style_guide.md`` — title length, all-caps, non-standard title
  characters, bullet count/length, backend-keyword byte budget, description length.

Every issue carries a stable ``rule_id`` so findings are auditable and testable, unlike
LLM-only checks whose output drifts between runs.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

TITLE_MAX_CHARS = 200
BULLET_MAX_CHARS = 500
BULLET_EXPECTED_COUNT = 5
BACKEND_KEYWORDS_MAX_BYTES = 250
DESCRIPTION_MAX_CHARS = 2000

_NONSTANDARD_TITLE_CHARS = set("!$?_~{}^¬¦")

# (rule_id, category, severity, regex, message, fix_hint)
_WORD_RULES: list[tuple[str, str, str, re.Pattern[str], str, str]] = [
    (
        "R101", "medical_claim", "critical",
        re.compile(r"\bcures?\b|\bheals?\b|\bremed(?:y|ies)\b", re.IGNORECASE),
        "Medical/therapeutic claim: pet accessories making treatment claims are treated as "
        "unapproved drugs and listings are suppressed.",
        "Describe comfort/support factually, e.g. 'provides joint support'.",
    ),
    (
        "R102", "medical_claim", "critical",
        re.compile(
            r"\btreat(?:s|ing|ed)?\s+(?:arthritis|disease|pain|illness|infection|allerg\w+|inflammation)\b"
            r"|\bprevents?\s+disease\b|\beliminates?\s+pain\b",
            re.IGNORECASE,
        ),
        "Treatment/prevention claim for a specific condition requires drug approval.",
        "State what the product does physically (e.g. 'supports mobility') without naming diseases.",
    ),
    (
        "R103", "antimicrobial_claim", "critical",
        re.compile(r"\bantibacterial\b|\bantimicrobial\b|\bkills\s+germs?\b|\bdisinfect\w*\b", re.IGNORECASE),
        "Antimicrobial claims are pesticide claims under FIFRA and require an EPA registration number.",
        "Use 'odor-resistant material' or 'easy-to-clean surface' instead.",
    ),
    (
        "R104", "fda_claim", "critical",
        re.compile(r"\bFDA[\s-]*(?:approved|certified)\b", re.IGNORECASE),
        "FDA does not 'approve' pet accessories; only registered facilities/devices may use such phrasing.",
        "If true and documented, use 'Made in an FDA-registered facility'.",
    ),
    (
        "R105", "prohibited_marketing", "critical",
        re.compile(
            r"\bfree\s+shipping\b|\b100%\s+satisfaction\s+guaranteed\b|\bmoney[-\s]?back\s+guarantee\b"
            r"|\bguaranteed\s+results\b|\bmiracle\b",
            re.IGNORECASE,
        ),
        "Promotional/guarantee phrases are auto-blocked by listing quality automation.",
        "Remove the promotional phrasing; a factual warranty line may go in the final bullet.",
    ),
    (
        "R106", "prohibited_marketing", "critical",
        re.compile(
            r"\bbest\b|\bbestseller\b|\bbest\s+seller\b|#\s?1\b|\btop\s+rated\b|\bcheapest\b"
            r"|\blowest\s+price\b|\bmost\s+popular\b|\bamazon'?s\s+choice\b|\bhot\s+sale\b"
            r"|\blimited\s+time\s+offer\b|\bbuy\s+now\b|\bwhile\s+supplies\s+last\b",
            re.IGNORECASE,
        ),
        "Subjective ranking / urgency / badge-reference phrases are prohibited in any listing field.",
        "Replace with verifiable product attributes (material, size, quantity).",
    ),
    (
        "R107", "environmental_claim", "warning",
        re.compile(r"\beco[-\s]?friendly\b|\bsustainable\b", re.IGNORECASE),
        "Unqualified environmental claims are flagged per FTC Green Guides.",
        "Qualify the claim (e.g. 'packaging made from 90% recycled cardboard') or remove it.",
    ),
    (
        "R108", "competitor_reference", "warning",
        re.compile(r"\bbetter\s+than\s+\w+", re.IGNORECASE),
        "Comparative claims naming another product risk IP complaints.",
        "State your own product's measurable advantage without naming competitors.",
    ),
]

_CONTACT_RE = re.compile(
    r"https?://|www\.|[\w.+-]+@[\w-]+\.\w+|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", re.IGNORECASE
)


@dataclass
class ComplianceIssue:
    """One deterministic rule-engine finding."""

    rule_id: str
    category: str
    severity: str
    field: str
    match: str
    message: str
    fix_hint: str
    source: str = "rule"


def _word_issues(text: str, field: str) -> list[ComplianceIssue]:
    issues: list[ComplianceIssue] = []
    for rule_id, category, severity, pattern, message, fix_hint in _WORD_RULES:
        m = pattern.search(text)
        if m:
            issues.append(
                ComplianceIssue(rule_id, category, severity, field, m.group(0), message, fix_hint)
            )
    return issues


def _title_issues(title: str) -> list[ComplianceIssue]:
    issues: list[ComplianceIssue] = []
    if len(title) > TITLE_MAX_CHARS:
        issues.append(
            ComplianceIssue(
                "R201", "structure", "critical", "title",
                f"{len(title)} chars",
                f"Pet Supplies titles are capped at {TITLE_MAX_CHARS} characters; longer titles "
                "are suppressed at submission.",
                "Trim to Brand + Product Type + Key Attribute + Size/Quantity + Color.",
            )
        )
    if len(title) > 10 and title.isupper():
        issues.append(
            ComplianceIssue(
                "R202", "structure", "warning", "title",
                "ALL CAPS title",
                "All-caps titles are auto-flagged by listing quality checks and degrade conversion.",
                "Use title case (capitalize each word except short prepositions/articles).",
            )
        )
    bad_chars = sorted({ch for ch in title if ch in _NONSTANDARD_TITLE_CHARS})
    if bad_chars:
        issues.append(
            ComplianceIssue(
                "R203", "structure", "warning", "title",
                "".join(bad_chars),
                "Non-standard symbols are not allowed in titles.",
                "Keep only hyphens, commas, periods, and forward slashes.",
            )
        )
    if _CONTACT_RE.search(title):
        m = _CONTACT_RE.search(title)
        issues.append(
            ComplianceIssue(
                "R204", "structure", "critical", "title",
                m.group(0) if m else "",
                "Seller contact details, URLs, or prices must not appear in the title.",
                "Remove contact/pricing info from the title.",
            )
        )
    return issues


def _bullet_issues(bullets: list[str], title: str) -> list[ComplianceIssue]:
    issues: list[ComplianceIssue] = []
    if len(bullets) != BULLET_EXPECTED_COUNT:
        issues.append(
            ComplianceIssue(
                "R301", "structure", "warning", "bullets",
                f"{len(bullets)} bullets",
                f"Amazon expects exactly {BULLET_EXPECTED_COUNT} bullet points; missing bullets waste "
                "indexed keyword space.",
                f"Write exactly {BULLET_EXPECTED_COUNT} bullets, leading with the primary benefit.",
            )
        )
    for i, bullet in enumerate(bullets, start=1):
        if len(bullet) > BULLET_MAX_CHARS:
            issues.append(
                ComplianceIssue(
                    "R302", "structure", "critical", f"bullets[{i}]",
                    f"{len(bullet)} chars",
                    f"Bullets are capped at {BULLET_MAX_CHARS} characters.",
                    "Trim to 150-250 characters for mobile readability.",
                )
            )
        if bullet.rstrip().endswith("."):
            issues.append(
                ComplianceIssue(
                    "R303", "structure", "warning", f"bullets[{i}]",
                    "ends with '.'",
                    "Bullets should be sentence fragments without a full stop.",
                    "Drop the trailing period.",
                )
            )
        if title and bullet.strip().lower() == title.strip().lower():
            issues.append(
                ComplianceIssue(
                    "R304", "structure", "warning", f"bullets[{i}]",
                    "duplicates title",
                    "Repeating the title verbatim in a bullet adds no search value.",
                    "Rewrite the bullet as a benefit statement.",
                )
            )
    return issues


def _backend_keywords_issues(backend_keywords: str) -> list[ComplianceIssue]:
    issues: list[ComplianceIssue] = []
    size = len(backend_keywords.encode("utf-8"))
    if size > BACKEND_KEYWORDS_MAX_BYTES:
        issues.append(
            ComplianceIssue(
                "R401", "structure", "critical", "backend_keywords",
                f"{size} bytes",
                f"Backend search terms are capped at {BACKEND_KEYWORDS_MAX_BYTES} bytes; excess "
                "terms are silently dropped.",
                "Prioritize long-tail synonyms; never include competitor trademarks.",
            )
        )
    return issues


def _description_issues(description: str) -> list[ComplianceIssue]:
    issues: list[ComplianceIssue] = []
    if len(description) > DESCRIPTION_MAX_CHARS:
        issues.append(
            ComplianceIssue(
                "R501", "structure", "warning", "description",
                f"{len(description)} chars",
                f"Descriptions without A+ Content are capped at {DESCRIPTION_MAX_CHARS} characters.",
                "Shorten the description or move content to A+ modules.",
            )
        )
    return issues


class ComplianceRuleEngine:
    """Deterministic pre-flight check over a structured listing draft."""

    def check_listing(self, listing: dict[str, Any]) -> list[dict[str, Any]]:
        title = str(listing.get("title", "") or "")
        bullets_raw = listing.get("bullets", [])
        bullets = [str(b) for b in bullets_raw] if isinstance(bullets_raw, list) else []
        backend_keywords = str(listing.get("backend_keywords", "") or "")
        description = str(listing.get("description", "") or "")

        issues: list[ComplianceIssue] = []
        issues += _word_issues(title, "title")
        issues += _title_issues(title)
        for i, bullet in enumerate(bullets, start=1):
            issues += _word_issues(bullet, f"bullets[{i}]")
        issues += _bullet_issues(bullets, title)
        issues += _word_issues(backend_keywords, "backend_keywords")
        issues += _backend_keywords_issues(backend_keywords)
        issues += _word_issues(description, "description")
        issues += _description_issues(description)
        return [asdict(issue) for issue in issues]

    def check_text(self, draft_text: str) -> list[dict[str, Any]]:
        """Word-level scan for unstructured drafts (e.g. raw listing text)."""
        issues: list[ComplianceIssue] = []
        for line_no, line in enumerate(draft_text.splitlines(), start=1):
            found = _word_issues(line, f"line[{line_no}]")
            issues.extend(found)
        return [asdict(issue) for issue in issues]

    def check_draft(self, draft: str | dict[str, Any]) -> list[dict[str, Any]]:
        """Accept either a structured listing dict or raw text (JSON blob or free text)."""
        if isinstance(draft, dict):
            return self.check_listing(draft)
        text = draft.strip()
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return self.check_listing(parsed)
            except json.JSONDecodeError:
                pass
        return self.check_text(text)
