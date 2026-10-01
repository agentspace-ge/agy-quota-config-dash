#!/usr/bin/env bash
set -euo pipefail

# Configuration
PROJECT_ID="${1:-${PROJECT_ID:-}}"
REGION="${2:-${REGION:-us-east5}}"
REPO_NAME="antigravity-portal"
IMAGE_TAG="${3:-latest}"

if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
fi

if [[ -z "$PROJECT_ID" ]]; then
  echo "Error: PROJECT_ID must be provided as arg 1 or via environment variable."
  echo "Usage: ./scripts/build_and_push.sh <PROJECT_ID> [REGION] [IMAGE_TAG]"
  exit 1
fi

IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/antigravity-quota-portal:${IMAGE_TAG}"

echo "========================================================================"
echo " Building & Publishing Container Image for Cloud Run"
echo " Target URI: ${IMAGE_URI}"
echo "========================================================================"

# Check for container builder runtime
if command -v podman &>/dev/null; then
  echo "==> Using Podman to build and push..."
  gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet || true
  gcloud auth print-access-token | podman login -u oauth2accesstoken --password-stdin "${REGION}-docker.pkg.dev"
  podman build -t "${IMAGE_URI}" -f Dockerfile .
  podman push "${IMAGE_URI}"
elif command -v docker &>/dev/null && docker info &>/dev/null; then
  echo "==> Using local Docker to build and push..."
  gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet || true
  docker build -t "${IMAGE_URI}" -f Dockerfile .
  docker push "${IMAGE_URI}"
else
  echo "==> Local container engine unavailable. Using Google Cloud Build..."
  gcloud builds submit \
    --project="${PROJECT_ID}" \
    --tag="${IMAGE_URI}" \
    .
fi

echo "==> Build and push complete: ${IMAGE_URI}"
