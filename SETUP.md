# AI Transparency Auditor v2 — Setup Guide

**Stack:** Vue 3 + Vuetify · FastAPI · Google Sheets API · Firebase Hosting

---

## Prerequisites

- Python 3.11+
- Node.js 20+
- A Google account with access to Google Cloud Console
- Firebase CLI (`npm install -g firebase-tools`)

---

## Step 1 — Google Cloud: Create Service Account + Enable Sheets API

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable the **Google Sheets API**: APIs & Services → Library → search "Sheets"
4. Create a Service Account: IAM & Admin → Service Accounts → Create
   - Role: Editor (or a custom role with Sheets read/write)
5. Download the JSON key: Actions → Manage keys → Add key → JSON
6. Save the file as `backend/service_account.json`

---

## Step 2 — Google Sheets: Create the Spreadsheet

1. Create a new Google Spreadsheet
2. Copy the **Spreadsheet ID** from the URL:
   `https://docs.google.com/spreadsheets/d/**<SPREADSHEET_ID>**/edit`
3. Create **4 tabs** with these exact names:
   - `Targets`
   - `Scorecard`
   - `Violations`
   - `AuditLog`
4. Share the spreadsheet with the service account email (found in the JSON key file)
   - Permission level: **Editor**

---

## Step 3 — Backend Setup

```bash
cd backend

# Copy and fill in environment variables
cp .env.example .env
# Edit .env: set SPREADSHEET_ID and verify GOOGLE_SERVICE_ACCOUNT_FILE path

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browser (for live crawling)
playwright install chromium

# Start the API
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.
Interactive docs at `http://localhost:8000/api/docs`.

On first startup, the backend automatically writes header rows to all 4 Sheets tabs.

---

## Step 4 — Frontend Setup

```bash
cd frontend

# Install Node dependencies
npm install

# Start the Vue dev server (proxies /api to localhost:8000)
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## Step 5 — Run Your First Audit

1. Open the app at `http://localhost:5173`
2. Go to **Target Registry** and verify the City of Lewisville is listed
   (seeded from `backend/data/target_registry.json` — add more cities here)
3. Click **Run Audit** on the Dashboard
4. Choose **Demo** for an offline test, or **Live** to crawl actual sites
5. Results appear in the Scorecard and Violations tabs and are written to Google Sheets

---

## Step 6 — Deploy to Firebase Hosting

```bash
# Build the Vue app
cd frontend
npm run build
# Output goes to ../dist/

# From the project root
cd ..
firebase login
firebase use --add        # select your Firebase project
# Update .firebaserc with your project ID

firebase deploy --only hosting
```

For the **backend**, deploy to Google Cloud Run (recommended) or any server:

```bash
cd backend
gcloud run deploy ai-transparency-auditor-api \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars SPREADSHEET_ID=<your_id>,GOOGLE_SERVICE_ACCOUNT_FILE=/secrets/sa.json
```

Update `firebase.json` → `hosting.rewrites[0].run.serviceId` to match your Cloud Run service name.
Also update `CORS_ORIGINS` in your backend `.env` to include your Firebase domain.

---

## Google Sheets Schema Reference

| Tab | Key Column | Description |
|---|---|---|
| Targets | `id` | Municipal domains to scan; `active=false` disables a target |
| Scorecard | `city` | One row per city; upserted on every scan |
| Violations | `violation_id` | One row per unique violation; cure-period countdown |
| AuditLog | `timestamp_utc` | Append-only scan summary and failure events |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/targets` | List active targets |
| POST | `/api/targets` | Add a target |
| DELETE | `/api/targets/{id}` | Deactivate a target |
| POST | `/api/audit/run?demo=false` | Trigger audit (background) |
| GET | `/api/audit/run` | Poll audit status |
| GET | `/api/scorecard` | Full scorecard rows |
| GET | `/api/scorecard/summary` | KPI summary counts |
| GET | `/api/violations` | All violations (filterable by ?status=in_cure) |
| GET | `/api/violations/{id}` | Single violation detail |
| GET | `/api/logs` | Audit log entries |

Full interactive docs: `/api/docs`

---

## Extending to New States / Frameworks

The rule engine is **governance-as-code**: add new modules to `backend/SCHEMA_DEFINITION.json`
under `compliance_modules` without touching Python. Supported module types:
- `External_Transparency_Module` (current — TRAIGA HB 149)
- `Internal_Governance_Module` (reserved)
- NIST AI RMF, ISO 42001 (planned)

---

## Legal Notice

Findings are candidate compliance signals from externally observable evidence.
They require human and legal review. Not legal advice. Confirm all statutory
citations against the enrolled HB 149 text before any enforcement-grade use.
