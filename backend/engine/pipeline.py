"""
pipeline.py — Core audit pipeline: crawl → fingerprint → validate → scorecard.

Storage-agnostic: takes targets (list of dicts) and a GovernanceRepository,
returns a results dict. Called identically from:
  - api/routes/audit.py  (HTTP-triggered scan)
  - core/scheduler.py    (scheduled automatic scan)

This is the canonical entry point for a full multi-city audit run.
The engine never imports from core/repositories or api/ — it is a pure
data-in, data-out module.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.governance_service import GovernanceRepository


def run_full_audit(
    targets: List[Dict[str, Any]],
    repo: GovernanceRepository,
    demo_fixtures: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute the full 5-stage audit pipeline for a list of targets.

    Stages:
      1. Crawl — retrieve page content for each target URL
      2. Fingerprint — detect AI vendor assets from page signals
      3. Validate — apply External_Transparency_Module disclosure rules
      4. Reconcile — merge new findings with existing violation state
      5. Scorecard — compute per-city compliance row and persist

    Args:
        targets:       List of target dicts (city, url, domain, jurisdiction).
        repo:          GovernanceRepository implementation (Sheets, Firestore, Mock).
        demo_fixtures: Optional dict of URL -> fixture data for demo/test runs.
                       If a target URL is in demo_fixtures, the crawler is bypassed.

    Returns:
        {
            "city_count":        int,
            "observed_failures": int,  # raw rule failures before dedup
            "open_violations":   int,  # violations still within cure period
        }

    Raises:
        Exception on unrecoverable pipeline failure (caller should catch and log).

    TODO: enforce system-level write only — no user can trigger this directly (auth placeholder).
    """
    import sys, os
    # Ensure engine modules resolve regardless of working directory
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from engine import rule_loader
    from engine.crawler import PageCapture, crawl_site
    from engine.fingerprint_engine import fingerprint
    from engine.disclosure_validator import validate
    from engine.cure_period import reconcile, open_violations
    from engine.scorecard import build_city_row, build_scorecard

    schema        = rule_loader.load_schema()
    vendors       = rule_loader.get_vendors(schema)
    threshold     = rule_loader.get_match_threshold(schema)
    rules         = rule_loader.get_external_rules(schema)
    scorecard_cfg = schema["scorecard_schema"]

    # Load existing violation state for reconciliation.
    # Scope to only the cities in this scan — violations for other cities are
    # preserved as-is in Sheets and never rewritten here (prevents city-scoped
    # re-audits from clearing violations for uninvolved cities, and avoids the
    # O(N*2) Sheets API call storm from writing every preserved violation).
    target_cities = {t["city"] for t in targets}
    all_existing_violations = repo.get_violations()
    scoped_violations = [v for v in all_existing_violations if v.get("city") in target_cities]

    state: Dict[str, Any] = {"violations": {}}
    for v in scoped_violations:
        vid = v.get("violation_id", "")
        if vid:
            raw_ev = v.get("evidence_json") or "{}"
            try:
                evidence = json.loads(raw_ev)
            except (json.JSONDecodeError, TypeError, ValueError):
                evidence = {}
            state["violations"][vid] = {
                **v,
                "evidence":           evidence,
                "cure_period_status": v.get("cure_period_status", "True") == "True",
                "needs_human_review": v.get("needs_human_review", "True") == "True",
            }

    observed_failures: List[Dict[str, Any]] = []
    per_city_assets:   Dict[str, List[Dict[str, Any]]] = {}
    crawled_cities:    set = set()   # cities where crawler returned >= 1 page of content

    for target in targets:
        city   = target["city"]
        domain = target.get("domain") or target.get("url", "")
        url    = target.get("url", domain)
        per_city_assets.setdefault(city, [])

        # Per-city error isolation: a crawl failure for one city must not
        # abort the entire pipeline run.  Log and continue.
        try:
            # Demo mode: bypass crawler with fixture data
            if demo_fixtures and url in demo_fixtures:
                captures = [PageCapture.from_fixture(url, demo_fixtures[url]["fixture"])]
            else:
                # Proxy policy: config.SCAN_PROXY_ONLY_FLAGGED routes only
                # cloudflare_protected targets through the (paid) residential
                # proxy to conserve bandwidth; otherwise all targets use it when
                # SCAN_PROXY_URL is set. crawl_site no-ops the proxy if unset.
                from engine import config as _cfg
                flagged = str(target.get("cloudflare_protected", "")).strip().lower() in ("true", "1", "yes")
                use_proxy = (not _cfg.SCAN_PROXY_ONLY_FLAGGED) or flagged
                captures = crawl_site(url, use_proxy=use_proxy)
        except Exception as exc:
            import traceback as _tb
            print(f"[pipeline] WARN: crawl failed for {city} ({url}): {type(exc).__name__}: {exc}\n{_tb.format_exc()}")
            captures = []   # treat as no signal — city still gets a scorecard row

        # Only consider a city "crawled" if we got actual page content back.
        # An empty list means the crawler was blocked or failed — we must NOT
        # auto-cure that city's existing violations (could be a WAF false-negative).
        if captures:
            crawled_cities.add(city)

        # Debug: log what the crawler captured for each page
        for cap in captures:
            print(f"[pipeline] {city} | url={cap.url} engine={cap.render_engine} "
                  f"html_len={len(cap.html)} script_hosts={cap.script_hosts[:5]} "
                  f"network_urls_count={len(cap.network_urls)} "
                  f"citibot_in_html={'citibot' in cap.html.lower()} "
                  f"citibot_in_text={'citibot' in (cap.text or '').lower()}")

        # Collect all raw detections across all pages for this city
        raw_detections: List[tuple] = []
        for cap in captures:
            scores = {}
            for vendor in vendors:
                from engine.fingerprint_engine import _indicator_haystack, _matches
                s = sum(float(ind.get("weight",0)) for ind in vendor.get("indicators",[])
                        if _matches(ind["pattern"], ind["type"], _indicator_haystack(cap, ind["type"])))
                if s > 0:
                    scores[vendor["vendor_id"]] = round(s, 3)
            if scores:
                print(f"[pipeline] {city} | fingerprint scores: {scores} (threshold={threshold})")
            for asset in fingerprint(cap, vendors, threshold):
                raw_detections.append((asset, cap))

        # Deduplicate: one entry per vendor per city, keeping highest-confidence hit.
        # A sitewide widget fires on every page — without this, 25 pages * N rules
        # would generate N*25 violations for a single chatbot widget.
        best: Dict[str, tuple] = {}
        for asset, cap in raw_detections:
            existing = best.get(asset.vendor_id)
            if existing is None or asset.match_confidence > existing[0].match_confidence:
                best[asset.vendor_id] = (asset, cap)

        for asset, cap in best.values():
            per_city_assets[city].append({
                "vendor_id":           asset.vendor_id,
                "display_name":        asset.display_name,
                "asset_type":          asset.asset_types,
                "match_confidence":    asset.match_confidence,
                "page_url":            asset.page_url,
                "verification_status": asset.verification_status,
            })
            for v in validate(cap, asset, rules):
                observed_failures.append({
                    "city":      city,
                    "domain":    domain,
                    "asset_id":  asset.asset_id,
                    "vendor_id": asset.vendor_id,
                    "rule_id":   v["rule_id"],
                    "citation":  v["citation"],
                    "severity":  v["severity"],
                    "evidence": {
                        "page_url":           asset.page_url,
                        "matched_indicators": asset.matched_indicators,
                        "remediation":        v["remediation"],
                    },
                })

    state    = reconcile(state, observed_failures, crawled_cities=crawled_cities)
    all_open = open_violations(state)

    rows = []
    for target in targets:
        city      = target["city"]
        city_open = [v for v in all_open if v["city"] == city]
        rows.append(build_city_row(
            city=city,
            jurisdiction=target.get("jurisdiction", ""),
            domain=target.get("domain") or target.get("url", ""),
            assets=per_city_assets.get(city, []),
            open_violations=city_open,
            scorecard_cfg=scorecard_cfg,
        ))
    scorecard = build_scorecard(rows, scorecard_cfg)

    # Persist via repository — engine has no knowledge of storage.
    # write_scorecard_rows uses _upsert_by_key — only writes the scanned cities'
    # rows (insert or update); other cities' rows are untouched in Sheets.
    # write_violations writes only the scoped (target-city) violations — preserved
    # (other-city) violations are already correct in Sheets and must not be
    # rewritten, as that would trigger an O(N*2) Sheets API call storm.
    repo.write_scorecard_rows(rows)
    repo.write_violations(list(state["violations"].values()))
    repo.append_audit_log(
        event="scan_complete",
        city_count=scorecard["city_count"],
        failures=len(observed_failures),
        details={"open_violations": len(all_open)},
    )

    return {
        "city_count":        scorecard["city_count"],
        "observed_failures": len(observed_failures),
        "open_violations":   len(all_open),
    }
