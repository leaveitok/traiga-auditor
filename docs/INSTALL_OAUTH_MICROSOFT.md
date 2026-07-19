# Shadow-AI Discovery — Microsoft 365 / Entra ID Setup

> **Audience:** the city's IT administrator. No developer knowledge required.
> **Time:** about 10 minutes.
> **What this does:** produces a file listing the third-party apps your staff have
> consented to, so you can see which of them are AI.

## What this does NOT do — read this first

- It does **not** install any software from us. It is a **script** you run and can read.
- It does **not** create an app registration, a client secret, or any standing access.
- It does **not** write, change, or delete anything in your tenant.
- It does **not** send anything anywhere. It writes a file to **your** disk. You decide
  whether to upload it, after reading it.
- By default it records **how many** users consented to each app, **not who**.

You sign in as yourself. The access token exists only for that PowerShell session and is
gone when you close the window. **There is nothing to revoke afterwards.**

---

## Step 1 — Check your role

You need a role that can **read** directory objects. **Global Reader** is sufficient and is
read-only. (Global Administrator also works, but is not required — please use Global Reader.)

## Step 2 — Install Microsoft's PowerShell module

> **Method A only.** If you intend to use Method B (browser), skip this — Method B
> installs nothing. Read the next section first if you are not sure which you need.

This is Microsoft's own module, published and signed by Microsoft — not our code:

```powershell
Install-Module Microsoft.Graph -Scope CurrentUser
```

## Two ways to do this — pick one

| | **Method A — run the script** | **Method B — no software runs at all** |
|---|---|---|
| What you run | A PowerShell script on your machine | Two read-only queries in your browser |
| Needs | PowerShell + Microsoft's Graph module | Only a browser and your admin sign-in |
| Best when | Your workstation permits PowerShell | **Endpoint protection, AppLocker, WDAC or Constrained Language Mode blocks scripts** |
| Effort | One command | Two queries, two downloads |

**If your endpoint protection blocks PowerShell, skip to Method B (Step 7).** That is a
normal control and we are not going to ask you to weaken it — a wrapper that bypasses
execution policy is the same behaviour security teams block malware for, so we do not
ship one. Method B runs nothing on your endpoint at all.

Both methods produce the same result in the dashboard.

---

# Method A — run the script

## Step 3 — Get the script and verify it

**Download it from the dashboard**, not from an email or an attachment:

> **AI Inventory → OAuth → Download script**

The dashboard is the only place you should ever get this file. It always serves the
version that matches the running system, so the script and the service that reads its
output can never fall out of step — and you never have to wonder whether the copy someone
sent you is current.

**Verify you received the file we published.** It is not Authenticode-signed — we do not
hold a code-signing certificate, so we publish a checksum instead. The SHA-256 is shown
next to the download button, with a copy control. Compare it to the file you saved:

```powershell
Get-FileHash .\Export-EntraOAuthGrants.ps1 -Algorithm SHA256
```

The checksum on screen is **computed from the exact file being served**, not typed into a
document, so it cannot drift out of date. If the two values differ, stop and tell us — do
not run the file.

A note on what this does and does not prove: the checksum confirms that the file you saved
is the file we served, so it catches corruption or truncation in transit. It is not, by
itself, proof of our trustworthiness. That is what Step 4 is for — reading the script, and
checking your own Entra audit logs afterwards.

## Step 4 — Read it before you run it

**Open it in a text editor and read it.** It is deliberately plain text. You will see
it requests only these two read scopes, and calls only `Get-` (read) cmdlets:

- `Application.Read.All` — read the list of enterprise applications
- `Directory.Read.All` — read the delegated permission grants (the consents)

The write versions of these permissions (`*.ReadWrite.All`) are **never requested**, so
Entra itself will refuse any write attempt regardless of what the script does.

## Step 5 — Unblock the file (Windows will block it otherwise)

**Do not skip this. It is the most common reason the script appears not to work.**

Windows attaches a hidden "downloaded from the internet" marker to any file saved from a
browser, and PowerShell refuses to run marked scripts. The error mentions the execution
policy, or a security warning appears asking you to confirm.

Clear the marker:

```powershell
Unblock-File .\Export-EntraOAuthGrants.ps1
```

That removes the download marker from **this one file**. It does not change any policy on
your machine and it does not affect any other script.

If your organisation's execution policy still blocks it, run it for this session only —
this affects only the current PowerShell window and reverts when you close it:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

**If either of these is prohibited by your policy, stop here and use Method B (Step 7)
instead.** Do not disable a control to run our tool. We would rather you took the path
that runs nothing.

Two other things worth knowing before you run it:

- **PowerShell version.** Either Windows PowerShell 5.1 or PowerShell 7 works.
- **Endpoint protection.** Some products quarantine any downloaded `.ps1` regardless of
  the marker. If the file disappears, that is what happened — use Method B.

## Step 6 — Run it

```powershell
.\Export-EntraOAuthGrants.ps1
```

A Microsoft sign-in window appears. Sign in as yourself and approve the **read** permissions.
The script then writes a file such as:

```
oauth-grants-<your-tenant-id>-<date>.json
```

If you specifically want the user identities in order to go revoke a grant, add
`-IncludeUsers`. **This makes the file employee-identifiable — handle it accordingly.**

---

# Method B — no software runs on your machine

Use this if endpoint protection, AppLocker, WDAC or Constrained Language Mode prevents you
running scripts — or if you would simply rather not run one. Everything here happens in
Microsoft's own website, signed in as yourself. Nothing is installed and nothing executes
on your endpoint.

## Step 7 — Open Microsoft Graph Explorer

Go to **<https://developer.microsoft.com/graph/graph-explorer>** and sign in with your
admin account. This is Microsoft's own tool, not ours.

## Step 8 — Run the first query and download the result

Paste this into the query bar, leave the method as **GET**, and press **Run query**:

```
https://graph.microsoft.com/v1.0/servicePrincipals?$select=id,appId,displayName,publisherName,signInAudience&$top=999
```

If prompted, consent to the read permission. Then use the **download / save** control on
the response panel to save the JSON. Call it `servicePrincipals.json`.

## Step 9 — Run the second query and download that too

```
https://graph.microsoft.com/v1.0/oauth2PermissionGrants?$top=999
```

Save it as `oauth2PermissionGrants.json`.

### If you see `@odata.nextLink` in the response

That means your tenant has more results than one page. **The download you just saved is
incomplete**, and an incomplete file makes a tenant look cleaner than it is — the worst
kind of wrong answer for a compliance tool.

Copy the `@odata.nextLink` URL, run it as the next query, and save that page too. Repeat
until no `nextLink` appears. Upload every page. The dashboard will also warn you if it
detects a partial file, but do not rely on that as your only check.

## Step 10 — Upload both files

In the dashboard, **AI Inventory → OAuth**, choose **Graph Explorer files** and select
both downloads. Order does not matter — the system identifies each file by its contents.

The join between the two files happens on our server, exactly as the script would have
done it locally, so both methods produce identical results.

---

# Both methods — finishing up

## Step 11 — Read the file before you send it

Open the JSON. Every application appears as a plain record:

```json
{
  "app_id": "…",
  "app_name": "Some AI Notetaker",
  "publisher": "…",
  "provider": "microsoft",
  "scopes": ["openid", "Mail.Read", "Files.Read.All"],
  "user_count": 7
}
```

That is the entire contents. Nothing else leaves your environment.

## Step 12 — Upload it (dry run first)

In TRAIGA Auditor: **AI Inventory → OAuth**, choose your city, and upload with **Dry run**
left ON — the single file from Method A, or both files from Method B.

A dry run **reports what it found and writes nothing**. You see exactly which apps would be
added to your inventory, and what each one can reach. Only when you are satisfied do you
re-run with Dry run off to record them.

## Step 13 — Verify us in your own logs

You do not have to take our word for "read-only." Every call the script made appears in
**Entra admin center → Monitoring → Audit logs / Sign-in logs** under your own account. You
will see reads and no writes.

---

## What you get back

Each discovered app is added to the AI inventory as **Procured · verify** — meaning it was
found in a record, not observed running on your public website — with:

- **where it came from** (OAuth consent), and
- **what the consent can reach** — e.g. *"mailbox contents; file/document contents"* —
  derived from the granted scopes.

We report what the grant **can reach**. We do not compute a risk score, because a number
nobody can cross-examine is worth less to your attorney than a cited fact.

## Revoking a grant (you do this, not us)

TRAIGA Auditor is a read-only observer and never revokes anything. To remove a consent:
**Entra admin center → Enterprise applications →** select the app **→ Permissions →** review
and revoke, or delete the enterprise application.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Microsoft.Graph module not found` | Module not installed | Step 2 |
| Sign-in fails or consent prompt is blocked | Your tenant restricts who may consent | Ask a Global Administrator to run it, or to grant admin consent for the two read scopes |
| `Insufficient privileges` | Role lacks directory read | Use Global Reader |
| Hash does not match | You did not get the published file | Re-download; do not run it |
| Export has 0 grants | No third-party app consents exist | This is a valid result — it means nothing to report |
