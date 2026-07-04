"""
rule_loader.py — load and structurally validate SCHEMA_DEFINITION.json.

Keeps the governance-as-code contract honest: if the schema is malformed or
missing required sections, fail loudly before any scan runs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from . import config


class SchemaError(Exception):
    """Raised when SCHEMA_DEFINITION.json is missing or structurally invalid."""


_REQUIRED_TOP_LEVEL = ["meta", "AI_Vendor_Fingerprints", "Compliance_Ruleset",
                       "violation_template", "scorecard_schema"]


def load_schema(path: Path | None = None) -> Dict[str, Any]:
    """Load the schema from disk and run lightweight structural validation."""
    schema_path = path or config.local_path(config.SCHEMA_FILE)
    if not Path(schema_path).exists():
        raise SchemaError(f"Schema not found at {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as fh:
        try:
            schema = json.load(fh)
        except json.JSONDecodeError as exc:
            raise SchemaError(f"Schema is not valid JSON: {exc}") from exc

    _validate(schema)
    return schema


def _validate(schema: Dict[str, Any]) -> None:
    missing = [k for k in _REQUIRED_TOP_LEVEL if k not in schema]
    if missing:
        raise SchemaError(f"Schema missing required sections: {missing}")

    # Vendor module sanity.
    vendors = schema["AI_Vendor_Fingerprints"].get("vendors", [])
    if not isinstance(vendors, list) or not vendors:
        raise SchemaError("AI_Vendor_Fingerprints.vendors must be a non-empty list")

    # Every external rule must carry a citation and an evaluator.
    ext = schema["Compliance_Ruleset"].get("External_Transparency_Module", {})
    for rule in ext.get("rules", []):
        for field in ("rule_id", "citation", "evaluator", "severity"):
            if field not in rule:
                raise SchemaError(f"Rule {rule.get('rule_id', '?')} missing '{field}'")

    # Violation template must require cure_period_status + days_remaining (project mandate).
    required = schema["violation_template"].get("required", [])
    for field in ("cure_period_status", "days_remaining"):
        if field not in required:
            raise SchemaError(f"violation_template must require '{field}'")


def get_vendors(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    return schema["AI_Vendor_Fingerprints"]["vendors"]


def get_match_threshold(schema: Dict[str, Any]) -> float:
    return float(schema["AI_Vendor_Fingerprints"].get("match_threshold", 0.6))


def get_external_rules(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    module = schema["Compliance_Ruleset"]["External_Transparency_Module"]
    return module.get("rules", []) if module.get("enabled", False) else []
