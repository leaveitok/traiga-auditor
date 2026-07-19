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

This is Microsoft's own module, published and signed by Microsoft — not our code:

```powershell
Install-Module Microsoft.Graph -Scope CurrentUser
```

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

## Step 5 — Run it

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

## Step 6 — Read the file before you send it

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

## Step 7 — Upload it (dry run first)

In TRAIGA Auditor: **AI Inventory → Discover OAuth**, choose your city, and upload the file
with **Dry run** left ON.

A dry run **reports what it found and writes nothing**. You see exactly which apps would be
added to your inventory, and what each one can reach. Only when you are satisfied do you
re-run with Dry run off to record them.

## Step 8 — Verify us in your own logs

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
