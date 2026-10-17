# Antigravity Quota Concierge — Enterprise Onboarding & Deployment Guide

This guide walks any engineer through developing, testing, deploying, and maintaining the **Antigravity Quota Concierge** (`antigravity_quota_concierge`) on **Vertex AI Agent Engine** and publishing it to **Gemini Enterprise**.

---

## 1. Architecture & Design Principles

```
  +-------------------------------------------------------------+
  |              Employee in Gemini Enterprise                  |
  +-------------------------------------------------------------+
                                 |
                                 v (OAuth Session Context)
  +-------------------------------------------------------------+
  |    Vertex AI Agent Engine (Reasoning Engine: google-adk)    |
  |                                                             |
  |  +-------------------------------------------------------+  |
  |  | Root Agent: antigravity_quota_concierge               |  |
  |  | Model: gemini-3.5-flash (global location)             |  |
  |  | Tools: get_my_quota_status, get_model_efficiency...   |  |
  |  +-------------------------------------------------------+  |
  |                              |                              |
  |                              v (delegation)                 |
  |  +-------------------------------------------------------+  |
  |  | Sub-Agent: quota_request_agent                        |  |
  |  | Tools: get_quota_request_options, submit_request...   |  |
  |  +-------------------------------------------------------+  |
  +-------------------------------------------------------------+
                                 |
                                 v (Google OIDC Bearer Token + X-Impersonate-User)
  +-------------------------------------------------------------+
  |       Antigravity Quota Portal (Cloud Run Backend)          |
  |                                                             |
  |  * Cryptographic OIDC validation (verify_oauth2_token)      |
  |  * Trusted Reasoning Engine Service Account proxy trust     |
  |  * Firestore persistence & Admin Review Queue               |
  +-------------------------------------------------------------+
                                 |
                                 v
  +-------------------------------------------------------------+
  |        Antigravity Admin Console (Web React SPA)            |
  |                                                             |
  |  * Administrators review, approve, or decline requests      |
  |  * Centralized queue under "Quota Increase Requests" tab    |
  +-------------------------------------------------------------+
```

### Key Technical Patterns
- **Zero-Dependency Sub-Project Isolation:** The agent code is strictly isolated inside `concierge-agent/`, leaving the root portal `Dockerfile` and `pyproject.toml` completely free of ADK dependencies.
- **Dynamic Identity Resolution (`auth.py`):** The agent never relies on hardcoded personas or untrusted LLM arguments. It dynamically resolves the authenticated corporate email from `ToolContext` (`tool_context.user_id`, `tool_context.session.user_id`, or `get_invocation_context().user_id`).
- **Structured State Control & Namespacing (`user:*`):** User identity and persistent preferences are maintained via ADK's native `user:*` namespace (`user:email`, `user:preferred_option`, `user:last_reason_category`) validated with Pydantic (`ConciergeState`).
- **ADK 2.0 Task Delegation:** `quota_request_agent` runs in `mode="task"` with typed `output_schema=QuotaRequestTaskOutput`, providing deterministic task boundaries and structured handoffs.
- **Trusted Service Account Impersonation (`app/api/deps.py`):** The Cloud Run backend validates Google-signed OIDC identity tokens and allows the Vertex AI Reasoning Engine service account (`service-<PROJECT_NUMBER>@gcp-sa-aiplatform-re.iam.gserviceaccount.com`) to pass `X-Impersonate-User` headers on behalf of employees.
- **Model Standard:** Always use `gemini-3.5-flash` (`CONCIERGE_MODEL="gemini-3.5-flash"`). The model is served from `global`; container environment variables must set `GOOGLE_CLOUD_LOCATION="global"` when deployed in `us-central1`.
- **In-App Admin Review Queue:** Requests are stored directly in Firestore and displayed in the Admin Console under the **Quota Increase Requests** tab. No external email/SMTP server is needed.

---

## 2. Prerequisites & Environment Setup

### Required Tools
- **Python 3.10+** (tested on Python 3.11 / 3.13)
- **uv** (recommended for virtualenv management: `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **gcloud CLI** (`gcloud auth login` and `gcloud auth application-default login`)
- **google-agents-cli** (`uv tool install google-agents-cli` to provide `agents-cli`)

### Required GCP IAM Permissions
For the operator deploying and verifying the agent:
- `roles/aiplatform.admin` or `roles/aiplatform.user`
- `roles/storage.admin` or `roles/storage.objectAdmin` on the staging bucket
- `roles/run.viewer` / `roles/run.invoker` on the Cloud Run portal service

For Google-managed Service Agents:
- **Reasoning Engine Service Agent** (`service-<PROJECT_NUMBER>@gcp-sa-aiplatform-re.iam.gserviceaccount.com`): `roles/run.invoker` on Cloud Run.
- **Discovery Engine Service Agent** (`service-<PROJECT_NUMBER>@gcp-sa-discoveryengine.iam.gserviceaccount.com`): `roles/aiplatform.user` on the project.

---

## 3. Step 1: Local Development & Testing (Stage 1)

### Automated Smoke Test (Zero Dependencies)
Run an automated 6-turn HTTP round-trip test against a built-in mock server using only standard Python libraries:
```bash
python3 concierge-agent/run_local_stage1.py --smoke-test
```

### Running the Full Unit Test Suite
The unit test suite covers identity extraction, coaching calculations, multi-agent wiring, dry-run deployment plans, anti-spoofing logic, Pydantic schemas, and namespaced state management (14 tests):
```bash
PYTHONPATH=concierge-agent python3 -m unittest discover -s concierge-agent/tests -v
```

### Interactive Local Playground
Start both the mock Quota Portal (`http://localhost:8080`) and the interactive Concierge web playground (`http://localhost:8000`):
```bash
python3 concierge-agent/run_local_stage1.py
```

### Running with the Official Google ADK Web UI
To run the full visual Agent Development Kit UI:
```bash
cd concierge-agent
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"

export PORTAL_API_BASE_URL="http://localhost:8080"
export DEFAULT_DEMO_USER_EMAIL="alex.morgan@example.com"
export CONCIERGE_MODEL="gemini-3.5-flash"

adk web --host "::" --port 8001 .
```
Access the ADK UI at `http://localhost:8001/dev-ui/`.

---

## 4. Step 2: Terraform Infrastructure Provisioning

The agent infrastructure is optionally managed by Terraform:
1. In `terraform/terraform.tfvars`:
   ```hcl
   project_id             = "your-gcp-project-id"
   region                 = "us-east5"
   concierge_agent_region = "us-central1"
   enable_concierge_agent = true
   ```
2. Apply Terraform:
   ```bash
   cd terraform
   terraform apply
   ```
   This automatically provisions:
   - Storage bucket `gs://<project_id>-agent-engine-staging` in `us-central1` with 30-day lifecycle management.
   - Dedicated Service Account `antigravity-concierge@<project_id>.iam.gserviceaccount.com`.
   - `roles/run.invoker` bindings for the Reasoning Engine service agent.
   - Container environment variables on Cloud Run (`CONCIERGE_SERVICE_ACCOUNT_EMAIL`).

---

## 5. Step 3: Deploying to Vertex AI Agent Engine (Stage 2)

Deploy the multi-agent package to Vertex AI Agent Engine using `deploy.sh`:

```bash
cd concierge-agent
./deploy.sh \
  --project-id "your-gcp-project-id" \
  --location "us-central1" \
  --staging-bucket "gs://your-gcp-project-id-agent-engine-staging" \
  --portal-api-url "https://quota.demo.example.com" \
  --fallback-cloud-run-url "https://antigravity-quota-portal-<hash>-<region>.a.run.app" \
  --iap-client-id "YOUR_IAP_OAUTH_CLIENT_ID.apps.googleusercontent.com"
```
*(Tip: When `--fallback-cloud-run-url` is provided alongside `--portal-api-url`, the Concierge Agent automatically falls back to the direct Cloud Run `.run.app` service URL using direct Cloud Run OIDC authentication if the Portal is switched from `external_lb` back to `proxy` mode or while the GCLB Managed SSL Certificate is still warming up.)*

### What `deploy.sh` Does:
1. Validates the GCS staging bucket exists (or creates it automatically).
2. Packages clean relative imports (`antigravity_quota_concierge`) without host path pollution.
3. Sets `GOOGLE_CLOUD_LOCATION="global"` and `CONCIERGE_MODEL="gemini-3.5-flash"` in runtime `env_vars`.
4. Deploys the `AntigravityConciergeAdkApp` via `vertexai.preview.reasoning_engines.ReasoningEngine.create`.
5. Patches `spec.agent_framework = "google-adk"` via Vertex AI API so the Cloud Console playground is unlocked.
6. Writes output metadata to `concierge-agent/deployment_metadata.json`.

---

## 6. Step 4: Live Remote Verification

Verify the deployed Reasoning Engine directly on Vertex AI:
```bash
cd concierge-agent
./test_remote_agent.py
```
This script executes queries against the live Vertex AI Reasoning Engine endpoint to verify quota diagnostics, model spend coaching, and sub-agent routing.

---

## 7. Step 5: Publishing to Gemini Enterprise (Stage 3)

Publish the verified Reasoning Engine to Gemini Enterprise using `agents-cli`:

```bash
# List available Gemini Enterprise apps
agents-cli publish gemini --list

# Publish the agent
agents-cli publish gemini \
  --metadata-file concierge-agent/deployment_metadata.json \
  --app-id "your-gemini-enterprise-app-id" \
  --display-name "Antigravity Quota Concierge" \
  --description "Check your Antigravity weekly quota status, get model efficiency tips, and request temporary quota increases."
```

Once published, the agent appears in Gemini Enterprise chat for authorized enterprise users.

---

## 8. Step 6: End-to-End Verification Walkthrough

1. **Employee Interaction (Gemini Enterprise):**
   - Open Gemini Enterprise chat with **Antigravity Quota Concierge**.
   - Type: *"Why is my Antigravity not working?"*
   - Verify that the agent reports current spend, quota limits, and reset countdown.
   - Reply: *"Yes"* to request an increase.
   - Select: *"Option 2 for a sprint deadline on the checkout service"*.
   - Verify that the agent submits the request and returns a Request ID (`req-...`).

2. **Admin Review (Antigravity Admin Console):**
   - Open the Antigravity Admin Console web portal.
   - Navigate to the **Quota Increase Requests** tab.
   - Click the **Refresh icon (`↻`)** to refresh the queue.
   - Verify the request displays under the **Pending** badge with the employee's corporate email, requested quota, and justification.
   - Click **Approve** or **Reject** to complete the governance loop.

---

## 9. CI/CD & Automated Verification

- **GitHub Actions:** [`.github/workflows/concierge-agent-ci.yml`](../.github/workflows/concierge-agent-ci.yml) triggers on changes to `concierge-agent/**`, running the full unit test suite and dry-run deployment validation.
- **Google Cloud Build:** [`concierge-agent/cloudbuild.yaml`](cloudbuild.yaml) supports automated builds on Google Cloud Build:
  ```bash
  gcloud builds submit concierge-agent --config=concierge-agent/cloudbuild.yaml
  ```
