"""
test_settings.py — admin operational settings / feature flags.

Verifies the allowlist (secrets rejected), coercion/clamping, enum fallback,
audit logging, and the UI schema — backed by a fake key-value repo (the same
get_run_state/save_run_state surface all real repos already implement).
"""
from core import settings


class FakeRepo:
    def __init__(self):
        self.kv = {}
        self.audit = []

    def get_run_state(self, key):
        return dict(self.kv.get(key, {}))

    def save_run_state(self, key, value):
        self.kv[key] = dict(value)

    def append_audit_log(self, **kwargs):
        self.audit.append(kwargs)


def test_defaults_from_config():
    r = FakeRepo()
    d = settings.get_all(r)
    assert set(d) == set(settings.SETTABLE)          # only allowlisted keys
    assert d["AGENDA_LLM_PROVIDER"] in ("keyword", "vertex", "none")


def test_save_coerces_and_allowlists():
    r = FakeRepo()
    eff = settings.save(r, {
        "AGENDA_ENGINE_ENABLED": "true",
        "AGENDA_LLM_PROVIDER": "vertex",
        "AGENDA_LOOKBACK_MONTHS": "999",     # over max → clamped
        "SCAN_PROXY_URL": "http://leak",     # NOT allowlisted → ignored (secret)
    }, actor="cio@test.gov")

    assert eff["AGENDA_ENGINE_ENABLED"] is True
    assert settings.get_bool(r, "AGENDA_ENGINE_ENABLED") is True
    assert eff["AGENDA_LLM_PROVIDER"] == "vertex"
    assert eff["AGENDA_LOOKBACK_MONTHS"] == settings.SETTABLE["AGENDA_LOOKBACK_MONTHS"]["max"]
    assert "SCAN_PROXY_URL" not in r.kv.get("app_settings", {})   # secret never stored
    assert any(a["event"] == "settings_changed" for a in r.audit)


def test_bad_enum_falls_back():
    r = FakeRepo()
    eff = settings.save(r, {"AGENDA_LLM_PROVIDER": "bogus"})
    assert eff["AGENDA_LLM_PROVIDER"] == "keyword"


def test_agenda_llm_model_is_settable_enum():
    r = FakeRepo()
    # Valid model is accepted and stored.
    eff = settings.save(r, {"AGENDA_LLM_MODEL": "gemini-3.1-flash-lite"})
    assert eff["AGENDA_LLM_MODEL"] == "gemini-3.1-flash-lite"
    # Off-list model falls back to the default (never a broken model id).
    eff = settings.save(r, {"AGENDA_LLM_MODEL": "gpt-4o"})
    assert eff["AGENDA_LLM_MODEL"] == settings.SETTABLE["AGENDA_LLM_MODEL"]["default"]()


def test_public_schema_has_no_defaults_or_secrets():
    sch = settings.public_schema()
    assert all("default" not in spec for spec in sch.values())
    assert "SCAN_PROXY_URL" not in sch and "GOOGLE_SERVICE_ACCOUNT_FILE" not in sch
