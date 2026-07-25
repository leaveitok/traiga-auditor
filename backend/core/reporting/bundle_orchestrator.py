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
