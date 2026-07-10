"""
test_discovery_substrate.py — identity resolver + procurement normalizer + merge.

Verifies the discovery substrate end to end WITHOUT storage or network:
  1. canonical identity resolution across channels (+ unknown: fallback),
  2. procurement fuzzy-match with a confidence floor + fail-secure skips,
  3. the multi-source merge: one canonical row per (city, tool), sources unioned,
     human fields preserved (the merge contract).

Self-contained: loads the four pure modules by file path (no package import, no
stale siblings) and uses an inline fake repo mirroring upsert_ai_asset's merge.
Run standalone:  python3 tests/test_discovery_substrate.py
Or under pytest: pytest tests/test_discovery_substrate.py
"""
import importlib.util
import json
import os

_BE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_BE, relpath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


identity = _load("d_identity", "engine/collectors/identity.py")
procurement = _load("d_procurement", "engine/collectors/procurement.py")
merge = _load("d_merge", "core/discovery/merge.py")

SCHEMA = {
    "AI_Tool_Catalog": {"ai_keywords": ["ai", "artificial intelligence", "machine learning", "chatbot", "copilot", "predictive analytics"], "tools": [
        {"tool_id": "openai_chatgpt", "display_name": "ChatGPT (OpenAI)", "aliases": {
            "sentinel_site_ids": ["chatgpt", "openai"],
            "oauth_app_ids": ["app-openai-123"],
            "domains": ["chatgpt.com", "openai.com", "api.openai.com"],
            "procurement_names": ["openai", "chatgpt enterprise"]}},
        {"tool_id": "microsoft_copilot", "display_name": "Microsoft Copilot", "aliases": {
            "sentinel_site_ids": ["copilot"], "domains": ["copilot.microsoft.com"],
            "procurement_names": ["microsoft copilot", "m365 copilot"],
            "product_names": ["copilot"]}},
        {"tool_id": "otter_ai", "display_name": "Otter.ai", "aliases": {
            "domains": ["otter.ai"], "procurement_names": ["otter", "otter.ai"]}},
    ]},
    "AI_Vendor_Fingerprints": {"vendors": [
        {"vendor_id": "citibot", "display_name": "Citibot"},
    ]},
}
INDEX = identity.build_tool_index(SCHEMA)


class FakeRepo:
    """Mirrors MockGovernanceRepository.upsert_ai_asset merge semantics."""
    def __init__(self, seed=None):
        self.assets = list(seed or [])

    def get_ai_assets(self, city=None):
        return [dict(r) for r in self.assets if city is None or r.get("city") == city]

    def upsert_ai_asset(self, asset):
        key = asset.get("asset_key")
        cur = next((r for r in self.assets if r.get("asset_key") == key), None)
        if cur is not None:
            cur.update({k: v for k, v in asset.items() if v is not None})
        else:
            self.assets.append(dict(asset))


# ── 1. identity resolution ───────────────────────────────────────────────────
def test_identity_resolution():
    assert identity.resolve_tool_id("sentinel_site_ids", "chatgpt", INDEX) == "openai_chatgpt"
    assert identity.resolve_tool_id("sentinel_site_ids", "OpenAI", INDEX) == "openai_chatgpt"
    assert identity.resolve_tool_id("domains", "chatgpt.com", INDEX) == "openai_chatgpt"
    assert identity.resolve_tool_id("oauth_app_ids", "app-openai-123", INDEX) == "openai_chatgpt"
    assert identity.resolve_tool_id("procurement_names", "Microsoft Copilot", INDEX) == "microsoft_copilot"
    # fingerprint vendor_id is a valid canonical tool_id
    assert identity.resolve_tool_id("by_name", "citibot", INDEX) == "citibot" or \
        INDEX["by_name"]["citibot"] == "citibot"
    # unknown -> surfaced, never silently mapped
    assert identity.resolve_tool_id("procurement_names", "Acme Plumbing", INDEX) == "unknown:acme plumbing"
    assert identity.resolve_tool_id("sentinel_site_ids", "", INDEX) == "unknown:blank"


# ── 2. procurement normalizer ────────────────────────────────────────────────
def test_procurement_matching_and_skips():
    rows = [
        {"vendor": "OpenAI API", "city": "Lewisville", "contract_id": "C-1", "amount": "12000"},
        {"vendor": "Microsoft Copilot", "city": "Denton"},
        {"vendor": "Otter.ai", "city": "Lewisville"},
        {"vendor": "Acme Plumbing Co", "city": "Lewisville"},   # not AI -> skipped
        {"vendor": "OpenAI", "city": ""},                       # no city -> skipped
    ]
    res = procurement.normalize(rows, INDEX)
    got = {(a["city"], a["tool_id"]) for a in res["assets"]}
    assert ("Lewisville", "openai_chatgpt") in got
    assert ("Denton", "microsoft_copilot") in got
    assert ("Lewisville", "otter_ai") in got
    assert res["skipped"] == 2, res["skipped"]
    # exact alias match is full confidence; evidence carries the raw name + contract
    oa = next(a for a in res["assets"] if a["tool_id"] == "openai_chatgpt")
    assert oa["provenance"] == "discovered_procurement"
    assert oa["evidence"]["vendor_name_raw"] == "OpenAI API"
    assert oa["evidence"]["contract_id"] == "C-1"
    assert "presence" not in oa   # procured != observed live


# ── 3. merge: canonical row, source union, human fields preserved ────────────
def test_merge_creates_canonical_row():
    repo = FakeRepo()
    res = procurement.normalize(
        [{"vendor": "OpenAI", "city": "Lewisville", "contract_id": "C-9"}], INDEX)
    out = merge.merge_discovered_assets(repo, res)
    assert out["written"] == 1 and out["errors"] == []
    row = repo.assets[0]
    assert row["asset_key"] == "lewisville::openai_chatgpt"
    assert row["provenance"] == "discovered_procurement"
    assert row["lifecycle_status"] == "discovered"
    srcs = json.loads(row["discovery_sources_json"])
    assert [s["provenance"] for s in srcs] == ["discovered_procurement"]


def test_merge_unions_sources_and_preserves_human_fields():
    # A prior SCAN row for the same tool, already attested by a human.
    prior = {
        "asset_key": "lewisville::openai_chatgpt", "city": "Lewisville",
        "tool_id": "openai_chatgpt", "provenance": "discovered_scan",
        "discovery_sources_json": json.dumps([{"provenance": "discovered_scan",
                                               "observed_utc": "2026-01-01T00:00:00Z", "evidence": {}}]),
        "owner_email": "cio@lewisville.gov", "owner_name": "Chris Lee",
        "purpose": "resident 311 assistant", "lifecycle_status": "attested",
        "attested_by": "cio@lewisville.gov",
    }
    repo = FakeRepo(seed=[prior])
    res = procurement.normalize(
        [{"vendor": "OpenAI", "city": "Lewisville", "contract_id": "C-42"}], INDEX)
    merge.merge_discovered_assets(repo, res)

    row = repo.assets[0]
    # ONE row, not two.
    assert len(repo.assets) == 1
    # Human fields untouched (merge contract).
    assert row["owner_email"] == "cio@lewisville.gov"
    assert row["purpose"] == "resident 311 assistant"
    assert row["lifecycle_status"] == "attested"        # scan/procurement never move lifecycle
    assert row["attested_by"] == "cio@lewisville.gov"
    # Primary provenance stays the FIRST source (scan); procurement is added as a source.
    assert row["provenance"] == "discovered_scan"
    provs = [s["provenance"] for s in json.loads(row["discovery_sources_json"])]
    assert set(provs) == {"discovered_scan", "discovered_procurement"}, provs
    # The procurement contract evidence rode along.
    proc_src = next(s for s in json.loads(row["discovery_sources_json"])
                    if s["provenance"] == "discovered_procurement")
    assert proc_src["evidence"]["contract_id"] == "C-42"


# ── 4. product-name matching + AI-keyword candidate screen ───────────────────
def test_product_field_disambiguates_multiproduct_vendor():
    # Vendor "Microsoft" alone is ambiguous (Office vs Copilot); the PRODUCT resolves it.
    rows = [{"vendor": "Microsoft", "product": "Copilot", "city": "Lewisville"}]
    res = procurement.normalize(rows, INDEX)
    assert len(res["assets"]) == 1
    a = res["assets"][0]
    assert a["tool_id"] == "microsoft_copilot"
    assert a["asset_types"] == ["procured_ai"]
    assert a["evidence"]["product_raw"] == "Copilot"


def test_ai_keyword_catches_unknown_vendor_as_candidate():
    # AI sold under a NON-AI company name, no catalog match -> surfaced for review.
    rows = [{"vendor": "Tyler Technologies", "product": "AI permitting assistant",
             "city": "Lewisville", "contract_id": "C-100"}]
    res = procurement.normalize(rows, INDEX)
    assert res["skipped"] == 0            # NOT dropped
    assert res["source_meta"]["candidates"] == 1
    a = res["assets"][0]
    assert a["asset_types"] == ["procured_ai_candidate"]
    assert a["tool_id"].startswith("unknown:ai:")
    assert a["evidence"]["match_type"] == "ai_keyword"
    assert a["evidence"]["matched_keyword"] in ("ai", "artificial intelligence")


def test_non_ai_line_item_still_skipped():
    rows = [{"vendor": "Acme Plumbing", "product": "backflow valve repair", "city": "Lewisville"}]
    res = procurement.normalize(rows, INDEX)
    assert res["assets"] == [] and res["skipped"] == 1


def test_keyword_boundary_no_false_positive():
    # "maintenance" contains "ai" as a substring but not as a word -> no candidate.
    rows = [{"vendor": "Acme HVAC", "product": "quarterly maintenance contract", "city": "Lewisville"}]
    res = procurement.normalize(rows, INDEX)
    assert res["assets"] == [] and res["skipped"] == 1


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} discovery-substrate tests passed")
