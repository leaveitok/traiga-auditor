"""
test_graph_join.py — the browser-only (Graph Explorer) input path.

WHY THIS PATH EXISTS. Many municipal shops run endpoint protection, AppLocker, WDAC or
Constrained Language Mode that blocks PowerShell. Those cities cannot run our export
script at all. The usual workaround — a .bat invoking `powershell -ExecutionPolicy
Bypass` — is the signature move of commodity malware, so it raises the chance of being
quarantined AND asks a security team to weaken a control in order to run a compliance
tool. We ship the opposite: an administrator runs two GET queries in Microsoft's own
Graph Explorer and uploads the raw JSON. Nothing executes on the endpoint.

The join our PowerShell script performs locally is reproduced here server-side, so both
methods converge on identical records before any business logic sees them.

Endpoints (Microsoft Graph v1.0):
  GET /servicePrincipals?$select=id,appId,displayName,publisherName,signInAudience
  GET /oauth2PermissionGrants
"""
import json

import pytest

from engine.collectors import graph_join


def _sps(*rows):
    return {"@odata.context": "https://graph.microsoft.com/v1.0/$metadata", "value": list(rows)}


def _grants(*rows):
    return {"@odata.context": "https://graph.microsoft.com/v1.0/$metadata", "value": list(rows)}


SP_CHATGPT = {"id": "sp-1", "appId": "1950a258-227b-4e31-a9cf-717495945fc2",
              "displayName": "ChatGPT", "publisherName": "OpenAI, L.L.C.",
              "signInAudience": "AzureADMultipleOrgs"}
SP_FIREFLIES = {"id": "sp-2", "appId": "d4f5-0000-0004", "displayName": "Fireflies.ai Notetaker",
                "publisherName": "Fireflies.ai", "signInAudience": "AzureADMultipleOrgs"}


# ── File identification ──────────────────────────────────────────────────────

def test_files_are_identified_by_shape_not_by_filename():
    """The admin downloads two files and cannot be expected to label them correctly.

    Requiring a naming convention would be a support burden for zero benefit, so each
    file is identified by its contents and either upload order works.
    """
    assert graph_join.classify_graph_file(_sps(SP_CHATGPT)) == "service_principals"
    assert graph_join.classify_graph_file(
        _grants({"clientId": "sp-1", "consentType": "Principal", "scope": "User.Read"})
    ) == "permission_grants"
    assert graph_join.classify_graph_file({"value": []}) == "unknown"


def test_script_export_is_not_mistaken_for_graph_output():
    """Method A's file must never be routed down Method B's join."""
    assert graph_join.looks_like_graph_payload({"grants": [{"app_name": "X"}]}) is False
    assert graph_join.looks_like_graph_payload(_sps(SP_CHATGPT)) is True


# ── The join ─────────────────────────────────────────────────────────────────

def test_join_reproduces_what_the_script_produces_locally():
    grants, meta = graph_join.join_graph_exports(
        _sps(SP_CHATGPT),
        _grants({"clientId": "sp-1", "consentType": "Principal",
                 "principalId": "u1", "scope": "User.Read openid"}),
    )
    assert len(grants) == 1
    g = grants[0]
    assert g["app_name"] == "ChatGPT"
    assert g["app_id"] == SP_CHATGPT["appId"]
    assert g["publisher"] == "OpenAI, L.L.C."
    assert g["sign_in_audience"] == "AzureADMultipleOrgs"
    assert g["scopes"] == ["User.Read", "openid"]      # space-delimited, sorted
    assert g["user_count"] == 1
    assert meta["apps_joined"] == 1


def test_the_same_person_consenting_twice_counts_once():
    """Graph returns one grant per (app, user, resource) — a user can appear repeatedly.

    Counting rows instead of distinct principals would inflate 'how many staff use this',
    which is the number a city acts on.
    """
    grants, _ = graph_join.join_graph_exports(
        _sps(SP_CHATGPT),
        _grants(
            {"clientId": "sp-1", "consentType": "Principal", "principalId": "u1", "scope": "User.Read"},
            {"clientId": "sp-1", "consentType": "Principal", "principalId": "u1", "scope": "Mail.Read"},
            {"clientId": "sp-1", "consentType": "Principal", "principalId": "u2", "scope": "User.Read"},
        ),
    )
    assert grants[0]["user_count"] == 2
    assert grants[0]["scopes"] == ["Mail.Read", "User.Read"]


def test_tenant_wide_admin_consent_is_detected():
    """consentType 'AllPrincipals' = an admin consented for everyone, so no employee did.

    It is also not a per-user consent, so it must not inflate the user count.
    """
    grants, _ = graph_join.join_graph_exports(
        _sps(SP_FIREFLIES),
        _grants({"clientId": "sp-2", "consentType": "AllPrincipals",
                 "scope": "Calendars.ReadWrite Mail.Read"}),
    )
    assert grants[0]["tenant_wide_admin_consent"] is True
    assert grants[0]["user_count"] == 0


def test_identities_are_never_returned():
    """principalIds are counted, never emitted. There is no opt-in on this path.

    The browser route has no legitimate need for identities, and the narrower surface is
    the safer one.
    """
    grants, _ = graph_join.join_graph_exports(
        _sps(SP_CHATGPT),
        _grants({"clientId": "sp-1", "consentType": "Principal",
                 "principalId": "alice-object-id", "scope": "User.Read"}),
    )
    assert "alice-object-id" not in json.dumps(grants)
    assert "principalId" not in json.dumps(grants)


# ── Completeness: the dangerous failure ──────────────────────────────────────

def test_paging_is_surfaced_because_a_partial_export_looks_clean():
    """Graph Explorer returns ONE page and an @odata.nextLink.

    An admin who saves only the first page uploads a truncated tenant. For a compliance
    product that is the worst failure mode available: it does not error, it reports a
    short list confidently, and the city concludes they are cleaner than they are.
    """
    paged = _sps(SP_CHATGPT)
    paged["@odata.nextLink"] = "https://graph.microsoft.com/v1.0/servicePrincipals?$skiptoken=X"
    assert graph_join.is_paged(paged) is True
    _, meta = graph_join.join_graph_exports(paged, _grants())
    assert meta["service_principals_paged"] is True


def test_grant_referencing_an_unknown_app_is_counted_not_silently_dropped():
    """Almost always means only the first page of applications was downloaded.

    The script skips such grants too (it cannot name the app), but here the count is the
    signal that the upload is incomplete, so it must reach the caller.
    """
    _, meta = graph_join.join_graph_exports(
        _sps(SP_CHATGPT),
        _grants({"clientId": "sp-NOT-IN-FILE", "consentType": "Principal",
                 "principalId": "u1", "scope": "User.Read"}),
    )
    assert meta["grants_without_matching_app"] == 1


# ── Robustness against what an admin might actually upload ───────────────────

@pytest.mark.parametrize("blob", [None, {}, [], {"value": []}, "not json", 42])
def test_malformed_input_does_not_raise(blob):
    """A confused upload must produce an empty result, never a 500."""
    grants, meta = graph_join.join_graph_exports(blob, blob)
    assert grants == []
    assert meta["apps_joined"] == 0


def test_bare_array_without_the_value_wrapper_is_accepted():
    """Some admins paste just the array, or a tool strips the envelope."""
    grants, _ = graph_join.join_graph_exports(
        [SP_CHATGPT],
        [{"clientId": "sp-1", "consentType": "Principal", "principalId": "u1", "scope": "User.Read"}],
    )
    assert len(grants) == 1 and grants[0]["app_name"] == "ChatGPT"


def test_output_feeds_the_existing_normalizer_unchanged():
    """The whole point: both methods converge before any business logic runs."""
    from engine.collectors import oauth
    from engine.collectors.identity import build_tool_index
    from engine import rule_loader

    schema = rule_loader.load_schema()
    grants, _ = graph_join.join_graph_exports(
        _sps(SP_CHATGPT),
        _grants({"clientId": "sp-1", "consentType": "Principal",
                 "principalId": "u1", "scope": "User.Read"}),
    )
    res = oauth.normalize(grants, build_tool_index(schema), "Lewisville",
                          scope_rules=schema.get("OAuth_Scope_Sensitivity", {}))
    assert res["source_meta"]["matched"] == 1
    assert res["assets"][0]["tool_id"] == "openai_chatgpt"
