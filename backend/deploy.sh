#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# BBall Backend — GCP Deployment Script
#
# Deploys the backend to Cloud Run with Cloud SQL, GCS, and Pub/Sub.
# Prerequisites: gcloud CLI installed and authenticated, billing enabled.
#
# Usage:
#   1. Set required env vars:
#        export GCP_PROJECT_ID="your-project-id"
#        export DB_PASSWORD="$(openssl rand -base64 24)"
#        export JWT_SECRET="$(openssl rand -base64 32)"
#        export ROBOFLOW_API_KEY=""  # optional
#   2. chmod +x deploy.sh
#   3. ./deploy.sh
#
# The script is idempotent — safe to re-run if a step fails partway through.
# ============================================================================

# ── CONFIG ──────────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID env var}"
REGION="${GCP_REGION:-us-central1}"
DB_PASSWORD="${DB_PASSWORD:?Set DB_PASSWORD env var}"
JWT_SECRET="${JWT_SECRET:?Set JWT_SECRET env var}"
ROBOFLOW_API_KEY="${ROBOFLOW_API_KEY:-}"

# Derived names
SERVICE_ACCOUNT="bball-sa"
SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/bball-repo/bball:latest"
SQL_INSTANCE="bball-db"
SQL_CONNECTION="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"
GCS_BUCKET="bball-videos-${PROJECT_ID}"
SA_KEY_FILE="/tmp/bball-sa-key.json"

# Get current authenticated user for IAM binding
DEPLOYER_EMAIL=$(gcloud config get account 2>/dev/null)

echo "=== BBall GCP Deployment ==="
echo "Project:   ${PROJECT_ID}"
echo "Region:    ${REGION}"
echo "Image:     ${IMAGE}"
echo "Deployer:  ${DEPLOYER_EMAIL}"
echo ""

# ── Step 1: Set project & enable APIs ───────────────────────────────────────
echo ">>> Step 1: Enabling APIs..."
gcloud config set project "${PROJECT_ID}" --quiet
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  pubsub.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  --quiet
echo "    APIs enabled."

# ── Step 2: Artifact Registry ──────────────────────────────────────────────
echo ">>> Step 2: Creating Artifact Registry repo..."
if gcloud artifacts repositories describe bball-repo --location="${REGION}" &>/dev/null; then
  echo "    (repo already exists)"
else
  gcloud artifacts repositories create bball-repo \
    --repository-format=docker \
    --location="${REGION}" \
    --description="BBall Docker images" \
    --quiet
  echo "    Repo created."
fi

# ── Step 3: Build & push Docker image ──────────────────────────────────────
echo ">>> Step 3: Building and pushing Docker image..."
gcloud builds submit --tag "${IMAGE}" . --quiet
echo "    Image built and pushed."

# ── Step 4: Service account + IAM ──────────────────────────────────────────
echo ">>> Step 4: Creating service account and granting roles..."
if gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" &>/dev/null; then
  echo "    (service account already exists)"
else
  gcloud iam service-accounts create "${SERVICE_ACCOUNT}" \
    --display-name="BBall Cloud Run SA" \
    --project="${PROJECT_ID}" \
    --quiet
  echo "    Service account created."
fi

# Grant roles to the service account
ROLES=(
  "roles/cloudsql.client"
  "roles/storage.admin"
  "roles/pubsub.editor"
  "roles/pubsub.subscriber"
  "roles/secretmanager.secretAccessor"
)
for role in "${ROLES[@]}"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${role}" \
    --quiet \
    --condition=None \
    > /dev/null
done
echo "    IAM roles granted to service account."

# Grant the deployer permission to act as the service account (required for Cloud Run deploy)
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --member="user:${DEPLOYER_EMAIL}" \
  --role="roles/iam.serviceAccountUser" \
  --project="${PROJECT_ID}" \
  --quiet \
  > /dev/null
echo "    Deployer granted serviceAccountUser on ${SA_EMAIL}."

# Create SA key and store in Secret Manager (needed for GCS signed URLs)
echo "    Creating service account key for GCS signing..."
gcloud iam service-accounts keys create "${SA_KEY_FILE}" \
  --iam-account="${SA_EMAIL}" \
  --project="${PROJECT_ID}" \
  --quiet 2>/dev/null || echo "    (using existing key file)"

if ! gcloud secrets describe gcs-sa-key --project="${PROJECT_ID}" &>/dev/null; then
  gcloud secrets create gcs-sa-key \
    --data-file="${SA_KEY_FILE}" \
    --project="${PROJECT_ID}" \
    --quiet
  echo "    Created secret: gcs-sa-key"
else
  gcloud secrets versions add gcs-sa-key \
    --data-file="${SA_KEY_FILE}" \
    --project="${PROJECT_ID}" \
    --quiet
  echo "    Updated secret: gcs-sa-key"
fi
rm -f "${SA_KEY_FILE}"

# ── Step 5: Cloud SQL ──────────────────────────────────────────────────────
echo ">>> Step 5: Creating Cloud SQL instance..."
if gcloud sql instances describe "${SQL_INSTANCE}" --project="${PROJECT_ID}" &>/dev/null; then
  echo "    (instance already exists)"
else
  gcloud sql instances create "${SQL_INSTANCE}" \
    --database-version=POSTGRES_16 \
    --tier=db-f1-micro \
    --edition=ENTERPRISE \
    --region="${REGION}" \
    --quiet
  echo "    Cloud SQL instance created."
fi

echo "    Creating database and user..."
gcloud sql databases create bball --instance="${SQL_INSTANCE}" --quiet \
  2>/dev/null || echo "    (database already exists)"
gcloud sql users create bball --instance="${SQL_INSTANCE}" --password="${DB_PASSWORD}" --quiet \
  2>/dev/null || true
gcloud sql users set-password bball --instance="${SQL_INSTANCE}" --password="${DB_PASSWORD}" --quiet \
  2>/dev/null || true

# Authorize all IPs (password-protected; lock down with VPC for production)
gcloud sql instances patch "${SQL_INSTANCE}" \
  --authorized-networks=0.0.0.0/0 \
  --project="${PROJECT_ID}" \
  --quiet 2>/dev/null || true

# Get the public IP for connection strings
SQL_IP=$(gcloud sql instances describe "${SQL_INSTANCE}" --project="${PROJECT_ID}" --format="value(ipAddresses[0].ipAddress)")
echo "    Cloud SQL IP: ${SQL_IP}"

# ── Step 6: GCS bucket ────────────────────────────────────────────────────
echo ">>> Step 6: Creating GCS bucket..."
if gcloud storage buckets describe "gs://${GCS_BUCKET}" &>/dev/null; then
  echo "    (bucket already exists)"
else
  gcloud storage buckets create "gs://${GCS_BUCKET}" \
    --location="${REGION}" \
    --uniform-bucket-level-access \
    --quiet
  echo "    Bucket created."
fi

# ── Step 7: Pub/Sub topics & subscriptions ─────────────────────────────────
echo ">>> Step 7: Creating Pub/Sub topics and subscriptions..."
gcloud pubsub topics create video-detection --quiet 2>/dev/null || echo "    (topic video-detection exists)"
gcloud pubsub topics create video-highlights --quiet 2>/dev/null || echo "    (topic video-highlights exists)"

gcloud pubsub subscriptions create video-detection-sub \
  --topic=video-detection --ack-deadline=600 --quiet \
  2>/dev/null || echo "    (subscription video-detection-sub exists)"

gcloud pubsub subscriptions create video-highlights-sub \
  --topic=video-highlights --ack-deadline=600 --quiet \
  2>/dev/null || echo "    (subscription video-highlights-sub exists)"

# ── Step 8: Secrets ────────────────────────────────────────────────────────
echo ">>> Step 8: Storing secrets..."

# Helper: create secret if it doesn't exist, then add a version with the value
store_secret() {
  local name="$1"
  local value="$2"
  if ! gcloud secrets describe "${name}" --project="${PROJECT_ID}" &>/dev/null; then
    echo -n "${value}" | gcloud secrets create "${name}" \
      --data-file=- --project="${PROJECT_ID}" --quiet
    echo "    Created secret: ${name}"
  else
    echo -n "${value}" | gcloud secrets versions add "${name}" \
      --data-file=- --project="${PROJECT_ID}" --quiet
    echo "    Updated secret: ${name}"
  fi
}

store_secret "jwt-secret" "${JWT_SECRET}"
if [ -n "${ROBOFLOW_API_KEY}" ]; then
  store_secret "roboflow-api-key" "${ROBOFLOW_API_KEY}"
fi

# ── Common env vars for Cloud Run services ─────────────────────────────────
DB_URL_ASYNC="postgresql+asyncpg://bball:${DB_PASSWORD}@${SQL_IP}/bball?ssl=disable"
DB_URL_SYNC="postgresql://bball:${DB_PASSWORD}@${SQL_IP}/bball"

SECRETS_FLAG="JWT_SECRET=jwt-secret:latest,GCS_SERVICE_ACCOUNT_JSON=gcs-sa-key:latest"
if [ -n "${ROBOFLOW_API_KEY}" ]; then
  SECRETS_FLAG="${SECRETS_FLAG},ROBOFLOW_API_KEY=roboflow-api-key:latest"
fi

# ── Step 9: Deploy API service ─────────────────────────────────────────────
echo ">>> Step 9: Deploying Cloud Run API service..."
# Use ^::^ delimiter to avoid comma-parsing issues with special chars in DB password
API_ENV="^::^"
API_ENV+="DATABASE_URL=${DB_URL_ASYNC}"
API_ENV+="::DATABASE_URL_SYNC=${DB_URL_SYNC}"
API_ENV+="::GCS_BUCKET=${GCS_BUCKET}"
API_ENV+="::GCS_PROJECT_ID=${PROJECT_ID}"
API_ENV+="::GCS_ENDPOINT_URL="
API_ENV+="::PUBSUB_PROJECT_ID=${PROJECT_ID}"
API_ENV+="::PUBSUB_EMULATOR_HOST="
API_ENV+="::PUBSUB_TOPIC_DETECTION=video-detection"
API_ENV+="::PUBSUB_TOPIC_HIGHLIGHTS=video-highlights"

gcloud run deploy bball-api \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --add-cloudsql-instances="${SQL_CONNECTION}" \
  --set-env-vars="${API_ENV}" \
  --set-secrets="${SECRETS_FLAG}" \
  --port=8000 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=10 \
  --allow-unauthenticated \
  --project="${PROJECT_ID}" \
  --quiet
echo "    API service deployed."

# ── Step 10: Deploy Worker service ─────────────────────────────────────────
echo ">>> Step 10: Deploying Cloud Run Worker service..."
WORKER_ENV="^::^"
WORKER_ENV+="DATABASE_URL=${DB_URL_ASYNC}"
WORKER_ENV+="::DATABASE_URL_SYNC=${DB_URL_SYNC}"
WORKER_ENV+="::GCS_BUCKET=${GCS_BUCKET}"
WORKER_ENV+="::GCS_PROJECT_ID=${PROJECT_ID}"
WORKER_ENV+="::GCS_ENDPOINT_URL="
WORKER_ENV+="::PUBSUB_PROJECT_ID=${PROJECT_ID}"
WORKER_ENV+="::PUBSUB_EMULATOR_HOST="
WORKER_ENV+="::PUBSUB_TOPIC_DETECTION=video-detection"
WORKER_ENV+="::PUBSUB_TOPIC_HIGHLIGHTS=video-highlights"
WORKER_ENV+="::PUBSUB_SUBSCRIPTION_DETECTION=video-detection-sub"
WORKER_ENV+="::PUBSUB_SUBSCRIPTION_HIGHLIGHTS=video-highlights-sub"

gcloud run deploy bball-worker \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --add-cloudsql-instances="${SQL_CONNECTION}" \
  --command="python","-m","app.workers.subscriber" \
  --set-env-vars="${WORKER_ENV}" \
  --set-secrets="${SECRETS_FLAG}" \
  --port=8080 \
  --memory=4Gi \
  --cpu=2 \
  --min-instances=1 \
  --max-instances=3 \
  --timeout=3600 \
  --no-allow-unauthenticated \
  --no-cpu-throttling \
  --project="${PROJECT_ID}" \
  --quiet
echo "    Worker service deployed."

# ── Step 11: Run database migrations ──────────────────────────────────────
echo ">>> Step 11: Running database migrations..."
if gcloud run jobs describe bball-migrate --region="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
  echo "    (migration job already exists, updating...)"
  gcloud run jobs update bball-migrate \
    --image="${IMAGE}" \
    --region="${REGION}" \
    --service-account="${SA_EMAIL}" \
    --set-cloudsql-instances="${SQL_CONNECTION}" \
    --set-env-vars="DATABASE_URL_SYNC=${DB_URL_SYNC},PYTHONPATH=/app" \
    --command="alembic","upgrade","head" \
    --memory=512Mi \
    --project="${PROJECT_ID}" \
    --quiet
else
  gcloud run jobs create bball-migrate \
    --image="${IMAGE}" \
    --region="${REGION}" \
    --service-account="${SA_EMAIL}" \
    --set-cloudsql-instances="${SQL_CONNECTION}" \
    --set-env-vars="DATABASE_URL_SYNC=${DB_URL_SYNC},PYTHONPATH=/app" \
    --command="alembic","upgrade","head" \
    --memory=512Mi \
    --project="${PROJECT_ID}" \
    --quiet
fi

gcloud run jobs execute bball-migrate --region="${REGION}" --project="${PROJECT_ID}" --wait --quiet
echo "    Migrations complete."

# ── Done ───────────────────────────────────────────────────────────────────
API_URL=$(gcloud run services describe bball-api --region="${REGION}" --project="${PROJECT_ID}" --format="value(status.url)")
echo ""
echo "=== Deployment complete ==="
echo "API URL: ${API_URL}"
echo ""
echo "Verify:"
echo "  curl ${API_URL}/health"
echo "  gcloud run services logs read bball-api --region=${REGION} --limit=20"
echo "  gcloud run services logs read bball-worker --region=${REGION} --limit=20"
