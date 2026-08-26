"""
test_obligation_applicability.py — WHICH statute applies to WHICH asset.

The regression this locks down: every inventory row used to carry the full External
Transparency ruleset, so a staff-side tool found in an OAuth export displayed Tex. Bus.
& Com. Code 552.051 disclosure duties. 552.051(b) binds an agency that "makes available
an artificial intelligence system intended to interact with consumers" — Grammarly on a
clerk's laptop is not that. Over-flagging a city with statutes it does not owe is the
fastest way for a governance product to lose the room.

Pure: engine/applicability.py has no I/O, so this runs with no FastAPI and no repo.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import applicability


def _asset(provenance, *sources):
    a = {"provenance": provenance}
    if sources:
        import json
        a["discovery_sources_json"] = json.dumps(
            [{"provenance": s, "observed_utc": "2026-08-24T00:00:00Z"} for s in sources])
    return a


# ── internal-use channels do NOT owe a consumer-disclosure duty ──────────────

def test_oauth_discovered_tool_is_internal_use():
    r = applicability.assess_asset(_asset("discovered_oauth"))
    assert r["applies"] is False
    assert r["basis"] == "internal_use"
    assert "552.051" in r["note"]


def test_sentinel_observed_tool_is_internal_use():
    assert applicability.assess_asset(_asset("discovered_sentinel"))["applies"] is False


def test_two_internal_channels_are_still_internal():
    r = applicability.assess_asset(
        _asset("discovered_oauth", "discovered_oauth", "discovered_sentinel"))
    assert r["applies"] is False


# ── a public-facing observation always wins ──────────────────────────────────

def test_scan_discovered_tool_owes_the_duty():
    r = applicability.assess_asset(_asset("discovered_scan"))
    assert r["applies"] is True and r["basis"] == "public_facing"


def test_internal_tool_later_seen_live_regains_the_duty():
    """THE false negative that would matter: provenance keeps the FIRST channel, so an
    OAuth-first asset the crawler later found live must not stay suppressed."""
    a = _asset("discovered_oauth", "discovered_oauth", "discovered_scan")
    r = applicability.assess_asset(a)
    assert r["applies"] is True and r["basis"] == "public_facing"


# ── everything else stays as it was: shown, with a verify-deployment caveat ──

def test_declared_asset_still_shows_obligations():
    r = applicability.assess_asset(_asset("declared"))
    assert r["applies"] is True and r["basis"] == "unverified_deployment"


def test_procurement_asset_still_shows_obligations():
    r = applicability.assess_asset(_asset("discovered_procurement"))
    assert r["applies"] is True and r["basis"] == "unverified_deployment"


def test_mixed_internal_and_procurement_is_not_suppressed():
    """Fail-secure: a procured system might be deployed publicly, so do not suppress."""
    r = applicability.assess_asset(
        _asset("discovered_oauth", "discovered_oauth", "discovered_procurement"))
    assert r["applies"] is True


def test_unknown_provenance_is_not_suppressed():
    assert applicability.assess_asset({"provenance": ""})["applies"] is True


def test_malformed_sources_json_does_not_crash():
    a = {"provenance": "discovered_oauth", "discovery_sources_json": "{not json"}
    assert applicability.assess_asset(a)["applies"] is False


def test_every_basis_carries_a_human_readable_note():
    for prov in ("discovered_oauth", "discovered_scan", "declared"):
        note = applicability.assess_asset(_asset(prov))["note"]
        assert note and len(note) > 40
