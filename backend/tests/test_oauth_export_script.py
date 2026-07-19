"""
test_oauth_export_script.py — the export script is served BY the backend.

WHY THE BACKEND SERVES IT. This PowerShell script produces the JSON that this same
service parses. Backend and frontend deploy as separate CI jobs, so hosting the script as
a frontend asset would let the producer and the parser drift: a city could download a
script whose output shape the running API no longer understands. Serving it from the
backend makes that impossible — they are one deployment.

It also removes a class of manual work that had already gone wrong once. The checksum used
to be typed into docs/INSTALL_OAUTH_MICROSOFT.md by hand, so every edit to the script
required remembering to update the document; a stale number tells a city their file was
tampered with when it wasn't. The hash is now COMPUTED from the file being served.
"""
import hashlib
import os

import pytest

from api.routes import discovery


def _script_file():
    return discovery._script_path("microsoft")


def test_script_ships_inside_the_backend_build_context():
    """The Docker build context is ./backend, so the script MUST live under backend/.

    This is the failure that made the endpoint necessary: the script originally sat in a
    top-level tools/ directory, which `docker build ./backend` never copies. The endpoint
    would have returned 500 in production while working perfectly on a developer machine.
    """
    path = _script_file()
    assert os.path.isfile(path)
    backend_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(discovery.__file__))))
    assert os.path.abspath(path).startswith(os.path.abspath(backend_root)), (
        "the export script must live under backend/ or it will not be in the container")


def test_meta_hash_is_computed_from_the_served_file():
    """The advertised checksum must be the checksum of the actual bytes we serve."""
    meta = discovery._script_meta("microsoft")
    expected = hashlib.sha256(open(_script_file(), "rb").read()).hexdigest()
    assert meta["sha256"] == expected
    assert len(meta["sha256"]) == 64
    assert meta["filename"] == "Export-EntraOAuthGrants.ps1"
    assert meta["size_bytes"] > 0


def test_meta_cache_invalidates_when_the_file_changes(tmp_path, monkeypatch):
    """A cached hash that outlives an edit is the same drift bug in a new place."""
    fake = tmp_path / "Export-EntraOAuthGrants.ps1"
    fake.write_text("# v1\n", encoding="utf-8")
    monkeypatch.setattr(discovery, "_SCRIPT_DIR", str(tmp_path))
    first = discovery._script_meta("microsoft")["sha256"]

    fake.write_text("# v2 — changed\n", encoding="utf-8")
    os.utime(fake, (fake.stat().st_atime + 10, fake.stat().st_mtime + 10))
    second = discovery._script_meta("microsoft")["sha256"]
    assert first != second, "the cache must key on mtime/size, not just path"


def test_unknown_provider_is_404_not_a_crash():
    """Google has no export script yet. Asking for one must be a clean 404."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        discovery._script_path("google")
    assert exc.value.status_code == 404


def test_missing_file_is_reported_as_a_deployment_error(tmp_path, monkeypatch):
    """If the script is absent from the image that is OUR fault, not the caller's — 500."""
    from fastapi import HTTPException
    monkeypatch.setattr(discovery, "_SCRIPT_DIR", str(tmp_path))
    with pytest.raises(HTTPException) as exc:
        discovery._script_path("microsoft")
    assert exc.value.status_code == 500


def test_script_is_still_read_only():
    """Guards the promise the install manual makes to a city IT admin.

    If a future edit ever introduces a write cmdlet or requests a ReadWrite scope, this
    fails — before a city is told, in writing, that the file cannot change their tenant.
    """
    text = open(_script_file(), encoding="utf-8-sig").read()
    for scope in ("Application.ReadWrite", "Directory.ReadWrite", "AppRoleAssignment.ReadWrite"):
        assert scope not in text, f"{scope} would break the read-only promise"
    import re
    writes = re.findall(r"\b(?:Set|New|Remove|Update|Add|Delete|Revoke|Disable|Enable)-Mg\w*", text)
    assert not writes, f"write cmdlets found: {writes}"
    assert "Application.Read.All" in text and "Directory.Read.All" in text


def test_install_manual_no_longer_hardcodes_a_checksum():
    """The manual must point at the dashboard rather than carry a hash that goes stale."""
    import pathlib
    repo_root = pathlib.Path(discovery.__file__).resolve().parents[3]
    doc = (repo_root / "docs" / "INSTALL_OAUTH_MICROSOFT.md").read_text(encoding="utf-8")
    import re
    stale = [ln for ln in doc.splitlines() if re.fullmatch(r"[0-9a-f]{64}", ln.strip())]
    assert not stale, (
        "a hardcoded SHA-256 in the manual will drift from the script; the dashboard "
        f"shows a computed one instead. Found: {stale}")
