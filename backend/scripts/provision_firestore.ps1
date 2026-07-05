# =============================================================================
# provision_firestore.ps1 — ONE-TIME Firestore provisioning for traiga-auditor
#
# Run on Windows with project-owner rights BEFORE pushing the Firestore
# migration commit (the deploy flips GOVERNANCE_STORE/SENTINEL_STORE to
# "firestore"; these databases must exist first).
#
# What it does:
#   1. Enables the Firestore API.
#   2. Creates the "(default)" database (dashboard data) if missing.
#      NOTE: "(default)" is the ONLY database covered by the Firestore free tier.
#   3. Creates the "traiga-sentinel" named database (Sentinel telemetry) if
#      missing — SEPARATE dataset by design (employee-monitoring metadata).
#   4. Grants the backend service account roles/datastore.user.
#
# Rollback of the app is env-var only (GOVERNANCE_STORE/SENTINEL_STORE=sheets);
# these databases can sit empty at zero cost if you roll back.
# =============================================================================

$ErrorActionPreference = "Stop"
$PROJECT = "traiga-auditor"
$LOCATION = "us-central1"   # same region as Cloud Run — lowest latency

# Backend SA = the identity in the mounted service_account.json.
# Auto-read client_email from Secret Manager so we grant the right principal:
$SA = (gcloud secrets versions access latest --secret=traiga-service-account --project=$PROJECT | ConvertFrom-Json).client_email
Write-Host "Backend service account: $SA"
if (-not $SA) { throw "Could not read client_email from secret traiga-service-account" }

Write-Host "`n[1/4] Enabling Firestore API..."
gcloud services enable firestore.googleapis.com --project=$PROJECT

Write-Host "`n[2/4] Ensuring (default) database exists..."
gcloud firestore databases describe --database="(default)" --project=$PROJECT 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud firestore databases create --database="(default)" --location=$LOCATION --type=firestore-native --project=$PROJECT
} else { Write-Host "  (default) already exists - skipping" }

Write-Host "`n[3/4] Ensuring traiga-sentinel database exists..."
gcloud firestore databases describe --database="traiga-sentinel" --project=$PROJECT 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud firestore databases create --database="traiga-sentinel" --location=$LOCATION --type=firestore-native --project=$PROJECT
} else { Write-Host "  traiga-sentinel already exists - skipping" }

Write-Host "`n[4/4] Granting roles/datastore.user to backend SA..."
gcloud projects add-iam-policy-binding $PROJECT `
    --member="serviceAccount:$SA" `
    --role="roles/datastore.user" `
    --condition=None --quiet | Out-Null

Write-Host "`nDone. Verify:"
gcloud firestore databases list --project=$PROJECT --format="table(name,type,locationId)"
Write-Host "`nNext: git push the migration commit - CI deploys with GOVERNANCE_STORE/SENTINEL_STORE=firestore."
