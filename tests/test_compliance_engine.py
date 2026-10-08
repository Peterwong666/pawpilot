"""Tests for the deterministic listing-compliance rule engine."""

from __future__ import annotations

from app.scenarios.compliance_engine import ComplianceRuleEngine


def _listing(**overrides: object) -> dict[str, object]:
    base = {
        "title": "PawPilot Cotton Rope Dog Toy for Aggressive Chewers, Large, 3-Pack",
        "bullets": [
            "Keeps aggressive chewers engaged for hours with thick knotted cotton rope",
            "Made of 100% natural cotton with AZO-free dye, safe to chew",
            "Large size fits medium and large dogs from 15 to 30 kg",
            "Machine washable, air dry for easy cleaning",
            "Backed by a 12-month manufacturer warranty",
        ],
        "backend_keywords": "rope dog toy chew large cotton natural",
        "description": "A durable cotton rope toy for interactive play.",
    }
    base.update(overrides)
    return base


def test_clean_listing_passes() -> None:
    engine = ComplianceRuleEngine()
    issues = engine.check_listing(_listing())
    assert issues == []


def test_medical_claim_detected() -> None:
    engine = ComplianceRuleEngine()
    listing = _listing(title="PawPilot Harness Cures Arthritis, Treats Disease, Eliminates Pain")
    rule_ids = {i["rule_id"] for i in engine.check_listing(listing)}
    assert {"R101", "R102"}.issubset(rule_ids)


def test_treat_noun_not_flagged() -> None:
    """'dog treats' (noun) must not trigger the medical-claim rule for verb 'treats'."""
    engine = ComplianceRuleEngine()
    listing = _listing(title="PawPilot Treat Dispensing Ball for Dog Treats, Medium")
    issues = engine.check_listing(listing)
    assert all(i["category"] != "medical_claim" for i in issues)


def test_antimicrobial_and_fda_claims() -> None:
    engine = ComplianceRuleEngine()
    listing = _listing(
        bullets=[
            "Antibacterial surface kills germs",
            "Made in an FDA approved facility",
            "Easy to clean",
            "Machine washable",
            "Backed by a 12-month warranty",
        ]
    )
    rule_ids = {i["rule_id"] for i in engine.check_listing(listing)}
    assert {"R103", "R104"}.issubset(rule_ids)


def test_prohibited_marketing_phrases() -> None:
    engine = ComplianceRuleEngine()
    listing = _listing(
        title="PawPilot Best Dog Toy, #1 Top Rated, Cheapest on Amazon, Free Shipping Included"
    )
    rule_ids = {i["rule_id"] for i in engine.check_listing(listing)}
    assert {"R105", "R106"}.issubset(rule_ids)


def test_environmental_and_competitor_warnings() -> None:
    engine = ComplianceRuleEngine()
    listing = _listing(
        description="Eco-friendly and sustainable. Better than Kong for heavy chewers."
    )
    issues = engine.check_listing(listing)
    rule_ids = {i["rule_id"] for i in issues}
    assert {"R107", "R108"}.issubset(rule_ids)
    assert all(i["severity"] == "warning" for i in issues if i["rule_id"] in {"R107", "R108"})


def test_title_length_and_all_caps() -> None:
    engine = ComplianceRuleEngine()
    long_title = "PawPilot " + "Rope " * 50
    listing = _listing(title=long_title)
    rule_ids = {i["rule_id"] for i in engine.check_listing(listing)}
    assert "R201" in rule_ids

    caps = _listing(title="PAWPILOT COTTON ROPE DOG TOY FOR AGGRESSIVE CHEWERS")
    rule_ids = {i["rule_id"] for i in engine.check_listing(caps)}
    assert "R202" in rule_ids


def test_bullet_count_and_length() -> None:
    engine = ComplianceRuleEngine()
    listing = _listing(bullets=["Too short", "Only two bullets"])
    rule_ids = {i["rule_id"] for i in engine.check_listing(listing)}
    assert "R301" in rule_ids

    listing = _listing(bullets=["x" * 600, "b", "c", "d", "e"])
    rule_ids = {i["rule_id"] for i in engine.check_listing(listing)}
    assert "R302" in rule_ids


def test_backend_keywords_byte_limit() -> None:
    engine = ComplianceRuleEngine()
    listing = _listing(backend_keywords="word " * 60)
    rule_ids = {i["rule_id"] for i in engine.check_listing(listing)}
    assert "R401" in rule_ids


def test_check_draft_accepts_json_blob_and_text() -> None:
    import json

    engine = ComplianceRuleEngine()
    blob = json.dumps(_listing(title="Best dog toy with Free Shipping"))
    rule_ids = {i["rule_id"] for i in engine.check_draft(blob)}
    assert "R106" in rule_ids

    text = "Plain text draft mentioning 100% satisfaction guaranteed."
    rule_ids = {i["rule_id"] for i in engine.check_draft(text)}
    assert "R105" in rule_ids


def test_all_issues_carry_stable_fields() -> None:
    engine = ComplianceRuleEngine()
    listing = _listing(title="Best Cure-All Dog Toy")
    for issue in engine.check_listing(listing):
        assert issue["source"] == "rule"
        assert set(issue) == {
            "rule_id", "category", "severity", "field", "match", "message", "fix_hint", "source",
        }
        assert issue["severity"] in ("critical", "warning")
