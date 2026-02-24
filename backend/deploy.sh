#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# BBall Backend — GCP Deployment Script
#
# Deploys the backend to Cloud Run with Cloud SQL, GCS, and Pub/Sub.
# Prerequisites: gcloud CLI installed and authenticated, billing enabled.
#
# Usage:
#   1. Edit the CONFIG section below with your values
#   2. chmod +x deploy.sh
#   3. ./deploy.sh
# ============================================================================

# ── CONFIG (edit these) ─────────────────────────────────────────────────────
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

echo "=== BBall GCP Deployment ==="
echo "Project:  ${PROJECT_ID}"
echo "Region:   ${REGION}"
echo "Image:    ${IMAGE}"
echo ""

# ── Step 1: Set project & enable APIs ───────────────────────────────────────
echo ">>> Step 1: Enabling APIs..."
gcloud config set project "${PROJECT_ID}"
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  pubsub.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com

# ── Step 2: Artifact Registry ──────────────────────────────────────────────
echo ">>> Step 2: Creating Artifact Registry repo..."
gcloud artifacts repositories create bball-repo \
  --repository-format=docker \
  --location="${REGION}" \
  --description="BBall Docker images" \
  2>/dev/null || echo "    (repo already exists)"

# ── Step 3: Build & push Docker image ──────────────────────────────────────
echo ">>> Step 3: Building and pushing Docker image..."
gcloud builds submit --tag "${IMAGE}" .

# ── Step 4: Service account + IAM ──────────────────────────────────────────
echo ">>> Step 4: Creating service account and granting roles..."
gcloud iam service-accounts create "${SERVICE_ACCOUNT}" \
  --display-name="BBall Cloud Run SA" \
  2>/dev/null || echo "    (service account already exists)"

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
    --quiet
done

# ── Step 5: Cloud SQL ──────────────────────────────────────────────────────
echo ">>> Step 5: Creating Cloud SQL instance..."
gcloud sql instances describe "${SQL_INSTANCE}" --project="${PROJECT_ID}" &>/dev/null || \
  gcloud sql instances create "${SQL_INSTANCE}" \
    --database-version=POSTGRES_16 \
    --tier=db-custom-1-3840 \
    --region="${REGION}" \
    --no-assign-ip \
    --enable-google-private-path

echo "    Creating database and user..."
gcloud sql databases create bball --instance="${SQL_INSTANCE}" \
  2>/dev/null || echo "    (database already exists)"
gcloud sql users create bball --instance="${SQL_INSTANCE}" \
  --password="${DB_PASSWORD}" \
  2>/dev/null || echo "    (user already exists)"

# ── Step 6: GCS bucket ────────────────────────────────────────────────────
echo ">>> Step 6: Creating GCS bucket..."
gcloud storage buckets create "gs://${GCS_BUCKET}" \
  --location="${REGION}" \
  --uniform-bucket-level-access \
  2>/dev/null || echo "    (bucket already exists)"

# ── Step 7: Pub/Sub topics & subscriptions ─────────────────────────────────
echo ">>> Step 7: Creating Pub/Sub topics and subscriptions..."
gcloud pubsub topics create video-detection 2>/dev/null || echo "    (topic video-detection exists)"
gcloud pubsub topics create video-highlights 2>/dev/null || echo "    (topic video-highlights exists)"

gcloud pubsub subscriptions create video-detection-sub \
  --topic=video-detection \
  --ack-deadline=600 \
  2>/dev/null || echo "    (subscription video-detection-sub exists)"

gcloud pubsub subscriptions create video-highlights-sub \
  --topic=video-highlights \
  --ack-deadline=600 \
  2>/dev/null || echo "    (subscription video-highlights-sub exists)"

# ── Step 8: Secrets ────────────────────────────────────────────────────────
echo ">>> Step 8: Storing secrets..."
echo -n "${JWT_SECRET}" | gcloud secrets create jwt-secret --data-file=- \
  2>/dev/null || echo -n "${JWT_SECRET}" | gcloud secrets versions add jwt-secret --data-file=-

if [ -n "${ROBOFLOW_API_KEY}" ]; then
  echo -n "${ROBOFLOW_API_KEY}" | gcloud secrets create roboflow-api-key --data-file=- \
    2>/dev/null || echo -n "${ROBOFLOW_API_KEY}" | gcloud secrets versions add roboflow-api-key --data-file=-
fi

# ── Common env vars for Cloud Run services ─────────────────────────────────
DB_URL_ASYNC="postgresql+asyncpg://bball:${DB_PASSWORD}@/bball?host=/cloudsql/${SQL_CONNECTION}"
DB_URL_SYNC="postgresql://bball:${DB_PASSWORD}@/bball?host=/cloudsql/${SQL_CONNECTION}"

# ── Step 9: Deploy API service ─────────────────────────────────────────────
echo ">>> Step 9: Deploying Cloud Run API service..."
SECRETS_FLAG="JWT_SECRET=jwt-secret:latest"
if [ -n "${ROBOFLOW_API_KEY}" ]; then
  SECRETS_FLAG="${SECRETS_FLAG},ROBOFLOW_API_KEY=roboflow-api-key:latest"
fi

gcloud run deploy bball-api \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --add-cloudsql-instances="${SQL_CONNECTION}" \
  --set-env-vars="DATABASE_URL=${DB_URL_ASYNC}" \
  --set-env-vars="DATABASE_URL_SYNC=${DB_URL_SYNC}" \
  --set-env-vars="GCS_BUCKET=${GCS_BUCKET}" \
  --set-env-vars="GCS_PROJECT_ID=${PROJECT_ID}" \
  --set-env-vars="GCS_ENDPOINT_URL=" \
  --set-env-vars="PUBSUB_PROJECT_ID=${PROJECT_ID}" \
  --set-env-vars="PUBSUB_EMULATOR_HOST=" \
  --set-env-vars="PUBSUB_TOPIC_DETECTION=video-detection" \
  --set-env-vars="PUBSUB_TOPIC_HIGHLIGHTS=video-highlights" \
  --set-secrets="${SECRETS_FLAG}" \
  --port=8000 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=10 \
  --allow-unauthenticated

# ── Step 10: Deploy Worker service ─────────────────────────────────────────
echo ">>> Step 10: Deploying Cloud Run Worker service..."
gcloud run deploy bball-worker \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --add-cloudsql-instances="${SQL_CONNECTION}" \
  --command="python","-m","app.workers.subscriber" \
  --set-env-vars="DATABASE_URL=${DB_URL_ASYNC}" \
  --set-env-vars="DATABASE_URL_SYNC=${DB_URL_SYNC}" \
  --set-env-vars="GCS_BUCKET=${GCS_BUCKET}" \
  --set-env-vars="GCS_PROJECT_ID=${PROJECT_ID}" \
  --set-env-vars="GCS_ENDPOINT_URL=" \
  --set-env-vars="PUBSUB_PROJECT_ID=${PROJECT_ID}" \
  --set-env-vars="PUBSUB_EMULATOR_HOST=" \
  --set-env-vars="PUBSUB_TOPIC_DETECTION=video-detection" \
  --set-env-vars="PUBSUB_TOPIC_HIGHLIGHTS=video-highlights" \
  --set-env-vars="PUBSUB_SUBSCRIPTION_DETECTION=video-detection-sub" \
  --set-env-vars="PUBSUB_SUBSCRIPTION_HIGHLIGHTS=video-highlights-sub" \
  --set-secrets="${SECRETS_FLAG}" \
  --port=8080 \
  --memory=4Gi \
  --cpu=2 \
  --min-instances=1 \
  --max-instances=3 \
  --timeout=3600 \
  --no-allow-unauthenticated \
  --no-cpu-throttling

# ── Step 11: Run database migrations ──────────────────────────────────────
echo ">>> Step 11: Running database migrations..."
gcloud run jobs create bball-migrate \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --add-cloudsql-instances="${SQL_CONNECTION}" \
  --set-env-vars="DATABASE_URL_SYNC=${DB_URL_SYNC}" \
  --command="alembic","upgrade","head" \
  --memory=512Mi \
  2>/dev/null || echo "    (migration job already exists, executing...)"

gcloud run jobs execute bball-migrate --region="${REGION}" --wait

# ── Done ───────────────────────────────────────────────────────────────────
API_URL=$(gcloud run services describe bball-api --region="${REGION}" --format="value(status.url)")
echo ""
echo "=== Deployment complete ==="
echo "API URL: ${API_URL}"
echo ""
echo "Verify:"
echo "  curl ${API_URL}/health"
echo "  gcloud run services logs read bball-api --region=${REGION} --limit=20"
echo "  gcloud run services logs read bball-worker --region=${REGION} --limit=20"
