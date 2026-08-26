"""
applicability.py — WHICH statutory module applies to a given AI asset (PURE; no I/O).

WHY THIS EXISTS. Tex. Bus. & Com. Code 552.051(b) obliges "a governmental agency that
makes available an artificial intelligence system intended to interact with consumers"
to disclose that fact to the consumer. It is a duty about PUBLIC-FACING systems. Before
this module existed, the inventory attached the whole External Transparency ruleset to
every asset, so a staff-side tool discovered in an OAuth export — Grammarly, Canva,
Copilot — displayed 552.051 disclosure duties it cannot owe. A CIO reads that as an
accusation, and a governance product that cries wolf about statutes is worth nothing.

Pure and storage-agnostic on purpose: the same decision has to hold in the inventory API,
in a council report, and in a framework crosswalk, so it cannot live in a route.

FAIL-SECURE IN BOTH DIRECTIONS. Over-flagging destroys trust; under-flagging hides a real
duty. So the decision reads EVERY discovery source, not the single `provenance` field
(which records only the FIRST channel that found the asset): a tool first seen in an
OAuth export and LATER observed live on the public site is public-facing, and suppressing
its obligations because provenance still reads discovered_oauth would be the one false
negative that actually matters.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Set

# Channels that observe INTERNAL staff usage. Nothing they find is, on that evidence
# alone, made available to a consumer.
INTERNAL_USE_PROVENANCE: Set[str] = {"discovered_oauth", "discovered_sentinel"}

# The one channel that PROVES a system is public-facing: it was observed by the crawler
# on the agency's own public website.
PUBLIC_FACING_PROVENANCE = "discovered_scan"

BASIS_PUBLIC = "public_facing"
BASIS_INTERNAL = "internal_use"
BASIS_UNVERIFIED = "unverified_deployment"

_NOTES = {
    BASIS_PUBLIC: ("Observed live on the public website, so it is made available to "
                   "consumers and the disclosure duty applies."),
    BASIS_INTERNAL: ("Internal staff use. Tex. Bus. & Com. Code 552.051 applies to an AI "
                     "system a governmental agency makes available to interact with "
                     "consumers; a tool consented inside your tenant is not that. Declare "
                     "it as public-facing if it is put in front of residents."),
    BASIS_UNVERIFIED: ("Not verified live on the public website. Confirm whether this "
                       "system is made available to consumers before treating the "
                       "disclosure duty as due."),
}


def discovery_provenances(asset: Dict[str, Any]) -> Set[str]:
    """Every channel that has ever found this asset (`provenance` is the FIRST only)."""
    found = {str(asset.get("provenance") or "")}
    raw = asset.get("discovery_sources_json")
    sources: List[Any] = []
    if isinstance(raw, str) and raw:
        try:
            sources = json.loads(raw) or []
        except (ValueError, TypeError):
            sources = []
    elif isinstance(raw, list):
        sources = raw
    for src in sources:
        if isinstance(src, dict) and src.get("provenance"):
            found.add(str(src["provenance"]))
    return {p for p in found if p}


def assess(provenances: Iterable[str]) -> Dict[str, Any]:
    """Decide whether the External Transparency (552.051) ruleset applies."""
    sources = {p for p in provenances if p}
    if PUBLIC_FACING_PROVENANCE in sources:
        basis = BASIS_PUBLIC
    elif sources and sources <= INTERNAL_USE_PROVENANCE:
        basis = BASIS_INTERNAL
    else:
        basis = BASIS_UNVERIFIED
    return {"applies": basis != BASIS_INTERNAL, "basis": basis, "note": _NOTES[basis]}


def assess_asset(asset: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience wrapper: applicability for a registry row as stored."""
    return assess(discovery_provenances(asset))
