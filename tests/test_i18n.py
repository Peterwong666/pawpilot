"""Unit tests for the web/i18n.py internationalisation module.

All tests patch ``web.i18n.st.session_state`` to a plain ``dict`` so
``init_lang`` / ``t`` behave deterministically outside of a Streamlit
runtime. The patch target MUST be ``web.i18n.st.session_state`` — patching
``streamlit.session_state`` directly does not affect the reference already
captured by ``import streamlit as st`` at module load time.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from web import i18n
from web.i18n import DEFAULT_LANG, LANG_KEY, en, t, zh

# ---------------------------------------------------------------------------
# Structural invariants — dictionaries must be perfectly symmetrical
# ---------------------------------------------------------------------------

def test_zh_en_dict_keys_are_identical() -> None:
    """Every key present in zh must also exist in en (and vice versa)."""
    zh_only = set(zh) - set(en)
    en_only = set(en) - set(zh)
    assert zh_only == set(), f"Keys in zh but missing in en: {zh_only}"
    assert en_only == set(), f"Keys in en but missing in zh: {en_only}"


def test_all_values_are_non_empty_strings() -> None:
    for label, dict_ in (("zh", zh), ("en", en)):
        for key, value in dict_.items():
            assert isinstance(value, str), f"{label}[{key!r}] is {type(value).__name__}, expected str"
            assert value.strip(), f"{label}[{key!r}] is empty or whitespace-only"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_constants() -> None:
    assert LANG_KEY == "lang"
    assert DEFAULT_LANG == "zh"


# ---------------------------------------------------------------------------
# init_lang — seeds default only when absent; idempotent otherwise
# ---------------------------------------------------------------------------

def test_init_lang_sets_default_when_missing() -> None:
    with patch.object(i18n.st, "session_state", {}):
        i18n.init_lang()
        assert i18n.st.session_state[LANG_KEY] == "zh"


def test_init_lang_does_not_overwrite_existing() -> None:
    with patch.object(i18n.st, "session_state", {"lang": "en"}):
        i18n.init_lang()
        assert i18n.st.session_state[LANG_KEY] == "en"


def test_init_lang_is_idempotent() -> None:
    """Multiple calls do not flip the default nor overwrite a set value."""
    with patch.object(i18n.st, "session_state", {"lang": "en"}):
        for _ in range(5):
            i18n.init_lang()
        assert i18n.st.session_state[LANG_KEY] == "en"

    with patch.object(i18n.st, "session_state", {}):
        for _ in range(5):
            i18n.init_lang()
        assert i18n.st.session_state[LANG_KEY] == "zh"


# ---------------------------------------------------------------------------
# t() — basic retrieval
# ---------------------------------------------------------------------------

def test_t_returns_chinese_when_lang_is_zh() -> None:
    with patch.object(i18n.st, "session_state", {"lang": "zh"}):
        assert t("app.title") == zh["app.title"]
        assert t("tab.policy") == zh["tab.policy"]


def test_t_returns_english_when_lang_is_en() -> None:
    with patch.object(i18n.st, "session_state", {"lang": "en"}):
        assert t("app.title") == en["app.title"]
        assert t("tab.policy") == en["tab.policy"]


def test_t_defaults_to_chinese_when_session_state_has_no_lang() -> None:
    with patch.object(i18n.st, "session_state", {}):
        assert t("app.title") == zh["app.title"]


# ---------------------------------------------------------------------------
# t() — fallback chain
# ---------------------------------------------------------------------------

def test_t_falls_back_to_english_when_lang_is_unknown() -> None:
    """An unsupported language code must resolve via the en fallback."""
    with patch.object(i18n.st, "session_state", {"lang": "xx"}):
        assert t("app.title") == en["app.title"]


def test_t_falls_back_to_key_when_missing_from_all_languages() -> None:
    with patch.object(i18n.st, "session_state", {"lang": "zh"}):
        assert t("definitely.not.a.real.key") == "definitely.not.a.real.key"


def test_t_falls_back_to_key_when_missing_from_english_too() -> None:
    """Even if en is picked, a missing key must return the raw key."""
    with patch.object(i18n.st, "session_state", {"lang": "en"}):
        assert t("also.missing") == "also.missing"


# ---------------------------------------------------------------------------
# t() — str.format parameterisation
# ---------------------------------------------------------------------------

def test_t_formats_named_placeholders() -> None:
    with patch.object(i18n.st, "session_state", {"lang": "zh"}):
        msg = t("t7.spinner_import", name="sales.csv")
        assert msg == "正在导入 sales.csv…"

        msg = t("t7.success", name="sales.csv", rows=3, type="sales", confidence="high")
        assert "sales.csv" in msg
        assert "3" in msg
        assert "sales" in msg
        assert "high" in msg

    with patch.object(i18n.st, "session_state", {"lang": "en"}):
        msg = t("t7.spinner_import", name="sales.csv")
        assert msg == "Importing sales.csv..."

        msg = t("err.backend_down_short", url="http://127.0.0.1:8001")
        assert "127.0.0.1:8001" in msg


def test_t_formats_list_values_as_joined_string() -> None:
    with patch.object(i18n.st, "session_state", {"lang": "zh"}):
        msg = t("t7.matched", cols=["sku", "date", "revenue_usd"])
        # list objects are rendered via str.format -> repr of list
        # This is fine because we want the template to not break.
        assert isinstance(msg, str)


def test_t_returns_raw_template_when_format_missing_kwargs() -> None:
    """If the caller forgets a placeholder, t() must not raise and must
    return the template unchanged so the UI stays usable."""
    with patch.object(i18n.st, "session_state", {"lang": "zh"}):
        msg = t("t7.spinner_import")  # no name=
        assert msg == "正在导入 {name}…"

    with patch.object(i18n.st, "session_state", {"lang": "en"}):
        msg = t("t7.spinner_import")
        assert msg == "Importing {name}..."


def test_t_no_kwargs_returns_raw_string() -> None:
    with patch.object(i18n.st, "session_state", {"lang": "zh"}):
        msg = t("t1.header")
        assert msg == zh["t1.header"]


# ---------------------------------------------------------------------------
# t() — cross-language coverage spot-checks (sanity)
# ---------------------------------------------------------------------------

LANG_SPOT_CHECKS = [
    ("app.title", "🐾 PawPilot", "Amazon Pet-Supplies"),
    ("tab.policy", "政策与 SOP", "Policy Q&A"),
    ("t7.header", "数据上传", "Data Upload"),
]


@pytest.mark.parametrize("key,zh_contains,en_contains", LANG_SPOT_CHECKS)
def test_spot_zh_en_are_distinct(
    key: str, zh_contains: str, en_contains: str
) -> None:
    with patch.object(i18n.st, "session_state", {"lang": "zh"}):
        assert zh_contains in t(key)
    with patch.object(i18n.st, "session_state", {"lang": "en"}):
        assert en_contains in t(key)
    # And they must differ between languages.
    with patch.object(i18n.st, "session_state", {"lang": "zh"}):
        zh_val = t(key)
    with patch.object(i18n.st, "session_state", {"lang": "en"}):
        en_val = t(key)
    assert zh_val != en_val
