# =============================================================================
# deploy.ps1 — Full deployment for AI Transparency Auditor v2 (Windows)
# Run from PowerShell:
#   cd "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"
#   powershell -ExecutionPolicy Bypass -File deploy\deploy.ps1
# =============================================================================

$ErrorActionPreference = "Stop"

# ── Config ────────────────────────────────────────────────────────────────────
$PROJECT_ID   = "traiga-auditor"
$REGION       = "us-central1"
$SERVICE_NAME = "ai-transparency-auditor-api"
$IMAGE_REPO   = "ai-transparency-auditor"
$IMAGE_NAME   = "api"
$SECRET_NAME  = "traiga-service-account"
$IMAGE_URI    = "$REGION-docker.pkg.dev/$PROJECT_ID/$IMAGE_REPO/$IMAGE_NAME`:latest"

$ROOT_DIR     = Split-Path -Parent $PSScriptRoot
$BACKEND_DIR  = Join-Path $ROOT_DIR "backend"
$FRONTEND_DIR = Join-Path $ROOT_DIR "frontend"
$ENV_FILE     = Join-Path $PSScriptRoot "env.yaml"
$SA_FILE      = Join-Path $BACKEND_DIR "service_account.json"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  AI Transparency Auditor v2 - Deployment" -ForegroundColor Cyan
Write-Host "  Project : $PROJECT_ID" -ForegroundColor Cyan
Write-Host "  Region  : $REGION" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 0: Set GCP project ───────────────────────────────────────────────────
Write-Host "[0/5] Setting GCP project..." -ForegroundColor Yellow
gcloud config set project $PROJECT_ID

# ── Step 1: Enable APIs ───────────────────────────────────────────────────────
Write-Host "[1/5] Enabling required GCP APIs..." -ForegroundColor Yellow
gcloud services enable `
  run.googleapis.com `
  artifactregistry.googleapis.com `
  secretmanager.googleapis.com `
  cloudbuild.googleapis.com `
  --quiet

# ── Step 2: Upload service account to Secret Manager ─────────────────────────
Write-Host "[2/5] Uploading service account to Secret Manager..." -ForegroundColor Yellow

if (-not (Test-Path $SA_FILE)) {
    Write-Host "ERROR: service_account.json not found at $SA_FILE" -ForegroundColor Red
    exit 1
}

$secretExists = gcloud secrets describe $SECRET_NAME --project=$PROJECT_ID 2>$null
if (-not $secretExists) {
    Write-Host "  Creating secret: $SECRET_NAME"
    gcloud secrets create $SECRET_NAME --replication-policy="automatic" --project=$PROJECT_ID
}

gcloud secrets versions add $SECRET_NAME --data-file="$SA_FILE" --project=$PROJECT_ID
Write-Host "  Secret uploaded OK." -ForegroundColor Green

# Grant Cloud Run service account access
$PROJECT_NUMBER = gcloud projects describe $PROJECT_ID --format="value(projectNumber)"
$CR_SA = "$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
gcloud secrets add-iam-policy-binding $SECRET_NAME `
  --member="serviceAccount:$CR_SA" `
  --role="roles/secretmanager.secretAccessor" `
  --project=$PROJECT_ID --quiet

# ── Step 3: Build Docker image ────────────────────────────────────────────────
Write-Host "[3/5] Building Docker image via Cloud Build..." -ForegroundColor Yellow

$repoExists = gcloud artifacts repositories describe $IMAGE_REPO --location=$REGION --project=$PROJECT_ID 2>$null
if (-not $repoExists) {
    Write-Host "  Creating Artifact Registry repo: $IMAGE_REPO"
    gcloud artifacts repositories create $IMAGE_REPO `
      --repository-format=docker `
      --location=$REGION `
      --project=$PROJECT_ID --quiet
}

gcloud builds submit "$BACKEND_DIR" `
  --tag="$IMAGE_URI" `
  --project=$PROJECT_ID `
  --timeout=20m

Write-Host "  Image pushed: $IMAGE_URI" -ForegroundColor Green

# ── Step 4: Deploy to Cloud Run ───────────────────────────────────────────────
Write-Host "[4/5] Deploying to Cloud Run..." -ForegroundColor Yellow

if (-not (Test-Path $ENV_FILE)) {
    Write-Host "ERROR: env.yaml not found at $ENV_FILE" -ForegroundColor Red
    exit 1
}

gcloud run deploy $SERVICE_NAME `
  --image="$IMAGE_URI" `
  --region=$REGION `
  --platform=managed `
  --no-allow-unauthenticated `
  --env-vars-file="$ENV_FILE" `
  --set-secrets="/secrets/service_account.json=${SECRET_NAME}:latest" `
  --memory=2Gi `
  --cpu=1 `
  --min-instances=0 `
  --max-instances=3 `
  --timeout=300 `
  --concurrency=80 `
  --project=$PROJECT_ID `
  --quiet

# Allow Firebase Hosting proxy to invoke Cloud Run
gcloud run services add-iam-policy-binding $SERVICE_NAME `
  --region=$REGION `
  --member="allUsers" `
  --role="roles/run.invoker" `
  --project=$PROJECT_ID --quiet

Write-Host "  Cloud Run deploy OK." -ForegroundColor Green

# ── Step 5: Build and deploy frontend ─────────────────────────────────────────
Write-Host "[5/5] Building and deploying frontend..." -ForegroundColor Yellow

Set-Location $FRONTEND_DIR
npm ci --silent
npm run build

Set-Location $ROOT_DIR
firebase deploy --only hosting --project=$PROJECT_ID

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  DEPLOYMENT COMPLETE" -ForegroundColor Green
Write-Host ""
Write-Host "  App URL : https://$PROJECT_ID.web.app" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
