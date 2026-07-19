"""
test_oauth_signature_harvest.py — the partner-tenant feedback loop.

WHY THIS FILE EXISTS. The City of Euless is piloting OAuth discovery as a COLLABORATOR,
not a customer. That makes the most valuable output of their run not the apps we
recognise, but the ones we DON'T: each is a candidate catalog signature, and a signature
added flags that vendor for every city afterwards. Before this, an unrecognised app only
incremented `skipped`, so a partner's run cost a round-trip and taught us nothing.

These tests run the REAL engine against a fixture built from the real export script's
output shape. Building that fixture immediately exposed a live defect — see
test_qualified_display_name_still_matches_via_publisher.

The fixture is deliberately realistic rather than convenient: display names carry the
product qualifiers Entra actually emits ("Grammarly for Windows", "Fireflies.ai
Notetaker"), not the tidy names our catalog aliases were written from.
"""
import json
from pathlib import Path

import pytest

from engine.collectors import oauth
from engine.collectors.identity import build_tool_index
from engine import rule_loader

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def index_and_rules():
    schema = rule_loader.load_schema()
    return build_tool_index(schema), schema.get("OAuth_Scope_Sensitivity", {})


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["grants"]


def _run(grants, index_and_rules, **kw):
    index, rules = index_and_rules
    return oauth.normalize(grants, index, "Lewisville", scope_rules=rules, **kw)


# ── The defect the fixture found ─────────────────────────────────────────────

def test_qualified_display_name_still_matches_via_publisher(index_and_rules):
    """REGRESSION. "Grammarly for Windows" must resolve to the grammarly catalog entry.

    It did not, originally. The shared matcher scores token-set (Jaccard) similarity, so
    {grammarly, for, windows} vs the alias {grammarly} = 1/3 = 0.333, below the 0.5
    threshold — the app fell through as unrecognised. Entra display names almost always
    carry such qualifiers, so this was not an edge case; it was the common case.

    Fixed by ALSO matching the publisher ("Grammarly, Inc." -> "Grammarly"), not by
    loosening the shared matcher — see clean_publisher.__doc__ for the rejected
    alternative and why it was unsafe.
    """
    res = _run(_load("entra_export_sample.json"), index_and_rules)
    matched = {a["display_name"]: a["tool_id"] for a in res["assets"]
               if a["asset_types"] == ["procured_ai"]}
    assert matched.get("Grammarly for Windows") == "grammarly"
    assert matched.get("Fireflies.ai Notetaker") == "fireflies_ai"


def test_publisher_cleaning_does_not_cross_match_vendors(index_and_rules):
    """The publisher signal must not become a source of false positives.

    Adobe publishes a document-signing product with no AI catalog entry. If cleaning
    publishers ever caused it to match an AI vendor, every city running Acrobat would be
    told it runs AI — a false compliance finding, which is worse than a missed one.
    """
    res = _run(_load("entra_export_sample.json"), index_and_rules)
    confirmed = [a["display_name"] for a in res["assets"]
                 if a["asset_types"] == ["procured_ai"]]
    assert "Adobe Acrobat Sign" not in confirmed


@pytest.mark.parametrize("raw,expected", [
    ("Grammarly, Inc.", "Grammarly"),
    ("OpenAI, L.L.C.", "OpenAI"),
    ("Anthropic PBC", "Anthropic"),
    ("Otter.ai Inc.", "Otter.ai"),
    ("Adobe Inc.", "Adobe"),
    ("", ""),
    (None, ""),
    # Only TRAILING suffixes are stripped; a suffix-like word inside the name stays.
    ("Cisco Systems", "Cisco Systems"),
])
def test_clean_publisher(raw, expected):
    assert oauth.clean_publisher(raw) == expected


# ── The signature harvest ────────────────────────────────────────────────────

def test_unmatched_apps_are_returned_with_signature_material(index_and_rules):
    """An unrecognised app must come back with enough to AUTHOR a catalog entry.

    A bare count ("skipped: 3") forces another round-trip with a partner who is doing us
    a favour. Names, publishers and IDs let us write the signature offline.
    """
    res = _run(_load("entra_export_sample.json"), index_and_rules)
    unmatched = res["unmatched"]
    assert unmatched, "unmatched must be populated for the OAuth channel"
    names = {u["app_name"] for u in unmatched}
    assert "Adobe Acrobat Sign" in names
    for u in unmatched:
        assert "app_id" in u and "catalog_promotable" in u
    assert res["unmatched_truncated"] is False


def test_unmatched_never_leaks_consenting_users(index_and_rules):
    """Even with include_users granted, the harvest carries no identities.

    An app we cannot identify is precisely the case where naming the employees who used
    it would be least defensible.
    """
    grants = _load("entra_export_sample.json")
    for g in grants:
        g["users"] = ["alice@city.gov", "bob@city.gov"]
    res = _run(grants, index_and_rules, include_users=True)
    blob = json.dumps(res["unmatched"])
    assert "alice@city.gov" not in blob
    assert "consenting_users" not in blob


def test_other_channels_are_unaffected_by_the_harvest():
    """collect_unmatched is opt-in: procurement and agenda payloads must not change."""
    from engine.collectors import procurement
    out = procurement.normalize([{"vendor": "Some Unknown Vendor", "city": "Lewisville"}],
                                {"procurement_candidates": [], "ai_keywords": []})
    assert "unmatched" not in out
    assert out["skipped"] == 1


# ── Signals that were previously computed and then dropped ───────────────────

def test_tenant_wide_admin_consent_survives_to_evidence(index_and_rules):
    """The highest-severity finding an export can carry must reach the operator.

    'AllPrincipals' consent means an administrator approved the app for the WHOLE
    organisation, so no individual employee ever agreed. The export script computed this
    and every layer below it silently discarded it.
    """
    res = _run(_load("entra_export_sample.json"), index_and_rules)
    ff = next(a for a in res["assets"] if a["display_name"] == "Fireflies.ai Notetaker")
    assert ff["evidence"].get("tenant_wide_admin_consent") == "yes"
    chatgpt = next(a for a in res["assets"] if a["display_name"] == "ChatGPT")
    assert "tenant_wide_admin_consent" not in chatgpt["evidence"]


@pytest.mark.parametrize("audience,promotable", [
    ("AzureADMultipleOrgs", True),
    ("AzureADandPersonalMicrosoftAccount", True),
    ("azureadmultipleorgs", True),          # case-insensitive
    ("AzureADMyOrg", False),                # tenant-local: ID means nothing elsewhere
    ("", False),                            # unknown -> fail closed
    (None, False),
])
def test_catalog_promotability_fails_closed(audience, promotable):
    """Only a MULTI-TENANT app ID is portable between cities.

    A single-tenant (AzureADMyOrg) appId is minted inside one tenant and is meaningless
    anywhere else — promoting one into the shared catalog would mis-attribute an
    unrelated app for every city that followed. Anything unrecognised returns False.
    """
    assert oauth.is_catalog_promotable(audience) is promotable


def test_internal_line_of_business_app_is_not_promotable(index_and_rules):
    """The city's own internal app must be flagged un-promotable in the harvest."""
    res = _run(_load("entra_export_sample.json"), index_and_rules)
    internal = next(u for u in res["unmatched"]
                    if u["app_name"] == "Lewisville Permit Portal Connector")
    assert internal["catalog_promotable"] == "no"


# ── Export-file shape ────────────────────────────────────────────────────────

def test_single_app_export_parses(index_and_rules):
    """A one-application tenant must behave like any other.

    Windows PowerShell 5.1's ConvertTo-Json collapses a one-element array into a bare
    object, which would turn "grants": [ {...} ] into "grants": { ... } and make the
    upload look empty. The export script now normalises that case; this asserts the
    engine handles the resulting single-element file.
    """
    res = _run(_load("entra_export_single_app.json"), index_and_rules)
    assert res["source_meta"]["rows"] == 1
    assert res["source_meta"]["matched"] == 1


def test_scope_sensitivity_is_reported_not_scored(index_and_rules):
    """We report what a grant can REACH. We never emit a risk score."""
    res = _run(_load("entra_export_sample.json"), index_and_rules)
    claude = next(a for a in res["assets"] if a["display_name"] == "Claude for Work")
    assert claude["evidence"]["scope_sensitivity"] in {"low", "medium", "high", "unknown"}
    for a in res["assets"]:
        assert "risk_score" not in a and "risk_score" not in a["evidence"]
