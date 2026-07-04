#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Full one-shot deployment for AI Transparency Auditor v2
#
# What this does:
#   1. Uploads service_account.json to Secret Manager (once, idempotent)
#   2. Builds the Docker image via Cloud Build and pushes to Artifact Registry
#   3. Deploys the backend to Cloud Run with env vars + secret mount
#   4. Builds the Vue frontend
#   5. Deploys the frontend to Firebase Hosting
#
# Prerequisites (install once):
#   - gcloud CLI:   https://cloud.google.com/sdk/docs/install
#   - firebase CLI: npm install -g firebase-tools
#   - Node 18+:     https://nodejs.org
#
# First-time setup:
#   gcloud auth login
#   gcloud auth application-default login
#   firebase login
#
# Usage:
#   cd "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"
#   bash deploy/deploy.sh
# =============================================================================

set -euo pipefail

# ── Config — edit these if your project IDs differ ────────────────────────────
PROJECT_ID="traiga-auditor"
REGION="us-central1"
SERVICE_NAME="ai-transparency-auditor-api"
IMAGE_REPO="ai-transparency-auditor"
IMAGE_NAME="api"
SECRET_NAME="traiga-service-account"

# Derived
IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$IMAGE_REPO/$IMAGE_NAME:latest"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

echo ""
echo "============================================================"
echo "  AI Transparency Auditor v2 — Deployment"
echo "  Project : $PROJECT_ID"
echo "  Region  : $REGION"
echo "  Service : $SERVICE_NAME"
echo "============================================================"
echo ""

# ── Step 0: Set active GCP project ───────────────────────────────────────────
echo "[0/5] Setting GCP project..."
gcloud config set project "$PROJECT_ID"

# ── Step 1: Enable required APIs (idempotent) ─────────────────────────────────
echo "[1/5] Enabling required GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  --quiet

# ── Step 2: Upload service account to Secret Manager ─────────────────────────
echo "[2/5] Uploading service account credentials to Secret Manager..."
SA_FILE="$BACKEND_DIR/service_account.json"

if [ ! -f "$SA_FILE" ]; then
  echo "ERROR: $SA_FILE not found. Place your service account JSON there first."
  exit 1
fi

# Create secret if it doesn't exist yet
if ! gcloud secrets describe "$SECRET_NAME" --project="$PROJECT_ID" &>/dev/null; then
  echo "  Creating new secret: $SECRET_NAME"
  gcloud secrets create "$SECRET_NAME" \
    --replication-policy="automatic" \
    --project="$PROJECT_ID"
fi

# Add a new version (latest always wins)
echo "  Uploading new version..."
gcloud secrets versions add "$SECRET_NAME" \
  --data-file="$SA_FILE" \
  --project="$PROJECT_ID"

echo "  Secret uploaded OK."

# Grant Cloud Run service account access to the secret
CR_SA="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"-compute@developer.gserviceaccount.com
gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:$CR_SA" \
  --role="roles/secretmanager.secretAccessor" \
  --project="$PROJECT_ID" \
  --quiet

# ── Step 3: Build and push Docker image via Cloud Build ───────────────────────
echo "[3/5] Building Docker image via Cloud Build..."

# Create Artifact Registry repo if it doesn't exist
if ! gcloud artifacts repositories describe "$IMAGE_REPO" \
     --location="$REGION" --project="$PROJECT_ID" &>/dev/null; then
  echo "  Creating Artifact Registry repo: $IMAGE_REPO"
  gcloud artifacts repositories create "$IMAGE_REPO" \
    --repository-format=docker \
    --location="$REGION" \
    --project="$PROJECT_ID" \
    --quiet
fi

# Submit build (runs in Cloud Build, no local Docker required)
gcloud builds submit "$BACKEND_DIR" \
  --tag="$IMAGE_URI" \
  --project="$PROJECT_ID" \
  --timeout=20m

echo "  Image pushed: $IMAGE_URI"

# ── Step 4: Deploy to Cloud Run ───────────────────────────────────────────────
echo "[4/5] Deploying to Cloud Run..."

# Load env vars from deploy/env.yaml
ENV_FILE="$SCRIPT_DIR/env.yaml"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found. Copy deploy/env.yaml.example to deploy/env.yaml and fill in your values."
  exit 1
fi

gcloud run deploy "$SERVICE_NAME" \
  --image="$IMAGE_URI" \
  --region="$REGION" \
  --platform=managed \
  --no-allow-unauthenticated \
  --env-vars-file="$ENV_FILE" \
  --set-secrets="/secrets/service_account.json=${SECRET_NAME}:latest" \
  --memory=2Gi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --timeout=300 \
  --concurrency=80 \
  --project="$PROJECT_ID" \
  --quiet

echo "  Cloud Run deploy OK."

# Allow Firebase Hosting to invoke Cloud Run (unauthenticated via proxy)
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --region="$REGION" \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --project="$PROJECT_ID" \
  --quiet

# ── Step 5: Build and deploy frontend ─────────────────────────────────────────
echo "[5/5] Building and deploying frontend..."

cd "$FRONTEND_DIR"
npm ci --silent
npm run build

cd "$ROOT_DIR"
firebase deploy --only hosting --project="$PROJECT_ID"

echo ""
echo "============================================================"
echo "  DEPLOYMENT COMPLETE"
echo ""
echo "  App URL : https://$PROJECT_ID.web.app"
echo "  API docs: (Cloud Run is proxied — no direct URL needed)"
echo ""
echo "  Next steps:"
echo "  1. Open https://$PROJECT_ID.web.app and sign in"
echo "  2. Trigger an audit to verify Sheets connectivity"
echo "  3. Download a Compliance Report and AI Use Policy to verify doc generation"
echo "============================================================"
echo ""
