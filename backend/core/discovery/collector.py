"""
collector.py — the DiscoveryCollector contract shared by every discovery channel.

A discovery channel is ONLY a new way to produce ai_assets rows. Each channel
splits into a PURE normalizer (engine/collectors/*, storage-agnostic, no I/O) and
an ORCHESTRATOR (core/discovery/*_source.py) that does the I/O and merges results
via core/discovery/merge.merge_discovered_assets. This mirrors the proven
sentinel_feed.py shape (build_usage_assets = normalizer, sync_to_inventory =
orchestrator), generalized so all channels are consistent and testable.

See docs/DISCOVERY_EXPANSION_DESIGN.md.
"""
from __future__ import annotations

from typing import Any, Dict, List, Protocol, TypedDict, runtime_checkable


class DiscoveredAsset(TypedDict, total=False):
    """One normalized discovery finding. MACHINE fields only — a collector never
    writes human fields (owner, attestation, purpose, cid_*); the repository merge
    contract preserves them. Values are stringified on write (Sheets/Firestore)."""
    tool_id:      str            # canonical id from the identity resolver
    city:         str
    vendor_id:    str
    display_name: str
    asset_types:  List[str]
    provenance:   str            # discovered_procurement | discovered_oauth | ...
    presence:     str            # active | observed | (unset for procured-not-observed)
    evidence:     Dict[str, Any] # channel-specific proof (contract id, grant id, host)
    confidence:   float
    observed_utc: str


class DiscoveryResult(TypedDict, total=False):
    assets:      List[DiscoveredAsset]
    skipped:     int                    # findings we could not attribute (fail-secure)
    source_meta: Dict[str, Any]         # counts / tenant / file — for the audit log


@runtime_checkable
class DiscoveryCollector(Protocol):
    """Contract every channel satisfies (structural subtyping — no inheritance).

    Storage-agnostic: collect() returns dicts; the orchestrator merges them.
    Injectable for tests — pass a fake source client + MockGovernanceRepository.
    """
    provenance: str

    def collect(self, context: Dict[str, Any]) -> DiscoveryResult:
        # TODO: enforce system-level invocation only (auth placeholder)
        # TODO: scope results to the requesting principal's cities (auth placeholder)
        ...
