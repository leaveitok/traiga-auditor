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


def _asset_key(city: str, vendor_id: str) -> str:
    """Stable inventory key for a scan-discovered asset: one per city+vendor."""
    safe = lambda s: str(s).strip().lower().replace(" ", "-").replace("/", "_")
    return f"{safe(city)}::{safe(vendor_id)}"


def _feed_inventory(repo: GovernanceRepository, city: str,
                    detected: list) -> None:
    """
    Reconcile one successfully-crawled city's detections into the ai_assets
    registry. Writes MACHINE fields only; the repository merge contract
    preserves human fields. Previously scan-discovered assets for this city
    that were NOT re-observed are marked presence=not_reobserved (never
    deleted, never auto-retired — a human decides retirement).
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    seen_keys = set()
    existing = {r.get("asset_key"): r for r in repo.get_ai_assets(city=city)}

    for a in detected:
        key = _asset_key(city, a.get("vendor_id", "unknown"))
        seen_keys.add(key)
        record = {
            "asset_key":          key,
            "city":               city,
            "vendor_id":          a.get("vendor_id", ""),
            "display_name":       a.get("display_name", ""),
            "asset_types_json":   json.dumps(a.get("asset_type", []) or []),
            "provenance":         "discovered_scan",
            "presence":           "active",
            "last_observed_utc":  now,
            "page_url":           a.get("page_url", ""),
            "match_confidence":   str(a.get("match_confidence", "")),
            "evidence_json":      json.dumps({
                "verification_status": a.get("verification_status", ""),
            }),
        }
        prior = existing.get(key)
        if not prior:
            record["first_observed_utc"] = now
            record["lifecycle_status"]   = "discovered"
        repo.upsert_ai_asset(record)

    # Mark this city's scan-discovered assets that did not reappear.
    for r in existing.values():
        if (r.get("provenance") == "discovered_scan"
                and r.get("asset_key") not in seen_keys
                and r.get("presence") != "not_reobserved"):
            repo.upsert_ai_asset({
                "asset_key": r.get("asset_key"),
                "presence":  "not_reobserved",
            })


def run_full_audit(
    targets: List[Dict[str, Any]],
    repo: GovernanceRepository,
    demo_fixtures: Optional[Dict[str, Any]] = None,
    progress_cb: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Execute the full 5-stage audit pipeline for a list of targets.

    Stages:
      1. Crawl — retrieve page content for each target URL
      2. Fingerprint — detect AI vendor assets from page signals
      3. Validate — apply External_Transparency_Module disclosure rules
      4. Reconcile — merge new findings with existing violation state
      5. Scorecard — compute per-city compliance row and persist

    INCREMENTAL PERSISTENCE: each city's scorecard row and violations are
    written as soon as that city finishes, so a polling dashboard repaints
    in real time during a long multi-city run. Per-city reconcile is
    semantically identical to the old end-of-run batch reconcile because
    both violation records and observations are city-keyed, and the
    crawled_cities guard restricts cure logic to the city just scanned.

    progress_cb, when provided, is called as
    progress_cb({"current_city": str, "completed": int, "total": int})
    before each city starts and after it persists.

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
    from engine.crawler import PageCapture, crawl_site, is_waf_challenge
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
    rows: List[Dict[str, Any]] = []
    total = len(targets)

    used_proxy_by_city: Dict[str, bool] = {}

    def _progress(city: str, completed: int, proxy_active: bool = False) -> None:
        if progress_cb:
            try:
                progress_cb({"current_city": city, "completed": completed,
                             "total": total, "proxy_active": bool(proxy_active)})
            except Exception:
                pass  # progress reporting must never break the scan

    for idx, target in enumerate(targets):
        city   = target["city"]
        domain = target.get("domain") or target.get("url", "")
        url    = target.get("url", domain)
        per_city_assets.setdefault(city, [])
        _progress(city, idx)
        city_failures: List[Dict[str, Any]] = []
        proxied = False   # did this city's crawl actually go through the residential proxy?

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
                # The proxy only actually applies when SCAN_PROXY_URL is configured.
                proxied = bool(use_proxy and _cfg.SCAN_PROXY_URL)
                if proxied:
                    _progress(city, idx, proxy_active=True)   # live "on residential IP" signal
                captures = crawl_site(url, use_proxy=use_proxy)

                # WAF auto-escalation: the operator can't know which cities
                # front with a WAF, so the flag is only a routing hint. If every
                # capture from a direct crawl looks like a challenge page and a
                # proxy is configured, retry once through the proxy.
                if (captures and not use_proxy and _cfg.SCAN_PROXY_URL
                        and all(is_waf_challenge(c) for c in captures)):
                    print(f"[pipeline] {city} | WAF challenge detected on direct crawl "
                          f"— auto-escalating to residential proxy")
                    proxied = True
                    _progress(city, idx, proxy_active=True)   # live escalation signal
                    captures = crawl_site(url, use_proxy=True)

                # Fail-secure: challenge pages carry no vendor surface. If all
                # captures are still challenges, treat the crawl as FAILED so
                # the city scores scan_failed — never a silent no_ai_detected.
                if captures and all(is_waf_challenge(c) for c in captures):
                    print(f"[pipeline] {city} | captures are WAF challenge pages "
                          f"— marking scan failed (fail-secure)")
                    captures = []
        except Exception as exc:
            import traceback as _tb
            print(f"[pipeline] WARN: crawl failed for {city} ({url}): {type(exc).__name__}: {exc}\n{_tb.format_exc()}")
            captures = []   # treat as no signal — city still gets a scorecard row

        # Only consider a city "crawled" if we got actual page content back.
        # An empty list means the crawler was blocked or failed — we must NOT
        # auto-cure that city's existing violations (could be a WAF false-negative).
        if captures:
            crawled_cities.add(city)
        used_proxy_by_city[city] = proxied

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

        best_assets = list(best.values())
        # A branded vendor match makes the structural "unknown chatbot" candidate
        # redundant — drop candidates when any confirmed vendor fired for the city.
        has_branded = any(a.verification_status != "candidate_review"
                          for a, _ in best_assets)
        for asset, cap in best_assets:
            is_candidate = asset.verification_status == "candidate_review"
            if is_candidate and has_branded:
                continue
            per_city_assets[city].append({
                "vendor_id":           asset.vendor_id,
                "display_name":        asset.display_name,
                "asset_type":          asset.asset_types,
                "match_confidence":    asset.match_confidence,
                "page_url":            asset.page_url,
                "verification_status": asset.verification_status,
            })
            # Candidates are surfaced for human review but NEVER auto-generate a
            # §552 violation — fail-secure without false-positive enforcement.
            if is_candidate:
                continue
            for v in validate(cap, asset, rules):
                city_failures.append({
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

        observed_failures.extend(city_failures)

        # ── Per-city reconcile + persist (incremental / real-time) ───────────
        # Equivalent to the old batch reconcile: records and observations are
        # city-keyed, and the crawled_cities guard means this call can only
        # open/refresh/cure THIS city's violations.
        state = reconcile(
            state, city_failures,
            crawled_cities=({city} if city in crawled_cities else set()),
        )
        city_open = [v for v in open_violations(state) if v["city"] == city]
        row = build_city_row(
            city=city,
            jurisdiction=target.get("jurisdiction", ""),
            domain=domain,
            assets=per_city_assets.get(city, []),
            open_violations=city_open,
            scorecard_cfg=scorecard_cfg,
            crawl_ok=(city in crawled_cities),
            used_proxy=used_proxy_by_city.get(city, False),
        )
        rows.append(row)
        try:
            # Write THIS city's row + violations now, so a polling dashboard
            # repaints while the run continues with the next city.
            repo.write_scorecard_rows([row])
            repo.write_violations(
                [v for v in state["violations"].values() if v.get("city") == city])
        except Exception as exc:
            # One city's persistence failure must not abort the whole run.
            print(f"[pipeline] WARN: persist failed for {city}: "
                  f"{type(exc).__name__}: {exc}")

        # ── Inventory discovery feed (must never break a scan) ───────────────
        # Upsert each detected asset into the AI Use-Case Inventory. Machine
        # fields only — the repo's merge contract preserves human fields
        # (owner, attestation, purpose). Skipped entirely if the crawl failed:
        # absence of evidence is not evidence of absence (fail-secure).
        if city in crawled_cities:
            try:
                _feed_inventory(repo, city, per_city_assets.get(city, []))
            except Exception as exc:
                print(f"[pipeline] WARN: inventory feed failed for {city}: "
                      f"{type(exc).__name__}: {exc}")
        _progress(city, idx + 1)

    all_open  = open_violations(state)
    scorecard = build_scorecard(rows, scorecard_cfg)

    def _safe_score(v):
        try:
            return int(float(str(v))) if v not in (None, "", "None", "NaN") else None
        except (ValueError, TypeError):
            return None
    scores = [s for s in (_safe_score(r.get("compliance_score")) for r in rows)
              if s is not None]
    repo.append_audit_log(
        event="scan_complete",
        city_count=scorecard["city_count"],
        failures=len(observed_failures),
        # avg_score + status counts feed the dashboard TrendChart;
        # summary/actor render in the Audit Log's activity columns.
        details={
            "open_violations": len(all_open),
            "avg_score":       round(sum(scores) / len(scores), 1) if scores else None,
            "compliant":       sum(1 for r in rows if r.get("traiga_status") == "compliant"),
            "in_cure":         sum(1 for r in rows if r.get("traiga_status") == "in_cure"),
            "scan_failed":     sum(1 for r in rows if r.get("traiga_status") == "scan_failed"),
            "summary":         f"Scan finished: {len(rows)} cities, "
                               f"{len(all_open)} open violations",
        },
    )

    return {
        "city_count":        scorecard["city_count"],
        "observed_failures": len(observed_failures),
        "open_violations":   len(all_open),
    }
