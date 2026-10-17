#!/usr/bin/env bash
# ==============================================================================
# deploy.sh — Turnkey Deployment of Antigravity Quota Concierge to Vertex AI Agent Engine
#
# Usage:
#   ./deploy.sh [OPTIONS]
#
# Options:
#   --project-id             GCP Project ID (default: $PROJECT_ID or $GOOGLE_CLOUD_PROJECT)
#   --location               Vertex AI region (default: us-central1 or $REGION / $GOOGLE_CLOUD_LOCATION)
#   --staging-bucket         GCS Staging Bucket (default: gs://<PROJECT_ID>-agent-engine-staging)
#   --portal-api-url         Base URL for Antigravity Quota Portal (GCLB+IAP URL or Cloud Run URL)
#   --fallback-cloud-run-url Optional fallback direct Cloud Run URL (.run.app) for seamless proxy/GCLB switching
#   --iap-client-id          Optional OAuth 2.0 Client ID when Portal is fronted by GCLB + IAP
#   --concierge-sa           Service account email for Concierge to Portal IAM authentication
#   --dry-run                Validate configuration and print deployment manifest without deploying
#   --help                   Show this help message
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Defaults (Customer-neutral)
PROJECT_ID="${PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-your-gcp-project-id}}"
LOCATION="${LOCATION:-${GOOGLE_CLOUD_LOCATION:-us-central1}}"
STAGING_BUCKET="${AGENT_ENGINE_STAGING_BUCKET:-}"
PORTAL_API_URL="${PORTAL_API_BASE_URL:-https://antigravity-quota-portal-example.a.run.app}"
FALLBACK_CLOUD_RUN_URL="${PORTAL_FALLBACK_CLOUD_RUN_URL:-}"
IAP_CLIENT_ID="${PORTAL_IAP_CLIENT_ID:-}"
CONCIERGE_SA="${CONCIERGE_SERVICE_ACCOUNT_EMAIL:-}"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id)
      PROJECT_ID="$2"
      shift 2
      ;;
    --location)
      LOCATION="$2"
      shift 2
      ;;
    --staging-bucket)
      STAGING_BUCKET="$2"
      shift 2
      ;;
    --portal-api-url)
      PORTAL_API_URL="$2"
      shift 2
      ;;
    --fallback-cloud-run-url)
      FALLBACK_CLOUD_RUN_URL="$2"
      shift 2
      ;;
    --iap-client-id)
      IAP_CLIENT_ID="$2"
      shift 2
      ;;
    --concierge-sa)
      CONCIERGE_SA="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --help|-h)
      sed -ne '/^#/!q;s/^# //;2,$p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${STAGING_BUCKET}" ]]; then
  STAGING_BUCKET="gs://${PROJECT_ID}-agent-engine-staging"
fi

echo "======================================================================"
echo " Antigravity Quota Concierge — Vertex AI Agent Engine Deployment"
echo "======================================================================"
echo " GCP Project ID:    ${PROJECT_ID}"
echo " Vertex Location:   ${LOCATION}"
echo " Staging Bucket:    ${STAGING_BUCKET}"
echo " Portal API URL:    ${PORTAL_API_URL}"
echo " Concierge SA:      ${CONCIERGE_SA:-<none (local dev / mock)>}"
echo " Dry Run:           ${DRY_RUN}"
echo "======================================================================"

# 1. Environment & Virtualenv Preparation
cd "${SCRIPT_DIR}"

if [[ ! -d ".venv" ]]; then
  echo "[-] Python virtual environment (.venv) not found. Creating..."
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv
    uv pip install --python .venv/bin/python -e .
  elif [[ -x "${HOME}/.local/bin/uv" ]]; then
    "${HOME}/.local/bin/uv" venv .venv
    "${HOME}/.local/bin/uv" pip install --python .venv/bin/python -e .
  else
    python3 -m venv .venv
    .venv/bin/pip install -e .
  fi
fi

PYTHON_BIN="${SCRIPT_DIR}/.venv/bin/python3"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

# 2. Check GCS Staging Bucket (if not dry run)
if [[ "${DRY_RUN}" == "false" ]]; then
  echo "[+] Checking GCS staging bucket: ${STAGING_BUCKET}..."
  if command -v gcloud >/dev/null 2>&1; then
    if ! gcloud storage buckets describe "${STAGING_BUCKET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
      echo "[!] Bucket ${STAGING_BUCKET} does not exist. Creating in ${LOCATION}..."
      gcloud storage buckets create "${STAGING_BUCKET}" \
        --project="${PROJECT_ID}" \
        --location="${LOCATION}" \
        --uniform-bucket-level-access
      echo "[+] Bucket created successfully."
    else
      echo "[+] Verified staging bucket exists."
    fi
  else
    echo "[i] Note: gcloud CLI not found in PATH; skipping pre-creation check. Python Vertex AI SDK will access ${STAGING_BUCKET} directly."
  fi
fi

# 3. Execute Deployment
echo "[+] Launching ReasoningEngine deployment..."
DEPLOY_ARGS=(
  --project-id "${PROJECT_ID}"
  --location "${LOCATION}"
  --staging-bucket "${STAGING_BUCKET}"
  --portal-api-url "${PORTAL_API_URL}"
  --metadata-file "${SCRIPT_DIR}/deployment_metadata.json"
)

if [[ -n "${CONCIERGE_SA}" ]]; then
  DEPLOY_ARGS+=(--concierge-sa-email "${CONCIERGE_SA}")
fi

if [[ -n "${FALLBACK_CLOUD_RUN_URL}" ]]; then
  DEPLOY_ARGS+=(--fallback-cloud-run-url "${FALLBACK_CLOUD_RUN_URL}")
fi

if [[ -n "${IAP_CLIENT_ID}" ]]; then
  DEPLOY_ARGS+=(--iap-client-id "${IAP_CLIENT_ID}")
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  DEPLOY_ARGS+=(--dry-run)
fi

# Clean local bytecode cache to prevent version conflicts in deployment tarball
find "${SCRIPT_DIR}" -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Disable mTLS client certificate auto-probing for standard workstation compatibility
export GOOGLE_API_USE_CLIENT_CERTIFICATE=false
export PYTHONPATH="${SCRIPT_DIR}"

"${PYTHON_BIN}" -m antigravity_quota_concierge.deploy_agent_engine "${DEPLOY_ARGS[@]}"

if [[ "${DRY_RUN}" == "false" ]]; then
  echo ""
  echo "======================================================================"
  echo " Deployment Succeeded!"
  echo " Deployment metadata written to: ${SCRIPT_DIR}/deployment_metadata.json"
  echo "======================================================================"
  echo "Next Steps:"
  echo " 1. Run live remote verification:"
  echo "      python3 ${SCRIPT_DIR}/test_remote_agent.py"
  echo " 2. View in Google Cloud Console:"
  echo "      https://console.cloud.google.com/vertex-ai/reasoning-engine?project=${PROJECT_ID}"
  echo " 3. Verify Agent Registry discovery:"
  echo "      gcloud alpha agent-registry agents list --project=${PROJECT_ID} --location=${LOCATION}"
  echo "======================================================================"
fi
