"""
site_metadata.py — PURE site-metadata detector (engine/, no HTTP, no repo, no LLM).

From the observable surface a website scan already captures (page HTML + observed
hosts), infer CANDIDATE governance metadata about the city's stack:
  - agenda_platform + agenda_client (Legistar slug etc.) + agenda_url
  - cms  (content management system)
  - privacy_policy_url

Signatures live in SCHEMA_DEFINITION.json → Site_Metadata_Signatures (governance-as-
code: add a platform/CMS with JSON only, no code change). Everything returned here is
an UNVERIFIED CANDIDATE — the same discipline as vendor fingerprints — until a human
confirms it. The caller persists these, never overwriting a human-verified value.

Reliability note: this only sees the pages the crawler fetched (~3, depth 1). A city
whose homepage does not link its agenda portal will yield no agenda_client here — the
value is then supplied by the agenda-run backstop (the slug a user enters is persisted).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

# Keys always present in the result (empty string = not found).
_FIELDS = ("agenda_platform", "agenda_client", "agenda_url", "cms", "privacy_policy_url")

_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)


def _empty() -> Dict[str, str]:
    return {k: "" for k in _FIELDS}


def _collect(pages: Iterable[Dict[str, Any]]):
    """Flatten pages → (combined lowercased html blob, list of hosts, list of hrefs)."""
    blobs: List[str] = []
    hosts: List[str] = []
    hrefs: List[str] = []
    for pg in pages or []:
        html = pg.get("html") or ""
        blobs.append(html)
        for h in (pg.get("hosts") or []):
            if h:
                hosts.append(str(h).lower())
        for m in _HREF_RE.finditer(html):
            hrefs.append(m.group(1))
    return "\n".join(blobs), hosts, hrefs


def _detect_agenda(blob: str, hosts: List[str], platforms: List[Dict[str, Any]]) -> Dict[str, str]:
    """First matching agenda platform wins. Search observed hosts first (most reliable),
    then the raw HTML (catches a plain <a href> to the portal)."""
    haystacks = list(hosts) + [blob.lower()]
    for plat in platforms or []:
        rgx = plat.get("host_regex")
        if not rgx:
            continue
        try:
            pat = re.compile(rgx, re.I)
        except re.error:
            continue
        stop = {str(s).lower() for s in plat.get("slug_stoplist", [])}
        grp = int(plat.get("slug_group", 1) or 0)
        for hay in haystacks:
            m = pat.search(hay or "")
            if not m:
                continue
            slug = ""
            if grp and m.lastindex and grp <= m.lastindex:
                slug = (m.group(grp) or "").lower()
            if slug and slug in stop:
                continue
            host = m.group(0)
            url = host if host.lower().startswith("http") else f"https://{host}"
            return {"agenda_platform": plat.get("platform", ""),
                    "agenda_client": slug, "agenda_url": url}
    return {"agenda_platform": "", "agenda_client": "", "agenda_url": ""}


def _detect_cms(blob: str, cms_sigs: List[Dict[str, Any]]) -> str:
    for c in cms_sigs or []:
        rgx = c.get("html_regex")
        if not rgx:
            continue
        try:
            if re.search(rgx, blob, re.I):
                return c.get("name", "")
        except re.error:
            continue
    return ""


def _detect_privacy(hrefs: List[str], link_regex: str) -> str:
    try:
        pat = re.compile(link_regex or "privacy", re.I)
    except re.error:
        pat = re.compile("privacy", re.I)
    for href in hrefs:
        if pat.search(href or ""):
            return href
    return ""


def detect_site_metadata(pages: Iterable[Dict[str, Any]],
                         schema: Dict[str, Any]) -> Dict[str, str]:
    """
    pages: iterable of {"html": str, "url": str, "hosts": [str, ...]} (hosts = a page's
           script_hosts + iframe_origins + network_urls). schema: the loaded
           SCHEMA_DEFINITION.json. Returns a dict with every _FIELDS key (empty = absent).

    TODO: results are candidates — caller stores unverified, never clobbers a human value.
    """
    sig = (schema or {}).get("Site_Metadata_Signatures", {}) or {}
    blob, hosts, hrefs = _collect(pages)
    out = _empty()
    out.update(_detect_agenda(blob, hosts, sig.get("agenda_platforms", [])))
    out["cms"] = _detect_cms(blob, sig.get("cms", []))
    out["privacy_policy_url"] = _detect_privacy(hrefs, sig.get("privacy_link_regex", "privacy"))
    return out
