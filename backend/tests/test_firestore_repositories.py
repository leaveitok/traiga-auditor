"""
test_firestore_repositories.py — unit tests for the Phase 2 Firestore backends.

Runs WITHOUT google-cloud-firestore or an emulator: a minimal in-memory fake
implements exactly the client surface the repositories use
(collection / document / get / set / update / delete / add / stream /
order_by / limit). Repos are instantiated via object.__new__ to bypass the
credential-loading constructor — everything above __init__ is real code.
"""
import json

import pytest

from core.repositories.firestore_repository import FirestoreRepository
from core.repositories.firestore_sentinel_repository import FirestoreSentinelRepository


# ── Fake Firestore client ─────────────────────────────────────────────────────

class _FakeSnap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self._id = doc_id

    def get(self):
        return _FakeSnap(self._id, self._store.get(self._id))

    def set(self, data):
        self._store[self._id] = dict(data)

    def update(self, patch):
        assert self._id in self._store, "update() on missing doc"
        self._store[self._id].update(patch)

    def delete(self):
        self._store.pop(self._id, None)


class _FakeQuery:
    def __init__(self, store, order_field=None, direction="ASCENDING", limit_n=None):
        self._store = store
        self._order_field = order_field
        self._direction = direction
        self._limit = limit_n

    def order_by(self, field, direction="ASCENDING"):
        return _FakeQuery(self._store, field, direction, self._limit)

    def limit(self, n):
        return _FakeQuery(self._store, self._order_field, self._direction, n)

    def stream(self):
        items = list(self._store.items())
        if self._order_field:
            items.sort(key=lambda kv: kv[1].get(self._order_field, ""),
                       reverse=(self._direction == "DESCENDING"))
        if self._limit is not None:
            items = items[: self._limit]
        return [_FakeSnap(k, v) for k, v in items]


class _FakeCollection(_FakeQuery):
    def __init__(self, store):
        super().__init__(store)
        self._n = 0

    def document(self, doc_id):
        return _FakeDocRef(self._store, doc_id)

    def add(self, data):
        self._n += 1
        doc_id = f"auto-{self._n:06d}"
        self._store[doc_id] = dict(data)
        return None, _FakeDocRef(self._store, doc_id)


class _FakeClient:
    def __init__(self):
        self._colls = {}

    def collection(self, name):
        store = self._colls.setdefault(name, {})
        coll = self._colls.setdefault(f"__obj_{name}", _FakeCollection(store))
        return coll


def _gov_repo():
    repo = object.__new__(FirestoreRepository)
    repo._db = _FakeClient()
    return repo


def _sentinel_repo():
    repo = object.__new__(FirestoreSentinelRepository)
    repo._db = _FakeClient()
    return repo


# ── Governance repository ─────────────────────────────────────────────────────

def test_target_roundtrip_and_string_contract():
    repo = _gov_repo()
    out = repo.add_target("City of Lewisville", "TX", "cityoflewisville.com",
                          "https://www.cityoflewisville.com", ["home"], True)
    assert out["cloudflare_protected"] is True
    rows = repo.get_targets()
    assert len(rows) == 1
    r = rows[0]
    assert r["city"] == "City of Lewisville"
    assert r["cloudflare_protected"] is True          # normalised to bool on read
    assert isinstance(r["active"], str)               # stored values stay strings
    assert json.loads(r["tags"]) == ["home"]


def test_deactivate_target_hides_from_get_targets():
    repo = _gov_repo()
    t = repo.add_target("A", "TX", "a.gov", "https://a.gov", [])
    assert repo.deactivate_target(t["id"]) is True
    assert repo.get_targets() == []
    assert repo.deactivate_target("nonexistent") is False


def test_scorecard_upsert_summary_delete():
    repo = _gov_repo()
    repo.write_scorecard_rows([
        {"city": "A", "traiga_status": "compliant", "compliance_score": 95,
         "open_violations": [], "band": "green"},
        {"city": "B", "traiga_status": "in_cure", "compliance_score": 60,
         "open_violations": [1, 2], "band": "orange"},
    ])
    # upsert: same city again must overwrite, not duplicate
    repo.write_scorecard_rows([
        {"city": "B", "traiga_status": "compliant", "compliance_score": 100,
         "open_violations": [], "band": "green"},
    ])
    rows = repo.get_scorecard()
    assert len(rows) == 2
    s = repo.get_scorecard_summary()
    assert s["total_cities"] == 2 and s["compliant"] == 2 and s["in_cure"] == 0
    assert s["average_compliance_score"] == 97.5
    assert repo.delete_scorecard_row("A") is True
    assert repo.delete_scorecard_row("A") is False
    assert len(repo.get_scorecard()) == 1


def test_violations_filtering_and_upsert():
    repo = _gov_repo()
    repo.write_violations([
        {"violation_id": "v1", "city": "Lewisville", "status": "in_cure",
         "evidence": {"k": 1}},
        {"violation_id": "v2", "city": "Plano", "status": "cured"},
    ])
    repo.write_violations([{"violation_id": "v1", "city": "Lewisville",
                            "status": "cured"}])          # upsert same id
    assert len(repo.get_violations()) == 2
    assert len(repo.get_violations(status="cured")) == 2
    assert len(repo.get_violations(city="lewisville")) == 1   # case-insensitive


def test_audit_log_newest_first_with_limit():
    repo = _gov_repo()
    for i in range(5):
        repo.append_audit_log(f"scan_{i}", i, 0, {"i": i})
    rows = repo.get_audit_log(limit=3)
    assert len(rows) == 3
    assert rows[0]["event"] == "scan_4"                   # newest first


def test_users_upsert_preserves_created_and_is_case_insensitive():
    repo = _gov_repo()
    repo.upsert_user("Chris@Example.com", "admin", "Lewisville")
    first = repo.get_user("chris@example.com")
    assert first is not None and first["role"] == "admin"
    repo.upsert_user("chris@example.com", "city", None)
    second = repo.get_user("CHRIS@EXAMPLE.COM")
    assert second["role"] == "city"
    assert second["created_utc"] == first["created_utc"]  # not reset on update
    assert len(repo.get_users()) == 1                     # upsert, no duplicate


# ── Sentinel repository ───────────────────────────────────────────────────────

def _event(eid, user="jdoe@cityoflewisville.com", policy="TX-PII-SSN", ts="2026-07-05T01:00:00+00:00"):
    return {
        "event_id": eid, "timestamp_utc": ts, "received_utc": ts,
        "device_id": "LWV-LT-1", "user_id": user,
        "detections_json": json.dumps([{"policy_id": policy, "match_count": 1}]),
        "action_taken": "blocked",
    }


def test_sentinel_rejects_prohibited_fields():
    repo = _sentinel_repo()
    with pytest.raises(ValueError):
        repo.store_event({**_event("e1"), "matched_text": "453-98-1122"})
    with pytest.raises(ValueError):
        repo.store_heartbeat({"event_id": "h1", "file_name": "John_Doe_SSN.pdf"})
    assert repo.get_events() == [] and repo.get_heartbeats() == []


def test_sentinel_event_ingest_is_idempotent():
    repo = _sentinel_repo()
    repo.store_event(_event("dup-1"))
    repo.store_event(_event("dup-1"))                     # extension retry
    assert len(repo.get_events()) == 1


def test_sentinel_unknown_keys_dropped_and_filters_work():
    repo = _sentinel_repo()
    repo.store_event({**_event("e1"), "unexpected_key": "x"})
    repo.store_event(_event("e2", user="asmith@cityoflewisville.com",
                            policy="CJIS-ID", ts="2026-07-05T02:00:00+00:00"))
    rows = repo.get_events()
    assert len(rows) == 2
    assert rows[0]["event_id"] == "e2"                    # newest first
    assert "unexpected_key" not in rows[1]                # column projection
    assert [r["event_id"] for r in repo.get_events(policy_id="CJIS-ID")] == ["e2"]
    assert [r["event_id"] for r in repo.get_events(user_id="jdoe@cityoflewisville.com")] == ["e1"]
    assert len(repo.get_events(limit=1)) == 1


def test_sentinel_heartbeats_newest_first_with_limit():
    repo = _sentinel_repo()
    for i in range(4):
        repo.store_heartbeat({"event_id": f"hb-{i}", "device_id": "LWV-LT-1",
                              "status": "ok",
                              "received_utc": f"2026-07-05T0{i}:00:00+00:00"})
    rows = repo.get_heartbeats(limit=2)
    assert [r["event_id"] for r in rows] == ["hb-3", "hb-2"]
