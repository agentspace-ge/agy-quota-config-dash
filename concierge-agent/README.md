# Antigravity Quota Concierge (Gemini Enterprise ADK Multi-Agent)

**Antigravity Quota Concierge** (`antigravity_quota_concierge`) is an optional, self-contained **Google Agent Development Kit (ADK)** multi-agent package designed for large enterprise Gemini Enterprise deployments (15,000+ licenses). It lives in its own isolated sub-project directory (`concierge-agent/`) so the main Antigravity Quota Portal container (`Dockerfile` and root `pyproject.toml`) remains 100% free of ADK dependencies unless you opt in to deploying the agent.

---

## What Employees Can Ask the Concierge

| User Journey | Example Employee Prompt | Agent & Tool Invoked |
| :--- | :--- | :--- |
| **1. Access & Quota Diagnostics** | *"Why is my Antigravity not working?"* | `antigravity_quota_concierge` $\rightarrow$ `get_my_quota_status()` (`GET /api/auth/me`) |
| **2. Model Efficiency & Spend Coaching** | *"Why did my quota run out so fast?"* / *"How can I make my quota last longer?"* | `antigravity_quota_concierge` $\rightarrow$ `get_model_efficiency_insights()` (Frontier Pro vs Flash split) |
| **3. Weekly Reset & Group Tier Check** | *"When does my quota reset?"* / *"Which quota group am I in?"* | `antigravity_quota_concierge` $\rightarrow$ `get_my_quota_status()` (`reset_countdown`, `group_display_name`) |
| **4. Quota Increase Request Submission** | *"Yes"* $\rightarrow$ *"Option 2 for a sprint deadline on checkout service"* | `quota_request_agent` $\rightarrow$ `get_quota_request_options()` & `submit_quota_increase_request()` (`POST /api/quota-requests`) |
| **5. Request Status, Cooldown & Cancellation** | *"What is the status of my quota request?"* / *"Cancel my pending request"* | `quota_request_agent` $\rightarrow$ `get_my_quota_requests()` & `cancel_pending_quota_request()` (`DELETE /api/quota-requests/{id}`) |

> [!NOTE]
> **Strictly Employee-Facing:** The Concierge is designed for developer self-service and FinOps coaching. When managers or administrators ask to approve or reject other employees' requests, the Concierge directs them to the **Antigravity Quota & Usage Management Portal Web Dashboard** (`Quota Increase Requests` tab).

---

## Example Conversation Transcript

**Employee (`alex.morgan@example.com`):**
> Why is my Antigravity not working?

**Antigravity Quota Concierge (`antigravity_quota_concierge`):**
> Your Antigravity access is currently paused because your weekly usage reached $6.04, which exceeds your $6.00 limit. Would you like me to submit an increase request to your manager or administrator?

**Employee:**
> Yes

**Quota Request Specialist (`quota_request_agent`):**
> Here are your quota increase options (current limit: **$6.00/wk** in **Business Users**):
> 1. **+$15.00 Temporary Boost** — New weekly limit: **$21.00/wk** (rest of current week)
> 2. **+$25.00 Temporary Boost (Recommended)** — New weekly limit: **$31.00/wk** (rest of current week)
> 3. **+$50.00 Permanent Upgrade** — New weekly limit: **$56.00/wk** (ongoing weekly limit, or specify a custom amount)
>
> **Reason Categories:** `SPRINT_DEADLINE`, `REFACTORING`, `INCIDENT`, `ROLE_UPGRADE`, `OTHER`
> *(Tip: Full-time software engineers in the default Business Users tier can request Option 3 under `ROLE_UPGRADE`.)*
>
> Which option and reason would you like me to submit?

**Employee:**
> Option 2 for a sprint deadline on the checkout service

**Quota Request Specialist (`quota_request_agent`):**
> Your quota increase request (`req-demo-0001`) to raise your weekly limit from **$6.00** to **$31.00** (Temporary, rest of current week) under `SPRINT_DEADLINE` has been submitted to your manager/administrator for approval. As soon as it is approved, your Antigravity access will be automatically restored.

---

## Quickstart (Stage 1 Local Testing & Demo)

### Option A: Zero-Dependency 1-Command Stage 1 Runner (Recommended)
Starts both the local **Antigravity Quota Portal** (`http://localhost:8080`, serving the React SPA + all `/api/*` endpoints seeded with `alex.morgan@example.com` at `$6.04 / $6.00`) and the interactive **Concierge Web Playground** (`http://localhost:8000`) using only the Python standard library:
```bash
# Run automated 6-turn live HTTP smoke test and exit:
python3 concierge-agent/run_local_stage1.py --smoke-test

# Or start both http://localhost:8080 (Portal) and http://localhost:8000 (Concierge UI):
python3 concierge-agent/run_local_stage1.py
```

### Option B: Run with `adk web` (Full ADK Dev UI)
If you have `uv` / `google-adk` installed in a virtual environment:
```bash
# Terminal 1 — Start the local Portal API (or use run_local_stage1.py)
SEED_CONCIERGE_DEMO_USER=true python3 scripts/run_local_demo.py

# Terminal 2 — Launch adk web
cd concierge-agent
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"

export PORTAL_API_BASE_URL="http://localhost:8080"
export DEFAULT_DEMO_USER_EMAIL="alex.morgan@example.com"
export CONCIERGE_MODEL="gemini-3.5-flash"

adk web .
```

---

## Running Unit Tests & Dry-Run Verification

The unit test suite runs out-of-the-box with zero external GCP calls (14 tests covering schemas, compatibility shims, state namespacing, and task delegation):
```bash
# Run unit tests from workspace root
PYTHONPATH=concierge-agent python3 -m unittest discover -s concierge-agent/tests -p "test_*.py" -v

# Or from inside concierge-agent/
cd concierge-agent
PYTHONPATH=. python3 -m unittest discover -s tests -p "test_*.py" -v

# Validate Vertex AI Agent Engine deployment plan (dry-run)
PYTHONPATH=. python3 -m antigravity_quota_concierge.deploy_agent_engine --dry-run
```

For complete technical specifications, architectural guidelines, and deployment instructions, refer to:
- [SPECIFICATION.md](SPECIFICATION.md): Full technical specification, state schemas, and API contracts.
- [AGENTS.md](AGENTS.md): ADK multi-agent development standards, state namespacing, and task delegation rules.
- [ONBOARDING.md](ONBOARDING.md): Step-by-step Vertex AI Reasoning Engine onboarding and Gemini Enterprise publishing.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): Multi-agent topology and trust model diagrams.

---

## Stage 2: Vertex AI Agent Engine Deployment

Vertex AI Agent Engine (Reasoning Engine) requires a Google Cloud Storage (GCS) staging bucket to store pickled code artifacts during deployment.

### 1. Provisioning the GCS Staging Bucket

#### Option A: Automated via Terraform (Recommended)
[`terraform/storage.tf`](../terraform/storage.tf) defines the staging bucket. When `enable_concierge_agent = true`, running Terraform automatically creates `gs://<project_id>-agent-engine-staging` with uniform bucket-level access and a 30-day lifecycle rule:
```bash
cd terraform
terraform apply -var="project_id=your-gcp-project-id" -var="enable_concierge_agent=true"
```

#### Option B: Manual Creation via gcloud CLI
If deploying the agent before running Terraform, create the bucket manually:
```bash
gcloud storage buckets create gs://your-gcp-project-id-agent-engine-staging \
  --project=your-gcp-project-id \
  --location=us-central1 \
  --uniform-bucket-level-access
```

### 2. Deploying the Agent

#### Turnkey Deployment via `deploy.sh`:
```bash
cd concierge-agent
./deploy.sh \
  --project-id "your-gcp-project-id" \
  --location "us-central1" \
  --staging-bucket "gs://your-gcp-project-id-agent-engine-staging" \
  --portal-api-url "https://quota.demo.example.com" \
  --fallback-cloud-run-url "https://<your-cloud-run-portal-url>" \
  --iap-client-id "YOUR_IAP_OAUTH_CLIENT_ID.apps.googleusercontent.com"
```
*(When `--fallback-cloud-run-url` is set, the Concierge Agent supports seamless bidirectional switching of the Portal between `external_lb` [GCLB + IAP] and `proxy` [Direct Cloud Run IAM] modes without needing to redeploy the agent.)*

Or invoke the Python module directly:
```bash
cd concierge-agent
PYTHONPATH=. .venv/bin/python3 -m antigravity_quota_concierge.deploy_agent_engine \
  --project-id "your-gcp-project-id" \
  --location "us-central1" \
  --staging-bucket "gs://your-gcp-project-id-agent-engine-staging" \
  --portal-api-url "https://<your-cloud-run-portal-url>"
```

### 3. Remote Live Verification via `test_remote_agent.py`
Once deployment completes, verify the live endpoint on Vertex AI Agent Engine:
```bash
cd concierge-agent
./test_remote_agent.py
```
This tests diagnosis and sub-agent routing against the live Reasoning Engine container using persona `alex.morgan@example.com`.

---

## Architecture & Integration Details

### 1. Dynamic Identity Resolution & Anti-Spoofing (`auth.py`)
The Concierge dynamically extracts authenticated employee identity without relying on hardcoded personas or untrusted caller-supplied arguments:
- **Discovery Engine / Gemini Enterprise Sessions:** Extracts `tool_context.user_id`, `tool_context.session.user_id`, or `get_invocation_context().user_id`.
- **OAuth JWT Bearer Claims:** Extracts `email` claim from Google OAuth identity tokens when present.
- **Strict Precedence:** Platform-authenticated identity strictly overrides any unverified user email parameters passed to tools, mitigating Confused Deputy / Insecure Direct Object Reference (IDOR) vectors.

### 2. Portal Backend Ingress & Trust Model (`app/api/deps.py`)
When the Reasoning Engine calls the Antigravity Quota Portal backend:
- **Cryptographic OIDC Verification:** The backend verifies Google-signed OIDC Bearer tokens (`verify_oauth2_token`).
- **Reasoning Engine Service Account Trust:** The portal recognizes the Vertex AI Reasoning Engine service account (`service-<PROJECT_NUMBER>@gcp-sa-aiplatform-re.iam.gserviceaccount.com`) as a trusted proxy.
- **Delegated Caller Identity:** Trusted service accounts are permitted to provide `X-Impersonate-User` headers or payload `user_email` fields to act on behalf of authenticated employees.

### 3. Vertex AI Reasoning Engine Specifics
- **Model Standard:** Configured to use `gemini-3.5-flash` (`CONCIERGE_MODEL="gemini-3.5-flash"`).
- **Global Endpoint Routing:** For deployments in regional locations like `us-central1`, `GOOGLE_CLOUD_LOCATION="global"` is set in the container environment variables so `gemini-3.5-flash` resolves properly.
- **Agent Framework Specification:** When deployed via the Python SDK, `spec.agent_framework = "google-adk"` is patched on the `ReasoningEngine` resource to enable the Vertex AI Agent Engine Console Playground and Gemini Enterprise integration.

### 4. Admin Review Queue Lifecycle
- **Centralized In-Portal Queue:** Quota increase requests submitted through the Concierge are dispatched directly into Firestore and surfaced in the **Antigravity Admin Console** under the **Quota Increase Requests** tab.
- **No External SMTP Needed:** The workflow operates entirely through the web console; administrators review, approve, or reject requests in real time via the dashboard.

### 5. ADK 2.0 Task Delegation Mode (`quota_request_agent`)
- **Discrete Task Protocol:** `quota_request_agent` is configured with `mode="task"` and an explicit Pydantic `output_schema=QuotaRequestTaskOutput`.
- **Deterministic Handoffs:** Rather than remaining in an open-ended conversational loop, the task agent gathers parameters, executes the request via portal REST APIs, populates the typed task output schema, and transfers execution back to `antigravity_quota_concierge`.

### 6. Structured State Control & ADK Namespacing (`schemas.py`, `auth.py`, `tools.py`)
- **Persistent User Scope (`user:*`):** User identity and preferences (`user:email`, `user:preferred_option`, `user:last_reason_category`) are stored in ADK's native `user:` namespace, persisting across sessions.
- **Transient Session Scope:** In-flight request IDs (`active_request_id`) and weekly telemetry limits are kept session-scoped.
- **Dual-Key Backward Compatibility:** Tools read from `user:*` with fallback to legacy plain keys, and write to both namespaces simultaneously to prevent breaking external integrations.
- **Pydantic State Validation:** `ConciergeState` leverages `validation_alias=AliasChoices(...)` and `ConfigDict(populate_by_name=True)` to validate raw `tool_context.state` dictionaries effortlessly.

---

## Roadmap: Enterprise Security & Governance (Stage 3 Feature Request)

Aligned with the [Google Cloud Agentic AI Architecture Overview](https://docs.cloud.google.com/architecture/agentic-ai-overview), the following defense-in-depth capabilities are tracked for Stage 3 Enterprise production hardening:

### Implemented in Stage 2 (Baseline Zero-Trust Foundation)
- **Confused Deputy / IDOR Prevention (`auth.py`)**: Platform-verified `ToolContext` OAuth identity (`auth_response` / session state) strictly takes `#1` precedence over unverified `user_email` tool parameters, preventing horizontal privilege escalation across employees.
- **Cryptographic OIDC Verification (`app/api/deps.py`)**: In production (`USE_MOCK_SERVICES=false`), the Portal verifies Google-signed OIDC Bearer tokens (`google.oauth2.id_token.verify_oauth2_token`) and enforces exact Service Account matching (`CONCIERGE_SERVICE_ACCOUNT_EMAIL`), blocking plaintext header spoofing.
- **Region-Aligned Artifact Staging (`terraform/storage.tf`)**: Dedicated `concierge_agent_region` (`us-central1`) ensures the GCS staging bucket is co-located with the Vertex AI Reasoning Engine resource.
- **Human-in-the-Loop (HITL) Blast-Radius Containment**: The agent cannot self-approve quota increases or mutate Cloud Identity groups; it only creates `PENDING` tickets requiring manager/admin approval in the Portal UI.

### Planned for Stage 3 (Enterprise Feature Request)
1. **Google Cloud Model Armor Integration**:
   - Provision a Model Armor template (`modelarmor.googleapis.com`) to inspect incoming prompts and outgoing tool/model responses for prompt injection, jailbreak attempts, and sensitive data (SDP/PII) leakage before LLM execution.
2. **Deterministic ADK Guardrail Callbacks (`before_tool_callback` & `before_model_callback`)**:
   - Register deterministic pre-execution hooks on `root_agent` and `quota_request_agent` to strip HTML/control characters, cap `justification` length (`<= 500` chars), and enforce strict self-service dollar bounds (`$0 < requested_quota_usd <= $500`) prior to HTTP invocation.
   - Configure explicit `GenerateContentConfig` Vertex AI `SafetySetting` thresholds (`BLOCK_LOW_AND_ABOVE`).
3. **VPC Service Controls (VPC-SC) & Private Service Connect (PSC) Egress**:
   - Place Vertex AI Agent Engine and the Cloud Run Quota Portal inside a shared VPC-SC security perimeter with PSC Private Egress so the Reasoning Engine tenant cannot make arbitrary outbound internet connections.
4. **Dual Audit Trail Attribution (`app/audit/`)**:
   - Record both the acting autonomous agent identity (`delegated_agent = antigravity-concierge@...`) and the human principal (`actor_user = alex.morgan@example.com`) in Cloud Logging and BigQuery audit records for forensic compliance.


