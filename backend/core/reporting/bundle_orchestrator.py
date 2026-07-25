"""
bundle_orchestrator.py — evidence-bundle orchestration (core/, does I/O).

The seam between the PURE engine (engine/reporting/*) and the outside world. It:
  * assembles a city's live governance data from the repository,
  * calls the pure bundle_spec to build a BundleModel,
  * renders to PDF / DOCX, and for a package preset assembles a zip with attachments.

Phase 1 is on-demand (no persistence). Snapshot storage arrives in Phase 2 behind an
ArtifactStore abstraction; nothing here assumes a storage backend, so that addition will
not touch this file's data-assembly logic.
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from typing import Any, Dict, List, Optional

from engine.reporting import bundle_spec, render_docx, render_pdf

_MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "zip": "application/zip",
}


def list_presets(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Preset catalogue for the UI. Data-driven from SCHEMA_DEFINITION.json."""
    presets = (schema.get("Report_Bundles", {}) or {}).get("presets", {}) or {}
    out = []
    for key, p in presets.items():
        out.append({
            "key": key,
            "title": p.get("title", key),
            "audience": p.get("audience", ""),
            "depth": p.get("depth", "summary"),
            "package": bool(p.get("package")),
            "formats": p.get("formats", ["pdf"]),
            "section_count": len(p.get("sections", [])),
        })
    return out


def _preset_or_404(schema: Dict[str, Any], preset_key: str) -> Dict[str, Any]:
    presets = (schema.get("Report_Bundles", {}) or {}).get("presets", {}) or {}
    preset = presets.get(preset_key)
    if not preset:
        raise KeyError(preset_key)
    return preset


def assemble_city_data(repo: Any, city: str) -> Dict[str, Any]:
    """Pull the city's live governance data into the shape bundle_spec expects.

    Uses the full ai_assets registry (every provenance) rather than the scan-only
    scorecard column, so the discovered-vs-declared story spans all channels.
    TODO: scope to the requesting user's jurisdiction (enforced in the route today).
    """
    rows = repo.get_scorecard()
    sc = next((r for r in rows if r.get("city") == city), None)
    if sc is None:
        raise LookupError(city)

    # Full registry (OAuth, procurement, agenda, scan, declared) — the rich inventory.
    try:
        assets = repo.get_ai_assets(city=city) or []
    except Exception:
        assets = []
    # Normalize field names the spec reads.
    norm_assets = []
    for a in assets:
        at = a.get("asset_types") or a.get("asset_type")
        if isinstance(at, str):
            try:
                at = json.loads(at)
            except Exception:
                at = [at]
        norm_assets.append({
            "display_name": a.get("display_name") or a.get("vendor_id") or "",
            "vendor_id": a.get("vendor_id", ""),
            "asset_type": at if isinstance(at, list) else [str(at)] if at else [],
            "provenance": a.get("provenance", "declared"),
            "match_confidence": a.get("match_confidence") or a.get("confidence"),
            "verification_status": a.get("verification_status", "candidate"),
            "page_url": a.get("page_url", ""),
        })

    violations = [v for v in repo.get_violations() if v.get("city") == city
                  and v.get("status") != "cured"]
    for v in violations:
        if isinstance(v.get("evidence_json"), str):
            try:
                v["evidence"] = json.loads(v["evidence_json"])
            except Exception:
                v["evidence"] = {}

    return {"city": city, "scorecard": sc, "ai_assets": norm_assets, "violations": violations}


def build_model(repo: Any, city: str, preset_key: str, schema: Dict[str, Any],
                tool_release: str = "dev") -> Dict[str, Any]:
    """Assemble data + build the pure BundleModel (used by preview and generate)."""
    preset = _preset_or_404(schema, preset_key)
    data = assemble_city_data(repo, city)
    return bundle_spec.build_bundle(data, preset, tool_release=tool_release)


def render_single(model: Dict[str, Any], fmt: str) -> bytes:
    if fmt == "pdf":
        return render_pdf.render(model)
    if fmt == "docx":
        return render_docx.render(model)
    raise ValueError(fmt)


# ── Attachments (package presets only) ───────────────────────────────────────

def _attachment_inventory_csv(data: Dict[str, Any]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Vendor / System", "Type", "Source (provenance)", "Confidence",
                "Status", "Location"])
    for a in data.get("ai_assets", []):
        conf = a.get("match_confidence")
        w.writerow([
            a.get("display_name", ""),
            ", ".join(a.get("asset_type", [])) if isinstance(a.get("asset_type"), list) else a.get("asset_type", ""),
            bundle_spec.PROVENANCE_LABELS.get(a.get("provenance", ""), a.get("provenance", "")),
            f"{float(conf) * 100:.0f}%" if isinstance(conf, (int, float)) else "",
            a.get("verification_status", ""),
            a.get("page_url", ""),
        ])
    return buf.getvalue().encode("utf-8")


def _attachment_provenance_appendix(data: Dict[str, Any]) -> bytes:
    lines = ["PROVENANCE APPENDIX", "=" * 60,
             "Each AI system and the discovery channel that surfaced it.", ""]
    for a in data.get("ai_assets", []):
        prov = a.get("provenance", "declared")
        lines.append(f"- {a.get('display_name','(unnamed)')}")
        lines.append(f"    source     : {bundle_spec.PROVENANCE_LABELS.get(prov, prov)}")
        lines.append(f"    status     : {a.get('verification_status','candidate')}")
        if a.get("page_url"):
            lines.append(f"    location   : {a.get('page_url')}")
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def _attachment_audit_log_excerpt(repo: Any, city: str) -> bytes:
    try:
        rows = repo.get_audit_log(limit=100)
    except Exception:
        rows = []
    hit = [r for r in rows if str(r.get("details", {}).get("city", "")) == city
           or city in json.dumps(r.get("details", {}), default=str)]
    lines = ["AUDIT LOG EXCERPT", "=" * 60,
             f"Recent recorded activity referencing {city}.", ""]
    for r in (hit or rows)[:50]:
        lines.append(f"{r.get('timestamp_utc','')}  {r.get('event','')}  "
                     f"{r.get('details', {}).get('summary','')}")
    return "\n".join(lines).encode("utf-8")


_ATTACHMENTS = {
    "inventory_csv": ("inventory.csv", lambda repo, city, data: _attachment_inventory_csv(data)),
    "provenance_appendix": ("provenance_appendix.txt", lambda repo, city, data: _attachment_provenance_appendix(data)),
    "audit_log_excerpt": ("audit_log_excerpt.txt", lambda repo, city, data: _attachment_audit_log_excerpt(repo, city)),
}


def build_package(repo: Any, city: str, preset_key: str, schema: Dict[str, Any],
                  tool_release: str = "dev") -> bytes:
    """Zip: report.pdf + report.docx + the preset's attachments. For package presets."""
    preset = _preset_or_404(schema, preset_key)
    data = assemble_city_data(repo, city)
    model = bundle_spec.build_bundle(data, preset, tool_release=tool_release)
    doc_id = model["meta"]["doc_id"]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{doc_id}.pdf", render_pdf.render(model))
        z.writestr(f"{doc_id}.docx", render_docx.render(model))
        for att_key in preset.get("attachments", []):
            spec = _ATTACHMENTS.get(att_key)
            if not spec:
                continue
            fname, fn = spec
            try:
                z.writestr(f"attachments/{fname}", fn(repo, city, data))
            except Exception as exc:  # an attachment must never fail the whole package
                z.writestr(f"attachments/{fname}.ERROR.txt",
                           f"Could not generate: {type(exc).__name__}: {exc}".encode("utf-8"))
        # A manifest with the content hash so the package is self-describing.
        manifest = {
            "doc_id": doc_id,
            "city": city,
            "preset": preset_key,
            "generated_utc": model["meta"]["generated_utc"],
            "tool_release": tool_release,
            "content_sha256": model["meta"]["content_sha256"],
            "attachments": preset.get("attachments", []),
        }
        z.writestr("MANIFEST.json", json.dumps(manifest, indent=2).encode("utf-8"))
    return buf.getvalue()


def media_type(fmt: str) -> str:
    return _MEDIA.get(fmt, "application/octet-stream")


# ── Snapshots (Evidence Room — Phase 2) ──────────────────────────────────────
# A snapshot freezes the render-agnostic BundleModel. Any format re-renders from it
# deterministically, and the stored content hash proves the findings are unchanged. No
# blob store is needed in beta because the frozen model is small JSON; the ArtifactStore
# abstraction (design doc) is where prod would additionally persist rendered bytes to GCS.

import uuid as _uuid


def _inv_csv_from_model(model: Dict[str, Any]) -> bytes:
    """Rebuild the inventory CSV from the FROZEN model's asset_inventory section, so a
    snapshot package is fully self-contained (no live repo access, byte-reproducible)."""
    inv = next((s for s in model.get("sections", []) if s.get("kind") == "asset_inventory"), None)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Vendor / System", "Type", "Source (provenance)", "Confidence", "Status", "Location"])
    for r in (inv or {}).get("rows", []):
        w.writerow([r.get("vendor", ""), r.get("type", ""), r.get("source", ""),
                    r.get("confidence", ""), r.get("status", ""), r.get("location", "")])
    return buf.getvalue().encode("utf-8")


def _prov_appendix_from_model(model: Dict[str, Any]) -> bytes:
    prov = next((s for s in model.get("sections", []) if s.get("kind") == "provenance_summary"), None)
    inv = next((s for s in model.get("sections", []) if s.get("kind") == "asset_inventory"), None)
    lines = ["PROVENANCE APPENDIX", "=" * 60]
    if prov:
        lines += [prov.get("headline", ""), ""]
        for r in prov.get("rows", []):
            lines.append(f"  {r.get('source','')}: {r.get('count','')} "
                         f"({'discovered' if r.get('discovered') else 'declared'})")
        lines.append("")
    for r in (inv or {}).get("rows", []):
        lines.append(f"- {r.get('vendor','')}  [{r.get('source','')}]  status={r.get('status','')}")
    return "\n".join(lines).encode("utf-8")


def build_package_from_model(model: Dict[str, Any]) -> bytes:
    """Zip a bundle from a FROZEN model alone: PDF + DOCX + attachments (derived from the
    model) + a manifest carrying the content hash. Used to re-render a saved snapshot's
    package with no live data, so the evidence is reproducible from what was stored."""
    meta = model["meta"]
    doc_id = meta["doc_id"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{doc_id}.pdf", render_pdf.render(model))
        z.writestr(f"{doc_id}.docx", render_docx.render(model))
        if any(s.get("kind") == "asset_inventory" for s in model.get("sections", [])):
            z.writestr("attachments/inventory.csv", _inv_csv_from_model(model))
            z.writestr("attachments/provenance_appendix.txt", _prov_appendix_from_model(model))
        z.writestr("MANIFEST.json", json.dumps({
            "doc_id": doc_id, "city": meta.get("city"), "audience": meta.get("audience"),
            "generated_utc": meta.get("generated_utc"), "tool_release": meta.get("tool_release"),
            "content_sha256": meta.get("content_sha256"),
        }, indent=2).encode("utf-8"))
    return buf.getvalue()


def create_snapshot(repo: Any, city: str, preset_key: str, schema: Dict[str, Any],
                    actor: str = "unknown", tool_release: str = "dev") -> Dict[str, Any]:
    """Build a bundle and persist it as an immutable snapshot. Returns the stored metadata
    (without the frozen model_json). TODO: enforce write:reports for the city."""
    model = build_model(repo, city, preset_key, schema, tool_release=tool_release)
    meta = model["meta"]
    record = {
        "id": str(_uuid.uuid4())[:8],
        "city": city,
        "preset": preset_key,
        "audience": meta.get("audience", ""),
        "title": meta.get("preset_title", ""),
        "generated_utc": meta.get("generated_utc", ""),
        "generated_by": actor,
        "tool_release": tool_release,
        "content_sha256": meta.get("content_sha256", ""),
        "source_fingerprint": meta.get("source_fingerprint", ""),
        "model_json": json.dumps(model),
    }
    saved = repo.save_report_snapshot(record)
    return {k: v for k, v in saved.items() if k != "model_json"}


def list_snapshots(repo: Any, city: Optional[str] = None) -> List[Dict[str, Any]]:
    """Snapshot metadata + a `stale` flag. A snapshot is stale when the city's live source
    data no longer matches the fingerprint captured at generation — i.e. a scan or a
    declaration changed the findings since. Live fingerprints are computed once per city."""
    rows = repo.get_report_snapshots(city)
    live_fp_cache: Dict[str, Optional[str]] = {}

    def _live_fp(c: str) -> Optional[str]:
        if c not in live_fp_cache:
            try:
                from engine.reporting import bundle_spec
                live_fp_cache[c] = bundle_spec.source_fingerprint(assemble_city_data(repo, c))
            except Exception:
                live_fp_cache[c] = None
        return live_fp_cache[c]

    out = []
    for r in rows:
        lf = _live_fp(r.get("city", ""))
        r = dict(r)
        r["stale"] = bool(lf is not None and r.get("source_fingerprint") and r["source_fingerprint"] != lf)
        out.append(r)
    return out


def _snapshot_model(repo: Any, snapshot_id: str) -> Optional[Dict[str, Any]]:
    snap = repo.get_report_snapshot(snapshot_id)
    if not snap:
        return None
    mj = snap.get("model_json")
    if isinstance(mj, str):
        try:
            return json.loads(mj)
        except Exception:
            return None
    return mj if isinstance(mj, dict) else None


def render_snapshot(repo: Any, snapshot_id: str, fmt: str) -> Optional[bytes]:
    """Re-render a saved snapshot to pdf|docx from its frozen model. Deterministic."""
    model = _snapshot_model(repo, snapshot_id)
    if model is None:
        return None
    return render_single(model, fmt)


def render_snapshot_package(repo: Any, snapshot_id: str) -> Optional[bytes]:
    model = _snapshot_model(repo, snapshot_id)
    if model is None:
        return None
    return build_package_from_model(model)


def snapshot_doc_id(repo: Any, snapshot_id: str) -> str:
    model = _snapshot_model(repo, snapshot_id)
    return (model or {}).get("meta", {}).get("doc_id", snapshot_id)
