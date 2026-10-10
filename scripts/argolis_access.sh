#!/usr/bin/env bash
# ==============================================================================
# Google Cloud Argolis & Private Cloud Run Access Helper
#
# Provides authenticated proxy bridging, identity token generation, and
# diagnostic verification for private Cloud Run deployments in Argolis.
# ==============================================================================

set -euo pipefail

# Default configuration values
DEFAULT_SERVICE="antigravity-quota-portal"
DEFAULT_PORT="8080"
DEFAULT_REGION="us-east5"

# Parse CLI arguments and options
COMMAND="${1:-proxy}"
shift || true

SERVICE="${SERVICE_NAME:-$DEFAULT_SERVICE}"
PORT="${PORT:-$DEFAULT_PORT}"
REGION="${REGION:-}"
PROJECT_ID="${PROJECT_ID:-}"
TARGET_PATH="/api/users"

# Help message
show_help() {
  cat << 'EOF'
Usage: ./scripts/argolis_access.sh [COMMAND] [OPTIONS]

Commands:
  proxy       Start the authenticated IAM proxy bridge (Default)
              Enables secure local and Cloud Shell access to private Cloud Run.
  token       Generate and print an identity token (gcloud auth print-identity-token)
  curl [PATH] Perform an authenticated cURL request using a generated identity token
              (Default PATH: /api/users)
  status      Inspect Cloud Run ingress, URL, and verify --no-allow-unauthenticated
  help        Show this help message

Options:
  -s, --service NAME    Cloud Run service name (default: antigravity-quota-portal)
  -p, --port PORT       Local proxy port (default: 8080)
  -r, --region REGION   GCP Region (default: from gcloud config or us-east5)
  --project PROJECT_ID  GCP Project ID (default: from gcloud config)
  -h, --help            Show this help message

Examples:
  # 1. Start proxy bridge on port 8080 (Cloud Shell / Local Browser)
  ./scripts/argolis_access.sh proxy

  # 2. Start proxy bridge on custom port in specific region
  ./scripts/argolis_access.sh proxy --port 9090 --region us-central1

  # 3. Print an identity token for API testing
  ./scripts/argolis_access.sh token

  # 4. Make an authenticated cURL request to private Cloud Run
  ./scripts/argolis_access.sh curl /api/config

  # 5. Check Cloud Run security posture & ingress status
  ./scripts/argolis_access.sh status
EOF
}

# If help is requested as command or option, handle immediately
if [[ "$COMMAND" == "-h" || "$COMMAND" == "--help" || "$COMMAND" == "help" ]]; then
  show_help
  exit 0
fi

# Process options
while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--service)
      SERVICE="$2"
      shift 2
      ;;
    -p|--port)
      PORT="$2"
      shift 2
      ;;
    -r|--region)
      REGION="$2"
      shift 2
      ;;
    --project)
      PROJECT_ID="$2"
      shift 2
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      if [[ "$COMMAND" == "curl" && "$TARGET_PATH" == "/api/users" ]]; then
        TARGET_PATH="$1"
        shift
      else
        echo "Error: Unknown argument: $1" >&2
        show_help >&2
        exit 1
      fi
      ;;
  esac
done

# Ensure gcloud CLI is installed
if ! command -v gcloud &>/dev/null; then
  echo "Error: 'gcloud' CLI is required but not found in PATH." >&2
  exit 1
fi

# Detect project and region if not explicitly provided
if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
fi
if [[ -z "$PROJECT_ID" ]]; then
  echo "Error: PROJECT_ID not set. Set it via --project or 'gcloud config set project <id>'." >&2
  exit 1
fi

if [[ -z "$REGION" ]]; then
  REGION="$(gcloud config get-value run/region 2>/dev/null || gcloud config get-value compute/region 2>/dev/null || true)"
fi
if [[ -z "$REGION" ]]; then
  REGION="$DEFAULT_REGION"
fi

case "$COMMAND" in
  proxy)
    echo "========================================================================"
    echo " Starting Authenticated Proxy Bridge for Argolis Private Cloud Run"
    echo "========================================================================"
    echo " Project : ${PROJECT_ID}"
    echo " Service : ${SERVICE}"
    echo " Region  : ${REGION}"
    echo " Port    : ${PORT}"
    echo " Local   : http://localhost:${PORT}"
    echo "========================================================================"
    echo ""
    echo " Access Instructions:"
    echo "  - Local Browser : Open http://localhost:${PORT}"
    echo "  - Cloud Shell   : Click 'Web Preview' (top-right) -> 'Preview on port ${PORT}'"
    echo "  - Terminal API  : curl http://localhost:${PORT}/api/users"
    echo ""
    echo "Press Ctrl+C to terminate proxy bridge."
    echo "------------------------------------------------------------------------"
    
    exec gcloud run services proxy "${SERVICE}" \
      --port="${PORT}" \
      --region="${REGION}" \
      --project="${PROJECT_ID}"
    ;;

  token)
    # Generate identity token
    TOKEN="$(gcloud auth print-identity-token)"
    if [[ -z "$TOKEN" ]]; then
      echo "Error: Failed to generate identity token. Please run 'gcloud auth login'." >&2
      exit 1
    fi
    echo "$TOKEN"
    ;;

  curl)
    # Fetch Cloud Run service direct URL
    echo "==> Fetching Cloud Run service URL..." >&2
    SERVICE_URL="$(gcloud run services describe "${SERVICE}" \
      --region="${REGION}" \
      --project="${PROJECT_ID}" \
      --format='value(status.url)' 2>/dev/null || true)"

    if [[ -z "$SERVICE_URL" ]]; then
      echo "Warning: Could not retrieve service URL from gcloud. Trying localhost:${PORT}..." >&2
      SERVICE_URL="http://localhost:${PORT}"
    fi

    echo "==> Generating identity token..." >&2
    ID_TOKEN="$(gcloud auth print-identity-token)"

    TARGET_URL="${SERVICE_URL%/}${TARGET_PATH}"
    echo "==> Sending authenticated GET request to: ${TARGET_URL}" >&2

    curl -sSL \
      -H "Authorization: Bearer ${ID_TOKEN}" \
      -H "Accept: application/json" \
      "${TARGET_URL}"
    echo ""
    ;;

  status)
    echo "========================================================================"
    echo " Private Cloud Run Security & Status Audit"
    echo "========================================================================"
    echo " Project : ${PROJECT_ID}"
    echo " Service : ${SERVICE}"
    echo " Region  : ${REGION}"
    echo "------------------------------------------------------------------------"

    # Describe service
    SERVICE_INFO="$(gcloud run services describe "${SERVICE}" \
      --region="${REGION}" \
      --project="${PROJECT_ID}" \
      --format='json' 2>/dev/null || true)"

    if [[ -z "$SERVICE_INFO" ]]; then
      echo "Error: Cloud Run service '${SERVICE}' was not found in ${REGION} (project: ${PROJECT_ID})." >&2
      exit 1
    fi

    SERVICE_URL="$(echo "$SERVICE_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', {}).get('url', 'N/A'))")"
    INGRESS_CONFIG="$(echo "$SERVICE_INFO" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('metadata', {}).get('annotations', {}).get('run.googleapis.com/ingress') or d.get('spec', {}).get('template', {}).get('metadata', {}).get('annotations', {}).get('run.googleapis.com/ingress') or 'internal')")"

    echo " Service URL    : ${SERVICE_URL}"
    echo " Ingress Policy : ${INGRESS_CONFIG}"

    echo ""
    echo " Checking IAM Authentication Policy (--no-allow-unauthenticated)..."
    IAM_POLICY="$(gcloud run services get-iam-policy "${SERVICE}" \
      --region="${REGION}" \
      --project="${PROJECT_ID}" \
      --format='json' 2>/dev/null || echo "{}")"

    ALL_USERS_INVOKER="$(echo "$IAM_POLICY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
bindings = data.get('bindings', [])
has_all_users = False
invokers = []
for b in bindings:
    if b.get('role') == 'roles/run.invoker':
        invokers.extend(b.get('members', []))
        if 'allUsers' in b.get('members', []):
            has_all_users = True
if has_all_users:
    print('FAIL: allUsers is bound to roles/run.invoker (Public Access Enabled!)')
else:
    print('PASS: allUsers is NOT permitted. Cloud Run is strictly private.')
print('Authorized Invokers:')
for m in invokers:
    print(f'  - {m}')
")"
    echo " ${ALL_USERS_INVOKER}"
    echo "========================================================================"
    ;;

  help|-h|--help)
    show_help
    ;;

  *)
    echo "Error: Unknown command '$COMMAND'." >&2
    show_help >&2
    exit 1
    ;;
esac
