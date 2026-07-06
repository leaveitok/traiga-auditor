@echo off
REM =============================================================================
REM deploy.bat - Full deployment for AI Transparency Auditor v2
REM Run from cmd:
REM   cd "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"
REM   deploy\deploy.bat
REM =============================================================================

set PROJECT_ID=traiga-auditor
set REGION=us-central1
set SERVICE_NAME=ai-transparency-auditor-api
set IMAGE_REPO=ai-transparency-auditor
set IMAGE_NAME=api
set SECRET_NAME=traiga-service-account
set IMAGE_URI=%REGION%-docker.pkg.dev/%PROJECT_ID%/%IMAGE_REPO%/%IMAGE_NAME%:latest

set ROOT_DIR=%~dp0..
set BACKEND_DIR=%ROOT_DIR%\backend
set FRONTEND_DIR=%ROOT_DIR%\frontend
set ENV_FILE=%~dp0env.yaml
set SA_FILE=%BACKEND_DIR%\service_account.json

echo.
echo ============================================================
echo   AI Transparency Auditor v2 - Deployment
echo   Project : %PROJECT_ID%
echo   Region  : %REGION%
echo ============================================================
echo.

REM -- Step 0: Set GCP project --------------------------------------------------
echo [0/5] Setting GCP project...
REM `call` is REQUIRED before every gcloud invocation: gcloud is gcloud.cmd (a
REM batch script). Without call, control transfers and NEVER returns — the
REM rest of this script silently never runs (bit us 2026-07-06).
call gcloud config set project %PROJECT_ID%
REM gcloud config set returns exit code 1 on SDK/Python warnings even on success; reset before continuing
ver > nul

REM -- Step 1: Enable APIs ------------------------------------------------------
echo [1/5] Enabling required GCP APIs...
call gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com --quiet
if %errorlevel% neq 0 goto error

REM -- Step 2: Upload service account to Secret Manager ------------------------
echo [2/5] Uploading service account to Secret Manager...

if not exist "%SA_FILE%" (
    echo ERROR: service_account.json not found at %SA_FILE%
    goto error
)

call gcloud secrets describe %SECRET_NAME% --project=%PROJECT_ID% >nul 2>&1
if %errorlevel% neq 0 (
    echo   Creating secret: %SECRET_NAME%
    call gcloud secrets create %SECRET_NAME% --replication-policy=automatic --project=%PROJECT_ID%
)

call gcloud secrets versions add %SECRET_NAME% --data-file="%SA_FILE%" --project=%PROJECT_ID%
if %errorlevel% neq 0 goto error
echo   Secret uploaded OK.

REM Grant Cloud Run service account access to the secret
for /f "tokens=*" %%i in ('gcloud projects describe %PROJECT_ID% --format=value(projectNumber)') do set PROJECT_NUMBER=%%i
set CR_SA=%PROJECT_NUMBER%-compute@developer.gserviceaccount.com
call gcloud secrets add-iam-policy-binding %SECRET_NAME% --member=serviceAccount:%CR_SA% --role=roles/secretmanager.secretAccessor --project=%PROJECT_ID% --quiet

REM -- Step 3: Build Docker image -----------------------------------------------
echo [3/5] Building Docker image via Cloud Build...

call gcloud artifacts repositories describe %IMAGE_REPO% --location=%REGION% --project=%PROJECT_ID% >nul 2>&1
if %errorlevel% neq 0 (
    echo   Creating Artifact Registry repo: %IMAGE_REPO%
    call gcloud artifacts repositories create %IMAGE_REPO% --repository-format=docker --location=%REGION% --project=%PROJECT_ID% --quiet
)

call gcloud builds submit "%BACKEND_DIR%" --tag=%IMAGE_URI% --project=%PROJECT_ID% --timeout=20m
if %errorlevel% neq 0 goto error
echo   Image built and pushed OK.

REM -- Step 4: Deploy to Cloud Run ----------------------------------------------
echo [4/5] Deploying to Cloud Run...

if not exist "%ENV_FILE%" (
    echo ERROR: env.yaml not found at %ENV_FILE%
    goto error
)

call gcloud run deploy %SERVICE_NAME% --image=%IMAGE_URI% --region=%REGION% --platform=managed --no-allow-unauthenticated --env-vars-file="%ENV_FILE%" --set-secrets=/secrets/service_account.json=%SECRET_NAME%:latest --memory=2Gi --cpu=1 --min-instances=0 --max-instances=3 --timeout=300 --concurrency=80 --project=%PROJECT_ID% --quiet
if %errorlevel% neq 0 goto error

call gcloud run services add-iam-policy-binding %SERVICE_NAME% --region=%REGION% --member=allUsers --role=roles/run.invoker --project=%PROJECT_ID% --quiet
echo   Cloud Run deploy OK.

REM -- Step 5: Build and deploy frontend ----------------------------------------
echo [5/5] Building and deploying frontend...

cd /d "%FRONTEND_DIR%"
REM Build with existing node_modules first. Avoid `npm ci` here: on Windows it
REM triggers the npm optional-dependency (rollup) bug (#4828) and the build dies.
call npm run build
if %errorlevel%==0 goto frontend_deploy

echo   Build failed - applying clean-reinstall fix for the npm/rollup bug...
if exist package-lock.json del /f /q package-lock.json
if exist node_modules rmdir /s /q node_modules
call npm install
if %errorlevel% neq 0 goto error
call npm run build
if %errorlevel% neq 0 goto error

:frontend_deploy
cd /d "%ROOT_DIR%"
call firebase deploy --only hosting --project=%PROJECT_ID%
if %errorlevel% neq 0 goto error

echo.
echo ============================================================
echo   DEPLOYMENT COMPLETE
echo   App URL : https://%PROJECT_ID%.web.app
echo ============================================================
echo.
goto end

:error
echo.
echo DEPLOYMENT FAILED - see error above
echo.
exit /b 1

:end
