#!/usr/bin/env bash
# ==============================================================================
# Enterprise Zero-Trust & Private Cloud Run Access Helper
#
# Provides authenticated proxy bridging, identity token generation, Cloud DNS &
# Managed SSL diagnostics, IAP verification, and bidirectional mode switching
# (proxy <-> external_lb) for private Cloud Run deployments.
# ==============================================================================

set -euo pipefail

# Default configuration values
DEFAULT_SERVICE="antigravity-quota-portal"
DEFAULT_PORT="8080"
DEFAULT_REGION="us-east5"
DEFAULT_LB_IP_NAME="antigravity-portal-ip"
DEFAULT_BACKEND_NAME="antigravity-portal-backend"

# Parse CLI arguments and options
COMMAND="${1:-proxy}"
shift || true

SERVICE="${SERVICE_NAME:-$DEFAULT_SERVICE}"
PORT="${PORT:-$DEFAULT_PORT}"
REGION="${REGION:-}"
PROJECT_ID="${PROJECT_ID:-}"
DNS_ZONE="${DNS_ZONE_NAME:-}"
LB_DOMAIN="${LB_DOMAIN:-}"
IAP_CLIENT_ID="${PORTAL_IAP_CLIENT_ID:-}"
TARGET_PATH="/api/users"
SWITCH_TARGET_MODE=""

# Help message
show_help() {
  cat << 'EOF'
Usage: ./scripts/portal_access.sh [COMMAND] [OPTIONS]

Commands:
  proxy                          Start the authenticated IAM proxy bridge (Default)
                                 Enables secure local and Cloud Shell access to private Cloud Run.
  token                          Generate and print an identity token (gcloud auth print-identity-token)
  curl [PATH]                    Perform an authenticated cURL request to Cloud Run using an identity token
                                 (Default PATH: /api/users)
  status                         Inspect Cloud Run ingress, URL, and verify --no-allow-unauthenticated
  dns-check                      Verify Cloud DNS Managed Zone name servers and A-record IP propagation
  iap-status                     Check GCLB Static IP, Managed SSL Certificate ACTIVE status, and IAP readiness
  iap-curl [PATH]                Perform an authenticated OIDC cURL request through the GCLB + IAP endpoint
  switch-mode <proxy|external_lb|dual>
                                 Instantly switch Cloud Run ingress between:
                                   - proxy       (--ingress=all, for gcloud run services proxy)
                                   - external_lb (--ingress=internal-and-cloud-load-balancing, strict GCLB+IAP)
                                   - dual        (--ingress=all, allows both GCLB+IAP and proxy simultaneously)
  help                           Show this help message

Options:
  -s, --service NAME             Cloud Run service name (default: antigravity-quota-portal)
  -p, --port PORT                Local proxy port (default: 8080)
  -r, --region REGION            GCP Region (default: from gcloud config or us-east5)
  --project PROJECT_ID           GCP Project ID (default: from gcloud config)
  --zone DNS_ZONE_NAME           Cloud DNS Managed Zone name (for dns-check)
  --domain LB_HOSTNAME           Load Balancer public hostname (for dns-check and iap-curl)
  --client-id IAP_CLIENT_ID      IAP OAuth 2.0 Client ID (for iap-curl programmatic OIDC auth)
  -h, --help                     Show this help message

Examples:
  # 1. Start proxy bridge on port 8080 (Cloud Shell / Local Browser)
  ./scripts/portal_access.sh proxy

  # 2. Check Cloud DNS zone name servers & A-record resolution
  ./scripts/portal_access.sh dns-check --zone sub-domain --domain quota.demo.example.com

  # 3. Check Managed SSL Certificate ACTIVE status & GCLB+IAP cutover readiness
  ./scripts/portal_access.sh iap-status

  # 4. Instantly switch Cloud Run between proxy mode and strict external_lb mode
  ./scripts/portal_access.sh switch-mode external_lb
  ./scripts/portal_access.sh switch-mode proxy

  # 5. Perform an authenticated cURL request through GCLB + IAP
  ./scripts/portal_access.sh iap-curl /api/auth/me --domain quota.demo.example.com --client-id YOUR_CLIENT_ID
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
    --zone)
      DNS_ZONE="$2"
      shift 2
      ;;
    --domain)
      LB_DOMAIN="$2"
      shift 2
      ;;
    --client-id)
      IAP_CLIENT_ID="$2"
      shift 2
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      if [[ ( "$COMMAND" == "curl" || "$COMMAND" == "iap-curl" ) && "$TARGET_PATH" == "/api/users" ]]; then
        TARGET_PATH="$1"
        shift
      elif [[ "$COMMAND" == "switch-mode" && -z "$SWITCH_TARGET_MODE" ]]; then
        SWITCH_TARGET_MODE="$1"
        shift
      else
        echo "Error: Unknown argument: $1" >&2
        show_help >&2
        exit 1
      fi
      ;;
  esac
done

# Validate switch-mode argument early before invoking gcloud
if [[ "$COMMAND" == "switch-mode" ]]; then
  if [[ -z "$SWITCH_TARGET_MODE" ]]; then
    echo "Error: 'switch-mode' requires a target mode: proxy, external_lb, or dual." >&2
    exit 1
  fi
  if [[ "$SWITCH_TARGET_MODE" != "proxy" && "$SWITCH_TARGET_MODE" != "external_lb" && "$SWITCH_TARGET_MODE" != "dual" ]]; then
    echo "Error: Invalid mode '$SWITCH_TARGET_MODE'. Must be one of: proxy, external_lb, dual." >&2
    exit 1
  fi
fi

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
    echo " Starting Authenticated Proxy Bridge for Private Cloud Run"
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
    TOKEN="$(gcloud auth print-identity-token)"
    if [[ -z "$TOKEN" ]]; then
      echo "Error: Failed to generate identity token. Please run 'gcloud auth login'." >&2
      exit 1
    fi
    echo "$TOKEN"
    ;;

  curl)
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

  dns-check)
    echo "========================================================================"
    echo " Cloud DNS Zone Delegation & A-Record Verification"
    echo "========================================================================"
    echo " Project : ${PROJECT_ID}"
    echo " Zone    : ${DNS_ZONE:-<not specified; pass --zone ZONE_NAME>}"
    echo " Domain  : ${LB_DOMAIN:-<not specified; pass --domain HOSTNAME>}"
    echo "------------------------------------------------------------------------"

    LB_IP="$(gcloud compute addresses describe "${DEFAULT_LB_IP_NAME}" \
      --global \
      --project="${PROJECT_ID}" \
      --format='value(address)' 2>/dev/null || true)"
    echo " Reserved Global Static IP (${DEFAULT_LB_IP_NAME}): ${LB_IP:-NOT_FOUND}"

    if [[ -n "$DNS_ZONE" ]]; then
      echo ""
      echo " Cloud DNS Managed Zone (${DNS_ZONE}) Name Servers:"
      gcloud dns managed-zones describe "${DNS_ZONE}" \
        --project="${PROJECT_ID}" \
        --format='value(nameServers)' 2>/dev/null | tr ';' '\n' | sed 's/^/  - /' || echo "  (Zone '${DNS_ZONE}' not found in project ${PROJECT_ID})"
    fi

    if [[ -n "$LB_DOMAIN" ]]; then
      echo ""
      echo " Resolving A-record for '${LB_DOMAIN}'..."
      RESOLVED_IPS="$(python3 -c "
import socket, sys
domain = sys.argv[1]
try:
    infos = socket.getaddrinfo(domain, 443, family=socket.AF_INET)
    ips = sorted(set(i[4][0] for i in infos))
    print(','.join(ips))
except Exception as e:
    print(f'UNRESOLVED ({e})')
" "${LB_DOMAIN}")"
      echo " Resolved IPv4 : ${RESOLVED_IPS}"
      if [[ -n "$LB_IP" && "$RESOLVED_IPS" == *"$LB_IP"* ]]; then
        echo " Status        : PASS (DNS A-record matches Global Static IP ${LB_IP})"
      else
        echo " Status        : PENDING (DNS A-record does not yet match ${LB_IP:-Global Static IP})"
      fi
    fi
    echo "========================================================================"
    ;;

  iap-status)
    echo "========================================================================"
    echo " GCLB + Managed SSL + Identity-Aware Proxy (IAP) Readiness Status"
    echo "========================================================================"
    echo " Project : ${PROJECT_ID}"
    echo " Service : ${SERVICE} (${REGION})"
    echo "------------------------------------------------------------------------"

    LB_IP="$(gcloud compute addresses describe "${DEFAULT_LB_IP_NAME}" \
      --global \
      --project="${PROJECT_ID}" \
      --format='value(address)' 2>/dev/null || true)"
    echo " 1. Global Static IP (${DEFAULT_LB_IP_NAME}) : ${LB_IP:-NOT_PROVISIONED}"

    echo ""
    echo " 2. Google-Managed SSL Certificates:"
    CERTS_JSON="$(gcloud compute ssl-certificates list \
      --global \
      --project="${PROJECT_ID}" \
      --filter='name~^antigravity-portal-cert' \
      --format='json' 2>/dev/null || echo "[]")"

    CERT_STATUS="$(echo "$CERTS_JSON" | python3 -c "
import sys, json
certs = json.load(sys.stdin)
if not certs:
    print('  - No antigravity-portal-cert-* Managed SSL certificate found.')
    print('CERT_READY=false')
else:
    all_active = True
    for c in certs:
        name = c.get('name', 'unknown')
        managed = c.get('managed', {})
        status = managed.get('status', c.get('type', 'UNKNOWN'))
        domains = managed.get('domainStatus', {})
        print(f'  - Certificate : {name}')
        print(f'    Status      : {status}')
        for dom, dstat in domains.items():
            print(f'    Domain      : {dom} -> {dstat}')
        if status != 'ACTIVE':
            all_active = False
    print(f'CERT_READY={\"true\" if all_active else \"false\"}')
")"
    echo "$CERT_STATUS" | grep -v '^CERT_READY='
    IS_CERT_READY="$(echo "$CERT_STATUS" | grep '^CERT_READY=' | cut -d= -f2)"

    echo ""
    echo " 3. IAP Backend Service (${DEFAULT_BACKEND_NAME}):"
    BACKEND_JSON="$(gcloud compute backend-services describe "${DEFAULT_BACKEND_NAME}" \
      --global \
      --project="${PROJECT_ID}" \
      --format='json' 2>/dev/null || echo "{}")"
    echo "$BACKEND_JSON" | python3 -c "
import sys, json
b = json.load(sys.stdin)
if not b:
    print('  - Backend service not provisioned.')
else:
    iap = b.get('iap', {})
    enabled = iap.get('enabled', False)
    client_id = iap.get('oauth2ClientId') or '(Google-Managed OAuth Client)'
    print(f'  - IAP Enabled : {enabled}')
    print(f'  - OAuth Client: {client_id}')
"

    echo ""
    echo " 4. Cloud Run Ingress Posture:"
    INGRESS_NOW="$(gcloud run services describe "${SERVICE}" \
      --region="${REGION}" \
      --project="${PROJECT_ID}" \
      --format='value(metadata.annotations."run.googleapis.com/ingress")' 2>/dev/null || echo "unknown")"
    echo "  - Current Ingress : ${INGRESS_NOW}"

    echo "------------------------------------------------------------------------"
    if [[ "$IS_CERT_READY" == "true" ]]; then
      echo " Verdict: READY FOR GCLB+IAP CUTOVER!"
      echo "  - Switch via CLI : ./scripts/portal_access.sh switch-mode external_lb"
      echo "  - Or Terraform   : Set access_mode = \"external_lb\" in terraform.tfvars"
    else
      echo " Verdict: WARMUP IN PROGRESS (Keep access_mode = \"proxy\" until SSL Status is ACTIVE)"
      echo "  - Use './scripts/portal_access.sh proxy' for immediate local/Cloud Shell access."
    fi
    echo "========================================================================"
    ;;

  iap-curl)
    if [[ -z "$LB_DOMAIN" ]]; then
      echo "Error: 'iap-curl' requires --domain <LB_HOSTNAME> (or LB_DOMAIN env var)." >&2
      exit 1
    fi
    if [[ -z "$IAP_CLIENT_ID" ]]; then
      echo "Error: 'iap-curl' requires --client-id <IAP_OAUTH_CLIENT_ID> (or PORTAL_IAP_CLIENT_ID env var)." >&2
      exit 1
    fi

    echo "==> Generating OIDC token for IAP audience: ${IAP_CLIENT_ID}..." >&2
    ID_TOKEN="$(gcloud auth print-identity-token --audiences="${IAP_CLIENT_ID}")"
    TARGET_URL="https://${LB_DOMAIN%/}${TARGET_PATH}"
    echo "==> Sending IAP-authenticated GET request to: ${TARGET_URL}" >&2

    curl -sSL \
      -H "Authorization: Bearer ${ID_TOKEN}" \
      -H "Accept: application/json" \
      "${TARGET_URL}"
    echo ""
    ;;

  switch-mode)
    if [[ "$SWITCH_TARGET_MODE" == "external_lb" ]]; then
      TARGET_INGRESS="internal-and-cloud-load-balancing"
      MODE_DESC="Strict External Load Balancer + IAP (blocks external direct .run.app proxy)"
    elif [[ "$SWITCH_TARGET_MODE" == "dual" ]]; then
      TARGET_INGRESS="all"
      MODE_DESC="Dual Mode (allows both External GCLB+IAP and IAM-authenticated gcloud run services proxy)"
    else
      TARGET_INGRESS="all"
      MODE_DESC="Proxy Mode (allows IAM-authenticated gcloud run services proxy on localhost:${PORT})"
    fi

    echo "========================================================================"
    echo " Switching Cloud Run Access Mode -> ${SWITCH_TARGET_MODE}"
    echo "========================================================================"
    echo " Project : ${PROJECT_ID}"
    echo " Service : ${SERVICE} (${REGION})"
    echo " Ingress : ${TARGET_INGRESS}"
    echo " Mode    : ${MODE_DESC}"
    echo "------------------------------------------------------------------------"

    gcloud run services update "${SERVICE}" \
      --ingress="${TARGET_INGRESS}" \
      --region="${REGION}" \
      --project="${PROJECT_ID}"

    echo "========================================================================"
    echo " Successfully switched '${SERVICE}' to mode '${SWITCH_TARGET_MODE}' (ingress=${TARGET_INGRESS})."
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
