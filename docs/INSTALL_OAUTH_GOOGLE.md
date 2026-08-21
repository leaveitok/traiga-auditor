# Shadow-AI Discovery — Google Workspace Setup

> **Audience:** the organization's Google Workspace administrator. No developer
> knowledge required.
> **Time:** about 5 minutes.
> **What this does:** produces a CSV listing the third-party apps your users have
> granted OAuth access to, so you can see which of them are AI.

## What this does NOT do — read this first

- It does **not** install any software. There is **no script to run**.
- It does **not** create anything or change anything in your tenant.
- It uses **Google's own Admin console** export. You download a CSV and decide whether
  to upload it, after reading it.
- The export records **how many** users granted each app and **what scopes** it holds —
  **not who**. No employee identities leave your environment.

---

## Step 1 — Check your role

You need **Super Admin**, or an admin role that includes the **API controls** privilege.
Read-only is sufficient — you never need to change any setting.

## Step 2 — Open the app access list

In the Google Admin console (admin.google.com), go to:

> **Security → Access and data control → API controls → App access control**

Click **Manage App Access**, then open the **Accessed apps** tab.

**Use "Accessed apps," not "Configured apps."** *Accessed apps* is the list of apps your
users have actually consented to — the real OAuth grants. *Configured apps* is only the
apps an admin has explicitly marked Trusted/Limited/Blocked, which is a much shorter and
different list.

## Step 3 — Download the list

At the top of the **Accessed apps** list, click **Download list** and save the CSV.

Each row contains: the app name, its client ID, the number of users who granted it, the
OAuth scopes it holds, verification status, and ownership. That is the entire contents —
there are no employee identities in the file.

## Step 4 — Read the file before you send it

Open the CSV. Every application appears as a plain row: app name, client ID, a user
count, and the Google API scopes it was granted (e.g. Drive, Gmail, Calendar). Nothing
else leaves your environment.

## Step 5 — Upload it (dry run first)

In TRAIGA Auditor: **AI Inventory → OAUTH → Google Workspace**, choose your **city**, and
upload the CSV with **Dry run** left ON.

A dry run **reports what it found and writes nothing**. You see exactly which apps would
be added to your inventory, and what each one can reach. Only when you are satisfied do
you re-run with Dry run off to record them.

## Step 6 — Verify us in your own logs

You do not have to take our word for "read-only." Nothing here touches your tenant beyond
the Admin console export you performed yourself. TRAIGA Auditor never connects to your
Google tenant — it only reads the file you upload.

---

## What you get back

Each discovered app is added to the AI inventory as **Procured · verify** — meaning it was
found in a consent record, not observed running on your public website — with:

- **where it came from** (Google OAuth consent), and
- **what the consent can reach** — e.g. *"file/document contents; mailbox contents"* —
  derived from the granted scopes.

We report what the grant **can reach**. We do not compute a risk score, because a number
nobody can cross-examine is worth less to your attorney than a cited fact.

## Revoking a grant (you do this, not us)

TRAIGA Auditor is a read-only observer and never revokes anything. To remove a consent:
in the Admin console, **Security → API controls → App access control**, select the app,
and change its access to **Blocked** (or **Restricted**), or have the user revoke it from
their own account's security page.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| No **Download list** button | You are on the wrong list | Open the **Accessed apps** tab (not Configured apps) |
| "This does not look like a Google export" | A different CSV was uploaded | Re-download using **Download list** on the Accessed apps page |
| Export has very few apps | You downloaded **Configured apps** | Use **Accessed apps** — the real consents |
| Matched 0 | No city selected | Choose a specific city before uploading |
