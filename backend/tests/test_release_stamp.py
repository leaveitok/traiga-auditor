"""
test_release_stamp.py — the release identifier surfaced by /health.

Context: on 2026-07-18 a feature shipped with two of its files never committed. Local
tests were green because pytest reads the working directory while git ships the index.
The release-stamping mechanism exists so that "what is running?" has a short, human
answer you can ask a pilot city to read off their screen. These tests protect the two
properties that make that answer trustworthy:

  1. /health exposes BOTH a human release and a unique commit SHA. The release alone is
     not sufficient (someone can ship without stamping); the SHA alone is useless to say
     out loud on a phone call. Dropping either one breaks a real workflow.
  2. Both fail SOFT to "dev" rather than raising or reporting a stale value. A health
     endpoint that 500s because an env var is unset takes the dashboard down with it.

The VERSION-file format is asserted here too, because the ship bats parse it with cmd's
`for /f ... delims=.` and a reformat would silently break every future stamp.
"""
import os
import re
from pathlib import Path

from api.routes.health import health_check

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_health_exposes_release_and_commit(monkeypatch):
    monkeypatch.setenv("APP_RELEASE", "01.7")
    monkeypatch.setenv("GIT_SHA", "3986274abcdef0123456789")
    body = health_check()
    assert body["release"] == "01.7"
    # SHA is truncated for display but must stay long enough to be unambiguous.
    assert body["version"] == "3986274abcde"
    assert len(body["version"]) == 12


def test_health_falls_back_to_dev_when_unstamped(monkeypatch):
    """Local dev, or a deploy that forgot to inject the vars. Must not raise."""
    monkeypatch.delenv("APP_RELEASE", raising=False)
    monkeypatch.delenv("GIT_SHA", raising=False)
    body = health_check()
    assert body["release"] == "dev"
    assert body["version"] == "dev"
    assert body["status"] == "ok"


def test_version_file_is_parseable_by_the_ship_bats():
    """_release_stamp.bat splits VERSION on '.' and runs `set /a` on the MINOR part.

    Two things would silently break it:
      - a format other than MAJOR.MINOR (the bat would read an empty minor)
      - a MINOR with a leading zero, because cmd's `set /a` treats 08/09 as OCTAL
    """
    version_file = REPO_ROOT / "VERSION"
    assert version_file.exists(), "VERSION is the single source of truth; do not remove it"
    raw = version_file.read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"\d+\.\d+", raw), f"VERSION must be MAJOR.MINOR, got {raw!r}"
    minor = raw.split(".")[1]
    assert minor == str(int(minor)), (
        f"MINOR {minor!r} has a leading zero; cmd's set /a would read it as octal"
    )


def test_releases_log_table_stays_append_only():
    """The bat appends a row with >>, so the table must be the LAST thing in the file.

    If someone adds prose below the table, every future release row lands after it and
    the table stops rendering.
    """
    releases = REPO_ROOT / "RELEASES.md"
    assert releases.exists()
    lines = [ln for ln in releases.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines[-1].lstrip().startswith("|"), (
        "The last non-blank line of RELEASES.md must be part of the table — "
        "_release_stamp.bat appends rows to the end of the file."
    )
