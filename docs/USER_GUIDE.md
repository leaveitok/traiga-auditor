---
title: "TRAIGA Auditor — User Guide"
subtitle: "AI Transparency & Compliance for Texas Municipalities · Version 1.2"
date: "July 18, 2026 · For City IT, CIO, and Compliance Staff"
---

# About TRAIGA Auditor

TRAIGA Auditor helps a city find the AI systems on its public digital services, check whether they meet the disclosure requirements of the **Texas Responsible Artificial Intelligence Governance Act (TRAIGA / House Bill 149, Tex. Bus. & Com. Code Ch. 552)**, and build the governance record that supports the law's safe-harbor defenses.

The platform does three things:

- **Discovers** AI systems (chatbots, virtual assistants, digital-human avatars) running on a city's website, including vendor-embedded tools the city may not know it has.
- **Assesses** each one for the state-required "you are interacting with AI" disclosure, and tracks any gap on the statutory 60-day cure clock.
- **Documents** the city's AI governance against a NIST-aligned readiness profile, producing council- and counsel-ready reports.

**Who this guide is for:** city IT staff, CIOs, and compliance or legal team members who use the platform day to day.

> **Important — please read.** TRAIGA Auditor produces **candidate compliance signals** derived from externally observable evidence. They are **not** enforcement determinations and **do not** constitute legal advice. Every finding requires human and legal review before any action. Statutory citations reference Texas HB 149 / Ch. 552; re-validate against the enrolled bill with counsel. The scanner is an out-of-line observer — it never modifies or disrupts a target system.

# Getting Started

## Signing in and roles

Sign in with your Google account. What you can do depends on your role:

| Role | What they can do |
|---|---|
| **Viewer** | Read dashboards, scorecards, findings, and reports for their assigned cities. |
| **Agency Admin** | Everything a Viewer can, plus attest governance controls for their cities. |
| **Platform Admin** | Full access: add/import/edit cities, run scans, change Settings and feature flags, and manage the platform. |

## Finding your way around

The left-hand menu is your map:

- **Dashboard** — your compliance at a glance.
- **Analytics** — trends and summaries.
- **AI Inventory** — every AI system discovered or declared, across cities.
- **Violations** — open disclosure gaps and their cure clocks.
- **Sentinel (DLP)** — visibility into staff AI usage (optional module).
- **Target Registry** — the list of cities you monitor.
- **Audit Log / Error Log** — the evidence trail and operational failures.
- **Administration / Settings** — users, feature flags, and configuration.

**Light or Stealth theme:** the sun/moon toggle by your name (bottom-left) switches between the standard light theme and a darker "Stealth" theme. Your choice is saved in your browser.

**On a phone or tablet:** the menu is hidden to give the content the full screen. Tap the **☰ menu button** in the top bar to open it, then tap where you want to go — the menu closes itself. Wide tables reshape into stacked cards so you can read them without scrolling sideways. On a laptop or desktop the menu stays open on the left as usual.

# The Dashboard

The Dashboard is your one-screen view of compliance across every city you monitor.

**Status tiles** across the top count your cities by state: Total Cities, Compliant, In Cure, Non-Compliant, Expired, No AI Detected, Scan Failed, and an overall Average Score.

**Texas Compliance Map** plots mapped cities colored by status.

**Cure Deadlines** lists cities with open violations, worst-first, showing the days remaining in each 60-day cure window — your triage list.

**City Compliance Scorecard** is the detailed table: City, Jurisdiction, Population, TRAIGA Status, Score, Open Violations, Min Days Left, Scan Type, and Last Scanned. Click a city name to open its detail page, or **Report** to generate its compliance report.

Two action buttons sit at the top: **Add City** and **Run Audit** (scan all active cities).

# Managing Your Cities (Target Registry)

The Target Registry is the list of city websites you monitor.

## Add a single city

Click **Add Target**, enter the city name, jurisdiction (e.g., TX), the domain (starting with `https://`), and optionally tags and population. Leave "Scan immediately" on to get results right away, or off to add it quietly.

## Bulk import many cities

Click **Bulk Import** (platform admin) and upload a CSV with at least `city` and `domain` columns (optional: `url, jurisdiction, tags, cloudflare_protected, population`). Imported cities are added as **Not Assessed** and are **not scanned automatically** — you run a scan when ready. Duplicate cities and domains are skipped automatically.

## Edit or remove a city

The **pencil** icon opens an edit dialog for a city's name, jurisdiction, domain, seed URL, tags, population, and its WAF flag. Every change is written to the Audit Log. The **trash** icon deactivates a city (it stops future scans but keeps the record).

## The Scan Type indicator

The **Scan Type** column shows how a city was reached: **Direct** (a normal crawl) or **Proxy** (a residential proxy was used because the site is protected by a web application firewall). This tells you whether a city needed the heavier scan path.

# Running Scans

Scanning is always a deliberate action (it uses paid resources), so newly added or imported cities stay **Not Assessed** until you scan them.

- **Run Audit** (Dashboard) scans every active city.
- **Re-Audit** or **Deep Scan** (on a city's detail page) scans just that city.

If a city's site blocks ordinary scanners, the platform **automatically escalates**: a direct crawl → a residential-proxy fetch → a server-side rendered fetch for the hardest, JavaScript-challenge firewalls. A small number of top-tier-protected sites may still return **Scan Failed** — an honest "we couldn't safely read the page," never a false "all clear."

## What the statuses mean

| Status | Meaning |
|---|---|
| **Not Assessed** | Added but not yet scanned. |
| **No AI Detected** | Scanned; no AI system found on the public site. |
| **In Cure** | AI found with a disclosure gap; inside the 60-day cure window. |
| **Non-Compliant** | A gap that is not (or no longer) in an open cure window. |
| **Expired** | The 60-day cure window elapsed without remediation. |
| **Review Needed** | A candidate AI system was found that needs human review. |
| **Scan Failed** | The site could not be safely read (e.g., a strong firewall). |

# Reading a City's Results

Click a city to open its detail page.

- **AI Assets Detected** lists each AI system found, its vendor, the confidence, and whether it is a confirmed candidate awaiting review.
- **Violations & Cure Period** lists each disclosure gap with its statutory citation and days remaining.
- **Cure Period Summary** shows the tightest deadline, the cure date, and the statutory basis.
- **Violation Breakdown** counts findings by severity and how many need review.

Every city page repeats the reminder that findings are candidate signals requiring human and legal review.

# The 60-Day Cure Clock

TRAIGA gives a 60-day window to fix a disclosure gap. Two things are important to understand:

- **The clock starts when the violation is first detected — not when the city was added or last scanned.** A city added months ago but first flagged today correctly shows 60 days.
- **The countdown is live.** It ticks down every day toward the cure deadline and does not reset when you re-scan. A gap left uncured past the deadline becomes **Expired** and is referable to the Texas Attorney General.

# Getting & Proving Compliance

The city detail page includes tools to move from "problem found" to "fixed and documented":

- **AI Use-Case Inventory** — declare AI systems your team uses, assign owners, and attest details. Each entry shows **where it came from** and whether it is actually running (see below).
- **Compliance Report** — generate a formal report (executive summary, inventory, and violations with citations) for council or counsel.
- **AI Use Policy** — generate a draft municipal AI use policy.
- **AG Response Pack** — assemble documentation responsive to an Attorney General inquiry.
- **Import Procurement / Sync Staff Usage / Agendas** — additional discovery inputs that widen the inventory beyond the public website.

## Knowing where an AI system came from — and whether it is live

Every row in the AI Use-Case Inventory carries two labels, and the difference matters:

**Where it was found** — *Website scan*, *Council agenda*, *Procurement*, *Budget*, *Staff usage*, or *Declared* (entered by your team).

**Whether it is deployed:**

- **Live on site** — the scanner observed it running on your public website. This is a real disclosure obligation right now.
- **Procured · verify** / **Budgeted · verify** — it was found in a contract, agenda, or budget record. The city has *bought or planned* it; that does **not** mean it is switched on yet. Confirm whether it is actually deployed before treating it as a live disclosure obligation.
- **Staff-reported** — seen in staff browser usage (Sentinel).
- **Self-declared** — your team entered it.

This distinction protects you from a false alarm: a tool approved in a January agenda but not launched until June is not a disclosure violation in February. Findings from records never create a violation or start a cure clock — only what is observed live on your website does.

## Discovering AI from council agendas

The **Agendas** tool scans a city's council or EDC meeting agendas for awarded technology contracts and adds any AI it finds to the inventory as *procured (agenda)*. You can point it at a Legistar portal (by client slug), an agenda PDF, or pasted agenda text, and set a date range (12 months by default). **You only need to enter the Legistar slug once per city** — it is remembered (and, where the city's website links its agenda portal, detected automatically), so it is filled in for you next time. Zoning and advisory items are skipped, and every result is a candidate for human review.

When the scan finishes, the result shows how many items were screened and a badge naming **which extractor read them**:

- **Extracted via Vertex (Gemini)** — the AI extractor read every item. A result of zero here is a reliable "no AI contracts found" for that window.
- **Vertex (Gemini) — some items used keyword fallback** — most items were read by the AI extractor, but one or more fell back to the simpler keyword screen.
- **Vertex unavailable — keyword fallback used** — the AI extractor could not run, so a plain keyword screen was used instead; consider re-running once it is available.
- **Keyword extractor (no LLM)** — the AI extractor is turned off in Settings; the keyword screen was used by design.

This badge tells you at a glance whether a "0 found" result means "checked thoroughly and clean" or "only a light check ran" — no server logs required.

# Safe Harbor Readiness & Framework Lenses

At the bottom of each city page, **TRAIGA Safe Harbor Readiness** scores the city's AI governance against the **Municipal AI Profile** — a right-sized profile of the **NIST AI Risk Management Framework** and its Generative AI Profile. This supports the reasonable-care presumption and internal-review defenses under **Tex. Bus. & Com. Code § 552.105(c)–(e)**.

## The four functions

Controls are grouped into the NIST functions — **GOVERN, MAP, MEASURE, MANAGE** — each shown as a ring with a satisfied/total count.

## Machine-verified vs. attested controls

- **Machine-verified** controls are satisfied automatically from platform data (for example, "public-facing AI is actively discovered" is proven by the scanner; "findings are tracked with cure deadlines" by the cure clock). These show a "Machine-verified from platform data" note.
- **Attested** controls are things the platform cannot observe (for example, "an AI use policy is adopted"). An admin marks these satisfied with the **Attest** button, adding evidence notes and a timestamp that appear in generated documentation. Use **Clear** to remove an attestation.

## Framework lenses (NIST / ISO 42001)

When more than one framework is enabled, a **Framework lens** selector appears. Switching it re-labels each control with the selected framework's reference (for example, the ISO/IEC 42001 Annex A objective) and shows an **overlap grade** — *strong*, *partial*, or *weak* — for how closely the control maps. The underlying assessment does not change; only the labels do. This is how one assessment is reported in several frameworks ("assess once, report many"). Crosswalk mappings are a positioning aid, not legal advice.

## Alignment Statement

**Alignment Statement** generates a Word document summarizing the city's readiness for the safe-harbor defense. It requires counsel review — the document says so itself.

# Settings

- **Appearance** — choose the Light or Stealth interface theme (saved per browser).
- **Feature Flags** (platform admin) — operational toggles that apply within seconds and are written to the Audit Log: the agenda-discovery engine, the daily automated scan and its hour, and the ISO/IEC 42001 framework lens.
- **Version & Build** — the deployed backend and frontend build identifiers and environment.
- **Storage / Backend API / Integrations / Deployment** — reference information about the running system.
- **API Health Check** — confirms the app can reach its backend.

# Audit Log & Error Log

- **Audit Log** is the append-only evidence trail: scans, configuration changes, attestations, and administrative actions, each with the acting user and time. This is what makes the platform's record defensible.
- **Error Log** (platform admin) surfaces operational failures across scans, the scheduler, and deep scans, so problems are visible rather than silent.

# Sentinel (DLP)

Sentinel is an optional module that gives the city visibility into staff use of AI tools with city data via lightweight browser telemetry (metadata only). It complements the website scan by covering AI that employees use directly.

# Glossary

| Term | Meaning |
|---|---|
| **TRAIGA / HB 149** | Texas Responsible Artificial Intelligence Governance Act; the state law this platform supports. |
| **Ch. 552** | Tex. Bus. & Com. Code chapter where TRAIGA is codified. |
| **Disclosure** | The required notice that a person is interacting with an AI system. |
| **Cure period** | The 60-day window to fix a disclosure gap before it can be referred to the Attorney General. |
| **Safe harbor** | Legal defenses (§ 552.105) available to a city that exercises reasonable care and internal review. |
| **Candidate signal** | An automated finding that requires human and legal confirmation. |
| **NIST AI RMF** | The U.S. National Institute of Standards and Technology's AI Risk Management Framework; the readiness profile's backbone. |
| **ISO/IEC 42001** | The international standard for AI management systems; an optional framework lens. |
| **WAF** | Web application firewall; site protection that can block ordinary scanners. |
| **Residential / render tier** | Heavier scan paths used to reach firewall-protected sites. |
| **Attestation** | A human record marking a governance control as satisfied, with evidence and a timestamp. |
| **Alignment Statement** | The generated safe-harbor readiness document (requires counsel review). |

# Important Disclaimers

TRAIGA Auditor is a governance and monitoring tool, not a substitute for legal counsel. Findings are candidate compliance signals derived from externally observable evidence and require human and legal review before any enforcement, representation, or public statement. Statutory citations reference Texas HB 149 / Tex. Bus. & Com. Code Ch. 552; re-validate against the enrolled bill. Framework crosswalks (NIST, ISO/IEC 42001, and others) are design and positioning aids and are not legal advice. Generated documents, including the Alignment Statement and Compliance Report, require review by qualified counsel before use.
