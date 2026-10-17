# Technical Design Document & Feature Specification: Antigravity Quota & Usage Management Portal


**Target Platform**: Google Cloud Platform (Single Always-On Cloud Run Instance, Firestore, BigQuery, Cloud Identity)

---

## 1. Executive Summary & Objective

The **Antigravity Quota & Usage Management Portal** provides fine-grained visibility, credit tracking, cost estimation, and automated access governance for developer access to Google Antigravity (Gemini Enterprise AI Developer Tools).

> [!NOTE]
> **Independent Quota Governance & Upstream Pool Visibility**: Gemini Enterprise enforces subscription quota as a pooled entitlement at the GCP project level. This portal establishes a **two-layer visibility and governance model**:
> 1. **Upstream Subscription Quota Pool**: Direct read-only telemetry from **Google Cloud Monitoring** (`discoveryengine.googleapis.com/quota/ratev2/...`), providing live organizational visibility into subscription license tier, gross Workload Token Unit (WTU) consumption, contract USD value, and the official Google Cloud weekly reset schedule.
> 2. **Per-Developer Allocation & Access Governance**: An independent management layer where administrators define per-developer credit budgets, track estimated usage from BigQuery inference logs, and automate access enforcement via Cloud Identity IAM gatekeeper groups (`antigravity-active@` vs `antigravity-throttled@`).

To minimize architectural complexity and infrastructure overhead, the system is deployed as a **single, always-on minimal Cloud Run instance** (`min-instances: 1`, `max-instances: 1`, 1 vCPU, 512MB RAM). This single instance hosts:
1. **The Web Dashboard & REST API**: Instantaneous page loads with zero cold starts for admin users.
2. **Cloud Monitoring Quota Pool Client**: Maintains an in-memory cache with a 300-second TTL and automatic Firestore fallback, polling live subscription tier and WTU telemetry without burdening GCP quota limits.
3. **The Embedded Background Worker**: Runs an internal scheduler (Python `APScheduler` loop) to evaluate developer quotas hourly and refresh pool statistics, completely eliminating the need for external Cloud Scheduler cron jobs.
4. **Instant Publish Handler**: Exposes an in-process trigger invoked whenever the admin clicks "Publish & Sync" in the UI to immediately reconcile identity groups and refresh pool metrics.

```mermaid
flowchart TD
    subgraph Antigravity ["Antigravity Ingestion & Audit Stream"]
        UserReq["Developer IDE Requests"] --> BAIC["businessaicode.googleapis.com"]
        BAIC -->|"Audit Logs"| LR["Cloud Logging Log Router Sink"]
        LR -->|"Daily Sharded Export"| BQ_SHARDS[("BigQuery Date Shards\n(inference_response_YYYYMMDD)")]
        BQ_SHARDS -->|"Terraform Unified View"| BQ[("BigQuery View\n(businessaicode_inference_response)")]
    end

    subgraph SubscriptionPool ["Upstream Subscription Telemetry"]
        CM["Google Cloud Monitoring\n(discoveryengine.googleapis.com/quota/ratev2)"]
    end

    subgraph AccessLayer ["Admin Access & Network Ingress"]
        AdminBrowser["Admin Browser\n(http://localhost:8080)"] <-->|"gcloud auth identity"| ProxyBridge["Local IAM Proxy Bridge\n(portal_access.sh proxy)"]
        ProxyBridge <-->|"Bearer Token (IAM Auth)"| WebApp
    end

    subgraph SingleContainer ["Single Always-On Cloud Run Instance (min=1, max=1)"]
        direction TB
        WebApp["FastAPI Web Server\n(Cloud Run in us-east5)"]
        EmbeddedCron["Internal Hourly Scheduler\n(APScheduler loop)"] -->|"Hourly Trigger"| Evaluator["In-Memory Evaluator Worker"]
        WebApp -->|"Publish Button Click"| Evaluator
        PoolClient["Cloud Monitoring Pool Client\n(300s TTL Cache & DB Fallback)"]
        WebApp --> PoolClient
        Evaluator --> PoolClient
    end

    PoolClient -->|"Query Subscription Pool (WTU/Tier)"| CM

    subgraph ExternalBackends ["GCP & Identity Services"]
        Evaluator -->|"Extract Weekly Tokens"| BQ
        Evaluator <-->|"Read/Write Settings, Spend & Pool Cache"| FS[("Google Cloud Firestore")]
        Evaluator -->|"Dual-Write Audit Logs"| CL_AUDIT[("Cloud Logging\nantigravity-quota-audit")]
        Evaluator -->|"Reconcile Memberships"| CI_API["Cloud Identity Directory API"]
        CI_API --> G_EN["antigravity-active@\n(Bound to roles/businessaicode.user)"]
        CI_API --> G_DIS["antigravity-throttled@\n(Throttled / Paused Users)"]
    end
```

---

## 2. Financial Ledger, Cost Calculation & Credit Mechanics

### 2.1 The Credit vs. Net Cost Model
In Antigravity enterprise deployments, user quotas are distributed as **credit allocations**. To provide accurate FinOps reporting, the system calculates both gross usage and net liability:

1. **Gross Estimated Cost ($C_{\text{gross}}$)**:
   $$\text{Blended Rate Per 1M Tokens } (R_{\text{blended}}) = (w_{\text{in}} \cdot P_{\text{in}}) + (w_{\text{out}} \cdot P_{\text{out}}) + (w_{\text{cache}} \cdot P_{\text{cache}})$$
   $$C_{\text{gross}} = \frac{T_{\text{total}} \times R_{\text{blended}}}{1,000,000}$$

2. **Allocated Quota Credits ($Q$)**:
   The weekly credit amount granted to the developer (e.g. \$10.00).

3. **Remaining Credit Balance ($B_{\text{credit}}$)**:
   $$B_{\text{credit}} = \max(0, Q - C_{\text{gross}})$$

4. **Net Cost / Developer Overage ($C_{\text{net}}$)**:
   $$C_{\text{net}} = \max(0, C_{\text{gross}} - Q)$$
   *(Note: Because Gemini Enterprise utilizes pooled project-level quotas, $C_{\text{net}}$ measures an individual developer's consumption exceeding their allocated quota target, rather than external GCP billing liability.)*

5. **Throttling Condition**:
   A user exceeds allowed usage when their Gross Cost exceeds their Quota Credits plus their allowed Overage Buffer ($O$):
   $$\text{Throttled if: } C_{\text{gross}} \ge Q + O \quad \iff \quad C_{\text{net}} \ge O$$

### 2.2 Global Estimation Disclaimer
To avoid visual clutter while maintaining legal/accounting compliance, the application features a **single, prominent disclaimer banner** pinned to the dashboard header / footer:

> ℹ️ **Estimation Notice**: *All token breakdowns, cost calculations, credit balances, and spend metrics displayed in this portal are estimated projections calculated from raw token counts and configured model pricing assumptions.*

### 2.3 Upstream Subscription Quota Pool Mechanics (Cloud Monitoring)

While Section 2.1 governs internal developer credit allocations, the organization's overarching entitlement is governed by its Gemini Enterprise contract tier. The portal interfaces with **Google Cloud Monitoring API v3** to track and display this upstream quota pool:

1. **Upstream Quota Metrics**:
   - Usage: `discoveryengine.googleapis.com/quota/ratev2/net_usage`
   - Limit: `discoveryengine.googleapis.com/quota/ratev2/limit`
   - Evaluated across subscription tiers via `metric.label.quota_metric_name`:
     - **`agentic_wtu_tier_enterprise_plus_pp_weekly_regional`**: Gemini Enterprise Plus (37.5M WTU limit, \$75.00 contract value at \$2.00 / 1M WTU).
     - **`agentic_wtu_tier_enterprise_standard_pp_weekly_regional`**: Gemini Enterprise Standard (40M WTU limit, \$80.00 contract value).
     - **`agentic_wtu_tier_consumption_only_pp_weekly_regional`**: Consumption-Only / Flex.

2. **Official Reset Cycle & Countdown**:
   - The upstream quota engine defines the start of each weekly window via the metric point label `window_start_time` (epoch seconds).
   - Window Start: $T_{\text{window\_start}} = \text{datetime.fromtimestamp}(\text{window\_start\_time})$.
   - Next Weekly Reset: $T_{\text{next\_reset}} = T_{\text{window\_start}} + 7 \text{ days}$.
   - Countdown Duration: $T_{\text{remaining}} = \max(0, T_{\text{next\_reset}} - T_{\text{now}})$, formatted dynamically as `Weekly Pool Resets in: Xd Xh` (or `Resetting soon` when $T_{\text{remaining}} \le 0$).
   - **Cross-Series Reduction & Aggregation Guard**: Cloud Monitoring unaggregated queries over multi-day windows return high volumes of 1-minute time series points, causing GCP API pagination where newly created weekly time series can be truncated on subsequent pages. To guarantee that the active cycle is never dropped, the client employs `ALIGN_MAX` and `REDUCE_MAX` aggregated across series grouped by `metric.label.window_start_time`, with a secondary fallback to an unaggregated recent 24-hour window.

3. **In-Memory Caching & Firestore Resiliency**:
   - High-frequency web UI polling is shielded by a **300-second in-memory TTL cache** in `CloudMonitoringPoolClient`.
   - On every successful upstream read, current metrics are mirrored to Firestore document `config/credit_pool`.
   - If Cloud Monitoring queries fail due to quota limits or transient network issues, the client transparently returns the last valid Firestore snapshot.

---

## 3. Quota Management Groups Architecture

### 3.1 Overview & Architecture Rationale
In enterprise organizations running Gemini Enterprise at scale (e.g. 15,000+ developer licenses), setting and updating credit quotas per individual developer becomes an operational bottleneck. 

To solve this, the portal introduces **Quota Management Groups**. Quota Management Groups allow FinOps administrators to group developers by business role, department, or engineering unit and apply quota budgets and overage buffers uniformly at the group level.

#### Critical Distinction: Quota Groups vs. IAM Gatekeeper Groups
It is essential to distinguish between the two layers of groups in the portal:
1. **IAM Gatekeeper Groups (Access Control Enforcers)**:
   - Specific Cloud Identity groups (`antigravity-active@` and `antigravity-throttled@`).
   - `antigravity-active@` is bound to GCP IAM role `roles/businessaicode.user`.
   - `antigravity-throttled@` has zero IAM permissions.
   - The quota evaluator swaps developers between these two gatekeeper groups based on hard quota breaches or manual administrative holds.
2. **Quota Management Groups (Spend Budget Policies)**:
   - Logical organizational groups stored in Firestore (`quota_groups` collection).
   - Define baseline weekly quota credits (`weekly_quota_usd`), overage buffer (`overage_buffer_usd`), and exemption status (`is_exempt`).
   - Optionally map to an enterprise IAM / Google Workspace group email (`iam_group_email`) for directory audit and upcoming automated member sync.

### 3.2 3-Tier Policy Inheritance & Resolution Precedence
When the evaluator evaluates a developer's allowed usage, it computes their effective quota according to a strict 3-tier hierarchy:

$$\text{User Custom Quota} \succ \text{Group Quota} \succ \text{Organization Global Default}$$

```mermaid
flowchart TD
    Start["Determine Developer Quota & Buffer"] --> CheckUser{"User has custom quota override?\n(has_custom_quota = true)"}
    CheckUser -->|Yes| ApplyUser["Apply User Custom Quota & Buffer\n(user.custom_quota_usd, user.custom_overage_usd)"]
    CheckUser -->|No| CheckGroup{"User belongs to a Quota Group?\n(user.group_id is set & exists)"}
    CheckGroup -->|Yes| ApplyGroup["Inherit Group Quota & Buffer\n(group.weekly_quota_usd, group.overage_buffer_usd)"]
    CheckGroup -->|No| ApplyGlobal["Fall Back to Organization Defaults\n(config.default_weekly_quota_usd, config.default_overage_buffer_usd)"]
```

### 3.3 Default Seeded Groups
On database initialization, the portal automatically seeds two standard enterprise quota groups:
1. **Developers (`developers`)**:
   - `display_name`: "Developers"
   - `description`: "Core engineering and technical staff requiring higher quota allowances"
   - `weekly_quota_usd`: \$50.00 / week
   - `overage_buffer_usd`: \$10.00 / week
   - `is_exempt`: `false`
2. **Business Users (`business-users`)**:
   - `display_name`: "Business Users"
   - `description`: "General enterprise users with standard weekly quota allowances"
   - `weekly_quota_usd`: \$10.00 / week
   - `overage_buffer_usd`: \$2.00 / week
   - `is_exempt`: `false`
   - *Protected Default*: Automatically assigned to newly discovered developers from BigQuery inference logs; cannot be deleted via the API or UI.

### 3.4 Group Exemption Inheritance
If a Quota Management Group is marked with `is_exempt = true`, all members of that group automatically inherit exemption from auto-throttling, even if their individual `user.is_exempt` flag is `false`:

$$\text{Effective Exemption} = \text{user.is\_exempt} \lor \text{group.is\_exempt}$$

Exempt developers continue to have their exact token usage and financial spend tracked in dashboards and audit logs, but the evaluator will never swap them into `antigravity-throttled@`.

### 3.5 Group Management REST API
The backend exposes comprehensive CRUD and membership management endpoints under `/api/groups`:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/groups` | List all quota groups with computed member count, aggregate spend, and token volume. |
| `POST` | `/api/groups` | Create a new custom quota group with baseline quota and overage buffer. |
| `GET` | `/api/groups/{group_id}` | Retrieve details and live membership statistics for a specific quota group. |
| `PATCH` | `/api/groups/{group_id}` | Update group display name, description, quota, buffer, exemption, or IAM email (auto-propagates to all inherited members). |
| `DELETE` | `/api/groups/{group_id}` | Delete a custom group. Members are safely reassigned to `business-users`. (`business-users` cannot be deleted). |
| `POST` | `/api/groups/{group_id}/members` | Bulk assign developers to the specified group with optional custom quota override reset. |

#### Bulk Member Assignment & Quota Reset Engine
When assigning developers to a group via `POST /api/groups/{group_id}/members`:
```json
{
  "emails": ["alice@company.com", "bob@company.com"],
  "action": "add",
  "reset_custom_quota": true
}
```
- **`action`**: `"add"` (appends users to the group) or `"replace"` (sets the exact membership list, safely reassigning unlisted members back to `business-users`).
- **`reset_custom_quota`** (default `true`):
  - Clears `has_custom_quota = false`, `custom_quota_usd = null`, `custom_overage_usd = null`.
  - Recalculates effective weekly credits, overage buffers, and utilization percentage against the new group's baseline.
  - **Auto-Restoration**: If an assigned user was previously `AUTO_DISABLED` due to exceeding an old custom or default limit, the engine automatically checks if their current spend is within the new group quota and restores their status to `ACTIVE`.
  - If set to `false`, pre-existing per-user custom quotas are preserved.

In addition, `/api/users` supports filtering by group via `GET /api/users?group_id={group_id}`, and developer updates via `PATCH /api/users/{email}` accept `group_id` with immediate effective quota re-evaluation.

### 3.6 Two-Tab Dashboard UI & Roster Pagination
The web UI is organized into two primary tabs:
1. **Users Tab**:
   - Filterable, sortable developer roster with color-coded credit utilization progress bars.
   - Quota Group chip displayed on each row (`Developers`, `Business Users`, or custom groups).
   - Dedicated Group Filter dropdown in the toolbar to isolate members of any group.
   - **Quota Policy Filter Dropdown**: Filter roster by `All Quota Types`, `Group Inherited` (members adopting group baselines), or `Custom Overrides` (members with individual caps).
   - Client-side pagination (`TablePagination`) supporting 10, 25, 50, and 100 developers per page to maintain performance with thousands of users.
2. **Groups Tab**:
   - Responsive card grid displaying each Quota Management Group.
   - Real-time aggregate metrics per group: Active Members, Total Weekly Tokens, Gross Spend, and Effective Baseline Quota.
   - Actions to Create, Edit, or Delete quota groups.
   - **Assign Members Action**: Opens a dedicated modal to paste email lists with a pre-selected `[✓] Reset custom quota overrides to group baseline` checkbox.
   - "View Members" navigation button that automatically redirects to the Developers tab with that group pre-filtered.

---

## 4. Core Architecture & Workflow Model

### 4.1 The "Save" vs. "Publish" Admin Lifecycle

To provide operational safety and batch management, administrative actions in the web UI follow a **Deferred Sync with Instant Publish** pattern:

```mermaid
sequenceDiagram
    autonumber
    actor Admin as IT / FinOps Admin
    participant UI as Web UI Dashboard
    participant FS as Cloud Firestore
    participant Worker as Evaluator Worker
    participant BQ as BigQuery Audit
    participant CI as Cloud Identity API

    Admin->>UI: Modify Quotas / Credits / Settings
    Admin->>UI: Click "Save Changes"
    UI->>FS: Persist updated user configs & pricing JSON
    UI-->>Admin: "Changes saved to draft. Click Publish to apply immediately."
    
    opt Immediate Sync Requested
        Admin->>UI: Click "Publish & Sync"
        UI->>Worker: Trigger immediate run via HTTP POST / Cloud Tasks
    end

    alt Hourly Cron OR Publish Triggered
        Worker->>FS: Load App Config, Timezone & Model Pricing Matrix
        Worker->>BQ: Run Weekly Token Aggregation Query (Credit Pool Window Start to Now)
        Worker->>FS: Update User Token Counts, Gross Cost, Net Spend
        Worker->>Worker: Evaluate Status (Active, Auto-Disabled, Manually Disabled, Exempt)
        Worker->>CI: Batch reconcile memberships in Enabled vs Disabled Groups
        Worker->>FS: Write Audit Log & Snapshot State
    end
```

1. **Save Changes**: Persists user quota overrides, overage amounts, exemptions, and model pricing directly to Firestore without immediately invoking external APIs.
2. **Publish & Sync**: Immediately triggers the in-process background evaluator worker to re-run the BigQuery consumption query, re-calculate gross vs. net spend, and reconcile Cloud Identity groups in real-time.
3. **Embedded Scheduled Run**: The container's internal background scheduler (`APScheduler` / `asyncio` loop) triggers the evaluator worker every hour as an automated background safety net without requiring external cron infrastructure.

---

## 5. Dual-Group IAM Gatekeeper State Machine

### 5.1 Group Definitions & IAM Roles

The portal separates **Quota Management Groups** (which define spending budgets) from **IAM Gatekeeper Groups** (which enforce access control). Access enforcement is managed via two designated Cloud Identity groups:

| Group Email | GCP IAM Role Binding | Purpose |
| :--- | :--- | :--- |
| `antigravity-active@yourcompany.com` | `roles/businessaicode.user` | **Active Developers**: Grants permission to run Antigravity inference. |
| `antigravity-throttled@yourcompany.com` | *None* | **Throttled / Paused Developers**: Zero IAM privileges. Tracks all inactive developers for audit and notification lists. |

### 5.2 State Definitions & Transitions

```mermaid
stateDiagram-v2
    [*] --> SYNTHETIC_DISCOVERY : User appears in BigQuery Log
    SYNTHETIC_DISCOVERY --> ACTIVE : Create Firestore Doc (Default Quota)

    state ACTIVE {
        [*] --> UnderQuota : Gross Spend < Quota Credits
        UnderQuota --> WarningPace : Gross Spend >= 80% of Quota
        WarningPace --> HardLimitBreached : Gross Spend >= (Quota + Overage)
    }

    HardLimitBreached --> AUTO_DISABLED : Worker moves user to Disabled Group
    
    state AUTO_DISABLED {
        [*] --> ThrottledInDisabledGroup : Incurred Net Overages
    }

    AUTO_DISABLED --> ACTIVE : Weekly Credit Pool Auto-Reset (Gross Spend resets to $0)
    AUTO_DISABLED --> ACTIVE : Admin increases Quota Credits & Publishes
    
    ACTIVE --> MANUALLY_DISABLED : Admin toggles "Disable Access" in UI
    AUTO_DISABLED --> MANUALLY_DISABLED : Admin locks user manually
    MANUALLY_DISABLED --> ACTIVE : Admin toggles "Enable Access" in UI

    ACTIVE --> EXEMPT : Admin sets is_exempt = true
    EXEMPT --> ACTIVE : Admin removes exemption
```

### 5.3 State Matrix & Evaluator Action Rules

| State / Flag | Group Location | Evaluator Action on Quota Breach | Weekly Pool Reset Behavior |
| :--- | :--- | :--- | :--- |
| **`ACTIVE`** (`is_exempt: false`) | `antigravity-active@` | If `C_gross >= Q + O`: Move to `antigravity-throttled@`, set state to `AUTO_DISABLED`. | Reset weekly gross token spend to `$0.00`. Credit balance resets to `Q`. Remain in `antigravity-active@`. |
| **`AUTO_DISABLED`** | `antigravity-throttled@` | User is throttled. If Admin increases `Q` such that `C_gross < Q + O`: Move to `antigravity-active@`, set state to `ACTIVE`. | **Auto-Re-enable**: Move user back to `antigravity-active@`, set state to `ACTIVE`. |
| **`MANUALLY_DISABLED`** | `antigravity-throttled@` | Manual lock. Evaluator never modifies group. | **Protected**: Ignored by weekly pool reset. User remains in `antigravity-throttled@`. |
| **`is_exempt: true`** | `antigravity-active@` | Quota checks bypassed. Usage is tracked and displayed, but user is never throttled. | Reset weekly counters. User remains in `antigravity-active@`. |

### 5.4 Automated Cloud Identity Group Provisioning (Terraform)

To eliminate manual directory setup, group creation and permission delegation are fully automated via Terraform ([`terraform/cloud_identity.tf`](terraform/cloud_identity.tf)):

1. **Group Provisioning (`google_cloud_identity_group`)**:
   - `antigravity-active@<domain>`: Tagged with `cloudidentity.googleapis.com/groups.discussion_forum`.
   - `antigravity-throttled@<domain>`: Tagged with `cloudidentity.googleapis.com/groups.discussion_forum`.
   - Configurable via `create_cloud_identity_groups = true/false` flag to support pre-existing groups.
2. **Access Entitlement (`google_project_iam_member`)**:
   - Automatically binds `roles/businessaicode.user` directly to `group:antigravity-active@<domain>`.
   - The disabled group receives no project IAM roles.
3. **Least-Privilege Group Delegation (`google_cloud_identity_group_membership`)**:
   - The Cloud Run Portal Service Account (`antigravity-quota-portal@<project>.iam.gserviceaccount.com`) is assigned roles `["MEMBER", "OWNER"]` scoped strictly inside both groups.
   - This eliminates the need for project-level IAM Admin privileges or organization-wide Super Admin credentials; the service account can only modify memberships within these two designated groups.

---

## 6. Token Cost Modeling Engine & "Hinge Points"

### 6.1 Per-Model Configuration Schema

```json
{
  "models": {
    "gemini-3-pro": {
      "display_name": "Gemini 3.1 Pro / 3.0 Pro",
      "log_pattern": "%3%pro%",
      "input_price_per_million": 1.25,
      "output_price_per_million": 5.00,
      "cached_price_per_million": 0.30,
      "estimated_input_ratio": 0.70,
      "estimated_output_ratio": 0.20,
      "estimated_cached_ratio": 0.10
    },
    "gemini-2.5-pro": {
      "display_name": "Gemini 2.5 Pro",
      "log_pattern": "%2.5%pro%",
      "input_price_per_million": 1.25,
      "output_price_per_million": 5.00,
      "cached_price_per_million": 0.30,
      "estimated_input_ratio": 0.70,
      "estimated_output_ratio": 0.20,
      "estimated_cached_ratio": 0.10
    },
    "gemini-3.5-flash": {
      "display_name": "Gemini 3.5 Flash",
      "log_pattern": "%3.5%flash%",
      "input_price_per_million": 0.15,
      "output_price_per_million": 0.60,
      "cached_price_per_million": 0.0375,
      "estimated_input_ratio": 0.75,
      "estimated_output_ratio": 0.20,
      "estimated_cached_ratio": 0.05
    },
    "gemini-3.8-flash": {
      "display_name": "Gemini 3.8 Flash (Antigravity Default)",
      "log_pattern": "%3.8%flash%",
      "input_price_per_million": 0.075,
      "output_price_per_million": 0.30,
      "cached_price_per_million": 0.01875,
      "estimated_input_ratio": 0.80,
      "estimated_output_ratio": 0.15,
      "estimated_cached_ratio": 0.05
    },
    "gemini-3.6-flash": {
      "display_name": "Gemini 3.6 / 3.7 Flash",
      "log_pattern": "%3.6%flash%",
      "input_price_per_million": 0.075,
      "output_price_per_million": 0.30,
      "cached_price_per_million": 0.01875,
      "estimated_input_ratio": 0.80,
      "estimated_output_ratio": 0.15,
      "estimated_cached_ratio": 0.05
    },
    "gemini-2.5-flash": {
      "display_name": "Gemini 2.5 Flash",
      "log_pattern": "%2.5%flash%",
      "input_price_per_million": 0.075,
      "output_price_per_million": 0.30,
      "cached_price_per_million": 0.01875,
      "estimated_input_ratio": 0.80,
      "estimated_output_ratio": 0.15,
      "estimated_cached_ratio": 0.05
    },
    "default_fallback": {
      "display_name": "Default Model Fallback",
      "log_pattern": "default",
      "input_price_per_million": 0.15,
      "output_price_per_million": 0.60,
      "cached_price_per_million": 0.0375,
      "estimated_input_ratio": 0.75,
      "estimated_output_ratio": 0.20,
      "estimated_cached_ratio": 0.05
    }
  }
}
```

---

## 7. Timezone & Weekly Boundary Engine

### 7.1 Credit Pool Window Alignment & Timezone Normalization
* **Upstream Synchronization**: Weekly usage and quota evaluation windows align with the upstream Google Cloud Credit Pool start timestamp (`window_start_utc` from Cloud Monitoring `ratev2` quota telemetry).
* **7-Day Dynamic Cycle**: The quota evaluation window runs for 7 days ($T_{\text{next\_reset}} = T_{\text{window\_start}} + 7 \text{ days}$).
* **Monotonic Reset Guard**: The evaluator only triggers a cycle rollover when a new `window_start_utc` is at least 5 days newer than the previous cycle, preventing mid-week churn or calendar day mismatch.
* **Portal Display Timezone**: The application stores a configurable timezone (e.g. `America/Los_Angeles`, `America/New_York`, or `UTC`). It formats user interface timestamps and serves as a deterministic fallback (Monday 00:00:00 to Sunday 23:59:59) if upstream Cloud Monitoring metrics are unavailable.

### 7.2 Date-Sharded Log Export & Consolidated BigQuery View

The Cloud Logging sink writes inference logs to BigQuery in date-sharded tables (`businessaicode_googleapis_com_inference_response_YYYYMMDD`). To enable uninterrupted queries across week boundaries without requiring table-partitioning restructuring:
1. **Terraform-Managed View**: A BigQuery view named `businessaicode_googleapis_com_inference_response` is provisioned across all table shards:
   ```sql
   CREATE OR REPLACE VIEW `{{PROJECT_ID}}.{{DATASET_NAME}}.businessaicode_googleapis_com_inference_response` AS
   SELECT * FROM `{{PROJECT_ID}}.{{DATASET_NAME}}.businessaicode_googleapis_com_inference_response_*`;
   ```
2. **Wildcard Fallback**: Application queries in [`app/bq/bq_client.py`](app/bq/bq_client.py) target `{self.project_id}.{self.dataset_name}.businessaicode_googleapis_com_inference_response*`, supporting both the unified view and raw wildcard table matches.

### 7.3 Structured Telemetry Payload (`metadata`)

Every log entry under `businessaicode.googleapis.com/inference_response` contains a structured JSON payload:

```json
{
  "timestamp": "2026-10-08 18:09:45.800408 UTC",
  "labels": {
    "user_id": "user:developer@company.com",
    "model": "gemini-3.8-flash",
    "request_id": "893c834a-9eef-4f6c-8472-a8c7df3158c8",
    "trajectory_id": "400ad99f-7f72-4d5f-9f79-6ea43a18e03e"
  },
  "jsonpayload_v1_inferenceresponselog": {
    "metadata": {
      "totaltokencount": 107315,
      "prompttokencount": 106636,
      "candidatestokencount": 193,
      "thoughtstokencount": 486,
      "cachedcontenttokencount": 101525,
      "quotatype": "REGULAR_QUOTA"
    }
  }
}
```

Key telemetry fields parsed by the evaluator:
* **`totaltokencount`**: Full token volume per interaction.
* **`prompttokencount`**: Prompt/input tokens.
* **`candidatestokencount`**: Completion/output response tokens.
* **`thoughtstokencount`**: Internal chain-of-thought/reasoning tokens.
* **`cachedcontenttokencount`**: Context cache savings.
* **`quotatype`**: Quota type flag (`REGULAR_QUOTA`).

### 7.4 BigQuery Parametrized Extraction Query

```sql
-- Parametrized BigQuery Usage Aggregation
-- @start_timestamp_utc and @end_timestamp_utc are calculated from Credit Pool Window (window_start_utc to Now)
WITH raw_events AS (
  SELECT
    timestamp,
    REPLACE(labels.user_id, 'user:', '') AS user_email,
    COALESCE(labels.model, 'gemini-3.8-flash') AS model_name,
    COALESCE(
      SAFE_CAST(jsonpayload_v1_inferenceresponselog.metadata.totalTokenCount AS INT64),
      SAFE_CAST(jsonpayload_v1_inferenceresponselog.metadata.totaltokencount AS INT64),
      0
    ) AS total_tokens
  FROM
    `{{PROJECT_ID}}.{{DATASET_NAME}}.businessaicode_googleapis_com_inference_response*`
  WHERE
    timestamp >= @start_timestamp_utc
    AND timestamp <= @end_timestamp_utc
)
SELECT
  user_email,
  model_name,
  COUNT(1) AS request_count,
  SUM(total_tokens) AS token_count,
  MAX(timestamp) AS last_active
FROM
  raw_events
WHERE
  user_email IS NOT NULL
  AND NOT ENDS_WITH(user_email, '.gserviceaccount.com')
GROUP BY
  user_email,
  model_name;
```

---

## 8. Firestore Database Schema

Firestore stores the application settings, user configurations, quota management groups, weekly consumption, credit ledgers, and upstream subscription quota pool cache.

```mermaid
erDiagram
    CONFIG_SETTINGS ||--o{ MODEL_PRICING : contains
    CONFIG_SETTINGS ||--|| CREDIT_POOL_CACHE : contains
    QUOTA_GROUPS ||--o{ USERS : classifies
    USERS ||--o{ AUDIT_EVENTS : tracks
    USERS ||--o{ WEEKLY_SNAPSHOTS : archives

    CONFIG_SETTINGS {
        string doc_id "app_config"
        string timezone "America/Los_Angeles"
        string enabled_group "antigravity-active@company.com"
        string disabled_group "antigravity-throttled@company.com"
        decimal default_quota_usd "10.00"
        decimal default_overage_usd "2.00"
        array preset_quotas "[10, 15, 25, 50, 100]"
        string webhook_alert_url "https://chat.googleapis.com/..."
        datetime last_publish_timestamp
    }

    CREDIT_POOL_CACHE {
        string doc_id "credit_pool"
        string tier_key "plus"
        string tier_name "Gemini Enterprise Plus"
        int64 usage_wtu "5106993"
        int64 limit_wtu "37500000"
        decimal usage_usd "10.21"
        decimal limit_usd "75.00"
        decimal utilization_pct "13.6"
        datetime window_start_utc "2026-10-10T15:17:05Z"
        datetime next_reset_utc "2026-10-17T15:17:05Z"
        datetime last_synced_at "2026-10-10T16:19:55Z"
    }

    QUOTA_GROUPS {
        string group_id PK "developers / business-users"
        string display_name "Developers"
        string description "Engineering staff"
        decimal weekly_quota_usd "50.00"
        decimal overage_buffer_usd "10.00"
        boolean is_exempt "false"
        string iam_group_email "devs@company.com"
        datetime created_at
        datetime updated_at
    }

    USERS {
        string email PK "alice@company.com"
        string group_id FK "business-users"
        string status "ACTIVE | AUTO_DISABLED | MANUALLY_DISABLED"
        boolean is_exempt "false"
        boolean has_custom_quota "false"
        decimal custom_quota_usd "15.00"
        decimal custom_overage_usd "3.00"
        datetime first_seen_at
        datetime last_evaluated_at
        object current_week_usage
    }

    WEEKLY_SNAPSHOTS {
        string week_id PK "2026-W35"
        decimal final_tokens
        decimal final_gross_cost_usd
        decimal final_quota_credits_usd
        decimal final_net_cost_usd
        string final_status
    }

    AUDIT_EVENTS {
        string event_id PK
        datetime timestamp
        string action "GROUP_SWAP | QUOTA_UPDATE | PUBLISH_TRIGGERED"
        string triggered_by "SYSTEM_WORKER | admin@company.com"
        string details
    }
```

### 8.1 Firestore User Document (`users/{user_email}`)

```json
{
  "email": "alice@yourcompany.com",
  "group_id": "developers",
  "status": "ACTIVE",
  "is_exempt": false,
  "has_custom_quota": true,
  "custom_quota_usd": 20.00,
  "custom_overage_usd": 5.00,
  "current_week": {
    "week_id": "2026-W35",
    "window_start_utc": "2026-08-24T15:17:05Z",
    "total_tokens": 3450000,
    "total_requests": 240,
    "gross_spend_usd": 14.85,
    "quota_credits_usd": 20.00,
    "remaining_credit_usd": 5.15,
    "net_billable_cost_usd": 0.00,
    "overage_buffer_usd": 5.00,
    "spend_breakdown": {
      "input_spend_usd": 10.40,
      "output_spend_usd": 3.85,
      "cached_spend_usd": 0.60
    },
    "tokens_by_model": {
      "gemini-3-pro": 2500000,
      "gemini-3.6-flash": 950000
    },
    "credit_utilization_percentage": 74.25,
    "last_active": "2026-08-27T11:42:10Z"
  },
  "created_at": "2026-08-01T09:00:00Z",
  "updated_at": "2026-08-27T12:00:00Z"
}
```

### 8.2 Firestore Credit Pool Cache Document (`config/credit_pool`)

Persists the latest upstream Google Cloud Monitoring subscription pool metrics to provide instant dashboard loads and offline/rate-limit fallback:

```json
{
  "tier_key": "plus",
  "tier_name": "Gemini Enterprise Plus",
  "usage_wtu": 5106993,
  "limit_wtu": 37500000,
  "usage_usd": 10.21,
  "limit_usd": 75.00,
  "utilization_pct": 13.6,
  "window_start_utc": "2026-10-10T15:17:05Z",
  "next_reset_utc": "2026-10-17T15:17:05Z",
  "last_synced_at": "2026-10-10T16:19:55.420160Z"
}
```

### 8.3 Firestore Quota Group Document (`quota_groups/{group_id}`)

Persists organizational spend groups, default quotas, and group-level exemptions:

```json
{
  "group_id": "developers",
  "display_name": "Developers",
  "description": "Core engineering and technical staff requiring higher quota allowances",
  "weekly_quota_usd": 50.00,
  "overage_buffer_usd": 10.00,
  "is_exempt": false,
  "iam_group_email": "developers@yourcompany.com",
  "created_at": "2026-10-11T12:00:00Z",
  "updated_at": "2026-10-11T12:00:00Z"
}
```

---

## 9. Web Application UI/UX Specification

### 9.1 Navigation Tabs & Top Banner
The dashboard navigation features top-level Material UI tabs:
1. **Users**: Real-time developer governance table, filters, pagination, and slide-out user management drawer.
2. **Groups**: Card-grid view of all quota management groups, live aggregate statistics, and group baseline editing dialogs.

A single global estimation disclaimer is pinned at the top of the portal below the application header:
> *"ℹ️ All token breakdown percentages, gross spend figures, credit balances, and net cost metrics are estimated projections calculated from raw token telemetry logs and configured model pricing assumptions."*

### 9.2 Upstream Hero Widget: Organization Quota Pool Card
Positioned prominently above the primary tabs, this hero component renders live upstream contract entitlement data fetched from Google Cloud Monitoring:
* **Header & Identity**:
  * Cloud Icon + Title: **`Organization Quota Pool`**
  * Tier Badge: **`Tier: Gemini Enterprise Plus`** (or Standard / Flex)
  * Information Tooltip: Clarifies that this card represents the upstream Google Cloud Subscription Quota Pool from Cloud Monitoring, distinct from internal developer credit targets.
* **Cycle Countdown & Timestamps**:
  * Countdown Pill: **`Weekly Pool Resets in: Xd Xh`** (e.g. `Weekly Pool Resets in: 6d 22h`)
  * Dual Timestamps: Displays exact reset moment in both UTC and local browser time (e.g. `Oct 17, 15:17 UTC · Oct 17, 11:17 Local`).
* **Dual Consumption Metrics**:
  * Primary Spend: **`$10.21 / $75.00 limit`** with color-coded utilization indicator (`13.6% utilized`).
  * Secondary WTU Raw Tokens: **`5,106,993 / 37,500,000 WTU (5.11M / 37.50M)`**.
* **Progress Bar**: Multi-stage visual progress bar with smooth transitions (Emerald `<80%`, Amber `80-100%`, Rose `>100%`).

### 9.3 Internal FinOps KPI Summary Cards
Six summary cards reflecting internal user credit allocations and BigQuery telemetry:
* `Active Users`: Number of users in `ACTIVE` status.
* `Throttled`: Number of users currently paused in `antigravity-throttled@`.
* `Tokens This Week`: Total weekly token volume (e.g. `53.54M`).
* `Total Spend`: Aggregated user token spend across all models (e.g. `$6.48`).
* `Allocated Quota`: Sum of all granted user quotas (e.g. `$23.00`).
* `Net Overages`: Cumulative spend exceeding individual quotas (e.g. `$0.88`).

### 9.4 Developer Governance Table (Tab 1)

| Column Name | Data Type | Sortable | Display / Visual Elements |
| :--- | :--- | :---: | :--- |
| **User** | String | Yes | Gravatar/Avatar + Developer Email (`user@company.com`) |
| **Group** | String | Yes | Colored chip with Quota Group display name (e.g. `Developers` or `Business Users`) |
| **Status** | Enum | Yes | 🟢 `Active` \| 🟡 `Warning (>80%)` \| 🔴 `Auto-Throttled` \| 🔒 `Locked` \| ⚪ `Exempt` |
| **Total Tokens** | Integer | Yes | Formatted with commas (`3,450,000`) |
| **Gross Usage** | Currency | Yes | **$14.85** *(Total token value)* |
| **Quota Credits** | Currency | Yes | **$20.00** *(Granted allowance)* |
| **Credit Balance / Net Overage** | Currency | Yes | If `C_gross <= Q`: **$5.15 Left** 🟢<br>If `C_gross > Q`: **+$2.40 Net Overage** 🔴 |
| **Credit Utilization** | Percentage | Yes | Progress Bar with dynamic color (`<80% Green`, `80-100% Yellow`, `>100% Red`) |
| **Last Active** | Relative Time | Yes | "12 minutes ago" |
| **Actions** | Action Menu | No | `[ Quick Edit Quota ]` \| `[ Disable / Lock ]` \| `[ Set Exempt ]` |

* **Group Filter**: A dropdown filter in the table toolbar allows filtering by specific Quota Management Groups or showing "All Groups".
* **Quota Policy Filter**: A dropdown filter in the table toolbar allows filtering by policy inheritance state: `All Quota Types`, `Group Inherited` (members adopting group baselines), and `Custom Overrides` (members with individual caps).
* **Pagination**: Client-side Material UI `TablePagination` supporting 10, 25, 50, and 100 rows per page to deliver high responsiveness even in large enterprises with thousands of developers.

### 9.5 Groups Grid (Tab 2)
* **Card Grid**: Responsive cards for each Quota Management Group rendering group name, description, baseline weekly quota (`$50.00/wk`), overage buffer (`$10.00/wk`), and exemption badge.
* **Aggregate Metrics**: Live KPI badges displaying Member Count, Weekly Gross Spend, and Weekly Token Volume per group.
* **Actions**:
  * `[ Create Group ]`: Dialog to define new custom quota groups.
  * `[ Edit Group ]`: Dialog to modify baseline budgets or group exemptions.
  * `[ Delete Group ]`: Deletes custom group and reassigns members to `business-users`. (`business-users` is protected).
  * `[ Assign Members ]`: Dedicated modal on each group card supporting multi-email paste with a `[✓] Reset custom quota overrides to group baseline` checkbox (default checked) to batch-assign users, clear legacy custom caps, and auto-restore throttled users.
  * `[ View Members ]`: Instantly navigates to the Developers tab with that group filter pre-selected.

### 9.6 User Detail Slide-out Drawer
Clicking any user row opens a slide-out drawer containing:
1.  **Credit & Cost Ledger**:
    *   **Gross Token Value**: \$14.85
    *   **Allocated Credits**: \$20.00
    *   **Remaining Credit Balance**: \$5.15
    *   **Net Billable Overage**: \$0.00
2.  **Usage & Cost Donut Chart**: Breakdown by model (`Gemini 3 Pro` vs `Gemini 3.6 Flash`).
3.  **Hinge Point Breakdown**: Estimated Input vs Output vs Cached token volume and dollar amounts.
4.  **Quota Configuration Form**:
    *   **Custom Override Policy Banner & Action**: When a developer has `has_custom_quota = true`, an informational notice warns that their custom override ($X.XX/wk) supersedes the group baseline ($Y.XX/wk). An **"Adopt Group Quota"** button provides a 1-click action to clear the custom override and inherit the group baseline directly.
    *   **Quota Management Group**: Select dropdown to switch developer's assigned Quota Group (e.g. `Developers` or `Business Users`).
    *   Radio buttons for presets (\$10, \$15, \$25, \$50, \$100) or Custom Text Input (\$XX.XX) for individual overrides.
    *   Overage Buffer Input (\$XX.XX).
    *   `Exempt from Quota Controls` Checkbox.
    *   `Manually Lock / Disable User` Toggle.

### 9.7 Developer Onboarding ("Add Developer" Dialog)
In addition to synthetic discovery from BigQuery telemetry, administrators can manually pre-provision developers:
* **Interactive Modal**: Admin enters developer email, selects Quota Management Group, optionally specifies custom quota/buffer overrides, and sets exemption status.
* **REST API**: Invokes `POST /api/users` to initialize the developer in Firestore with status `ACTIVE`.
* **Instant Group Assignment**: Upon "Publish & Sync", the evaluator verifies and adds the developer to IAM Gatekeeper group `antigravity-active@`.

---

## 10. Security & Minimal Privilege IAM Model

| Identity / Service Account | Granted IAM Roles | Scoped Resource | Purpose |
| :--- | :--- | :--- | :--- |
| **Cloud Run Portal SA** (`antigravity-quota-portal@...`) | `roles/monitoring.viewer` | GCP Project | Queries upstream Gemini Enterprise subscription quota metrics (`discoveryengine.googleapis.com/quota/ratev2`). |
| **Cloud Run Portal SA** (`antigravity-quota-portal@...`) | `roles/bigquery.dataViewer`<br>`roles/bigquery.jobUser` | BigQuery Dataset & Project | Queries weekly developer token logs. |
| **Cloud Run Portal SA** (`antigravity-quota-portal@...`) | `roles/datastore.user` | Cloud Firestore | Manages configurations, quotas, user states, quota groups, subscription pool cache, and audit trails. |
| **Cloud Run Portal SA** (`antigravity-quota-portal@...`) | `roles/logging.logWriter` | GCP Project | Emits structured compliance audit logs to Cloud Logging (`antigravity-quota-audit`). |
| **Cloud Run Portal SA** (`antigravity-quota-portal@...`) | `roles/serviceusage.serviceUsageConsumer` | GCP Project | Consumes BigQuery, Cloud Monitoring, and logging APIs without project admin rights. |
| **Cloud Run Portal SA** (`antigravity-quota-portal@...`) | Cloud Identity **Owner & Member** | `antigravity-active@`<br>`antigravity-throttled@` | Reconciles developer memberships. **Zero GCP project IAM admin rights.** |
| **Admin Users / Domains** (e.g. `domain:example.com`) | `roles/run.invoker` | Cloud Run Service | Authorized invocation of the web dashboard and REST APIs under IAM authentication. |
| **Cloud Logging Sink Writer** (`service-PROJECT_NUM@gcp-sa-logging...`) | `roles/bigquery.dataEditor` | `antigravity_inference_logs` Dataset | Ingests `businessaicode.googleapis.com` logs from Cloud Logging into BigQuery. |

---

## 11. Enterprise Ingress & Zero-Trust Access (Domain-Restricted Environments)

In high-governance and domain-restricted enterprise environments (`constraints/iam.allowedPolicyMemberDomains`), Google Cloud organization policies strictly forbid public unauthenticated Cloud Run endpoints (`allUsers`). The system accommodates this via three complementary, bidirectionally switchable access patterns:

```mermaid
flowchart LR
    subgraph LocalAdmin ["Mode A: Proxy Bridge (access_mode = 'proxy')"]
        Browser["Admin Web Browser"] <-->|"http://localhost:8080"| Proxy["portal_access.sh proxy\n(Local IAM Bridge)"]
    end

    subgraph BrowserSSO ["Mode B: GCLB + Cloud DNS + IAP (access_mode = 'external_lb')"]
        CorpUser["Enterprise Browser / Concierge Agent"] <-->|"HTTPS (Cloud DNS + Managed SSL)"| GCLB["Global External ALB +\nIdentity-Aware Proxy (IAP)"]
    end

    subgraph GCP ["Google Cloud Platform"]
        Proxy <-->|"HTTPS with Bearer Token\n(gcloud auth identity)"| CR["Cloud Run Service\n(No allUsers; IAM + IAP SA)"]
        GCLB <-->|"Serverless NEG + IAP SA\n(roles/run.invoker)"| CR
        CR <--> BQ[("BigQuery")]
        CR <--> FS[("Firestore")]
    end
```

1. **Local Authenticated IAM Proxy Bridge (`access_mode = "proxy"`, `scripts/portal_access.sh proxy`)**:
   - Runs a lightweight local proxy (`http://localhost:8080`) that attaches the caller's `gcloud` OIDC identity token:
     ```bash
     ./scripts/portal_access.sh proxy --port 8080 --region us-east5 --project your-gcp-project-id
     ```
   - Allows instant browser testing without exposing the Cloud Run service to unauthenticated traffic.
2. **Global External Application Load Balancer + Cloud DNS + Identity-Aware Proxy (`access_mode = "external_lb"`)**:
   - Codifies Global Static IPv4 (`antigravity-portal-ip`), Cloud DNS Managed Zone / A-record (`terraform/dns.tf`), Google-Managed SSL Certificate (`google_compute_managed_ssl_certificate`), Serverless NEG, and IAP Backend Service (`terraform/lb.tf`).
   - Supports **Google-managed IAP OAuth** out-of-the-box (when `iap_oauth_client_id` is omitted after Internal OAuth Consent Screen configuration) as well as explicit OAuth 2.0 Web Client credentials for programmatic OIDC calls.
   - **Two-Stage Warmup & Bidirectional Mode Switching**: Setting `access_mode = "proxy"` with `enable_lb = true` provisions the GCLB + DNS + Managed SSL Certificate in the background while keeping `proxy` access active until `./scripts/portal_access.sh iap-status` confirms the certificate is `ACTIVE`. Operators can switch between `proxy`, `external_lb`, and simultaneous `dual` mode (`allow_proxy_with_lb = true`) at any time via Terraform or `./scripts/portal_access.sh switch-mode <proxy|external_lb|dual>`.
3. **Regional Internal Load Balancer (`access_mode = "internal_lb"`)**:
   - Provisions a Regional Internal ALB (`INTERNAL_MANAGED`) and Serverless NEG accessible strictly within the private VPC network.

---

## 12. Dual-Write Audit Trail & Observability

To satisfy enterprise FinOps compliance and SIEM ingestion, all state changes are recorded using a dual-write architecture:

1. **Firestore Audit Trail**: Persisted to the `audit_events` collection for rendering in the administrative web UI with rich filtering.
2. **GCP Cloud Logging Emitter (`antigravity-quota-audit`)**:
   - Implemented via `CloudLoggingAuditEmitter` in [`app/audit/cloud_logging.py`](app/audit/cloud_logging.py).
   - Writes structured JSON payloads containing actor identity, event type (`GROUP_SWAP`, `QUOTA_UPDATE`, `MANUAL_LOCK`, `EVALUATOR_RUN`), previous state, new state, and impact.
   - Categorizes group swaps and overage throttling as `WARNING`/`NOTICE` severity.
   - Built with non-blocking error isolation so audit export failures never disrupt user requests.

---

## 13. Summary & Operational Status

The portal is actively running with:
1. **Live Inference Log Ingestion**: Ingesting daily sharded telemetry from `businessaicode.googleapis.com` via a consolidated BigQuery view.
2. **Dynamic Pricing Calibration**: Supporting current models including `gemini-3.8-flash`, `gemini-3.1-pro-preview`, and `gemini-3.5-flash-lite`.
3. **Automated Directory Governance**: Cloud Identity IAM gatekeeper groups (`antigravity-active@` / `antigravity-throttled@`) fully provisioned and managed via Terraform.
4. **Quota Management Groups**: 3-tier policy hierarchy (`User Custom Quota > Group Quota > Global Default`) with pre-seeded "Developers" ($50/wk) and "Business Users" ($10/wk) groups, group exemption cascading, and full CRUD REST APIs.
5. **Three-Tab Responsive Governance UI**: Dedicated "Users", "Groups", and "Quota Increase Requests" tabs with client-side table pagination and pending request badges.
6. **Developer Self-Service View (`/my-quota`)**: Personalized developer portal with live quota status, Cloud Monitoring reset countdown, spend metrics, and model efficiency insights.
7. **In-App Quota Requests Governance**: Full request lifecycle with reason categories, OpenAI approval flexibility, Claude anti-spam and cooldown protections, self-service cancellation, and bulk approvals.
8. **Upstream Quota Telemetry**: Google Cloud Monitoring ratev2 integration with 300s TTL in-memory caching and Firestore snapshot fallback, tracking organizational subscription tier, WTU token usage, and live 7-day reset countdowns.
9. **Enterprise Zero-Trust Ingress Compliance**: Zero unauthenticated exposure (`--no-allow-unauthenticated`), GCLB + Cloud DNS + Identity-Aware Proxy (IAP), IAM-authenticated invocation, and local proxy bridge for operational administration.

---

## 14. Developer Self-Service Portal & Quota Requests Governance (Phase 2 & Enterprise Refinements)

### 14.1 Objective & Architecture
Enterprise organizations with thousands of AI developers (e.g. telecommunications, banking, healthcare) cannot scale quota adjustments through out-of-band emails or manual administrator tickets. The Phase 2 governance release introduces an integrated self-service and approval engine inspired by **OpenAI Codex Enterprise** and **Claude Code Enterprise** quota patterns.

```mermaid
flowchart TD
    subgraph DeveloperWorkstation ["Developer Experience (/my-quota)"]
        Dev["AI Developer (IDE / Browser)"]
        SelfCard["Developer Self-Service Card\n(Spend, Status, Reset Countdown, Model Breakdown)"]
        ReqModal["Request Quota Modal\n(Amount, Reason Category, Duration, Justification)"]
        Dev -->|"Visits Portal"| SelfCard
        SelfCard -->|"Clicks Request Quota"| ReqModal
        SelfCard -->|"Clicks Cancel Request"| CancelAPI["DELETE /api/quota-requests/{id}"]
    end

    subgraph APIAuthGateway ["FastAPI Identity & Governance Layer"]
        AuthMe["GET /api/auth/me\n(Role Detection & JIT Auto-Provisioning)"]
        SubmitReq["POST /api/quota-requests\n(Anti-Spam 409 & Cooldown 429 Checks)"]
        AdminReview["PATCH /api/quota-requests/{id}\n(Approval Flexibility & Duration Override)"]
        BulkReview["POST /api/quota-requests/bulk-review\n(Multi-Select Fast Approval)"]
    end

    subgraph AdminConsole ["Admin Governance (Quota Increase Requests Tab)"]
        Admin["IT / FinOps Admin"]
        ReqTab["Quota Increase Requests Tab\n(Pending Badge, Sub-Tabs, Multi-Select Checkboxes)"]
        Admin -->|"Reviews Requests"| ReqTab
        ReqTab -->|"Approves with Adjustments"| AdminReview
        ReqTab -->|"Batch Approves"| BulkReview
    end

    subgraph BackendStorage ["Persistence & Identity Sync"]
        FS[("Cloud Firestore\nquota_requests collection")]
        CI["Cloud Identity API\n(antigravity-active@ / antigravity-throttled@)"]
        Eval["Evaluator Weekly Reset\n(Reverts Temporary Quotas)"]
    end

    ReqModal -->|"Submits Request"| SubmitReq
    SubmitReq -->|"Persists Pending Request"| FS
    AdminReview -->|"Updates Request Status & User Quota"| FS
    AdminReview -->|"Immediate Unthrottle & Group Swap"| CI
    BulkReview -->|"Batch Updates"| FS
    CancelAPI -->|"Marks CANCELLED"| FS
    Eval -->|"Pool Rollover: Reverts Temporary Quota"| FS
```

### 14.2 Role-Based Landing & Just-in-Time (JIT) Provisioning
1. **Identity Extraction**:
   - The system checks Google Identity-Aware Proxy (IAP) header `X-Goog-Authenticated-User-Email` (stripping prefix `accounts.google.com:`), falling back to `X-User-Email` and `X-Forwarded-Email`.
2. **Role Routing**:
   - `GET /api/auth/me` resolves caller privileges against `AppConfig.admin_emails` or Cloud Identity group `AppConfig.admin_group_email`.
   - **Administrators**: Land on the full 3-tab management dashboard (`Users`, `Groups`, `Quota Increase Requests`), with a top-bar toggle to switch to `My Quota` or use the **"Preview As Developer"** dropdown to impersonate and test any developer's view.
   - **Developers (Non-Admins)**: Land directly on the simplified `<SelfServiceCard />` (`/my-quota`).
3. **Just-in-Time (JIT) Provisioning**:
   - If an authenticated developer visits the portal before their first prompt or BigQuery log ingestion, `GET /api/auth/me` automatically provisions them into Firestore with `business-users` baseline quota ($10.00/wk) and `ACTIVE` status.

### 14.3 Developer Self-Service View (`/my-quota`)
1. **Live Access Status Badge**:
   - `🟢 ACTIVE`: Quota credits remaining; member of `antigravity-active@`.
   - `🟡 WARNING (80%+ Used)`: Proactive pacing indicator alerting the developer before throttling occurs.
   - `🟠 AUTO-THROTTLED`: Quota + overage buffer exhausted; paused in `antigravity-throttled@`.
   - `🔴 MANUALLY LOCKED`: Administrative hold.
   - `⚪ EXEMPT`: Executive/lead bypass.
2. **Key Telemetry Metrics**:
   - Current Quota Allowance ($/wk) and Assigned Group.
   - Gross Spend This Week ($) and Credit Progress Bar (green `<75%`, yellow `75–99%`, red `≥100%`).
   - Countdown to Auto-Reset (days, hours, minutes) synchronized with Google Cloud Monitoring.
3. **Model Breakdown & Efficiency Insights**:
   - Collapsible panel displaying token and spend distribution by model (`gemini-3-pro`, `gemini-3.6-flash`, etc.).
   - Model Efficiency Insight tip: *"Pro reasoning models accounted for XX% of spend. Switching to Flash models for routine code edits yields up to 4x higher token efficiency."*
4. **Dynamic Action Banner**:
   - **Pending Request**: Displays amber banner `⏳ Quota Increase Pending: Requested $XX.XX/wk · Awaiting Admin Review` alongside a self-service **`[ Cancel Request ]`** button to withdraw.
   - **Cooldown Active**: Displays grey/red banner `🚫 Cooldown Active: Previous request declined (« Admin Note »). You may submit a new request after weekly reset in X days.`
   - **Standard Action**: Primary button **`[ Request Quota Increase ]`**.

### 14.4 Request Submission & Anti-Spam Protections
1. **Request Dialog Form**:
   - **Reason Category**: Emojified dropdown with categorized intent:
     - `🚀 Active Sprint / Tight Deadline` (`SPRINT_DEADLINE`)
     - `🛠️ Heavy Refactoring / Large Context` (`REFACTORING`)
     - `🚨 Production Incident / Hotfix` (`INCIDENT`)
     - `👥 Role Change / Need Tier Upgrade` (`ROLE_UPGRADE`)
     - `📝 Other Project Need` (`OTHER`)
   - **Requested Amount**: Quick-select chips (`+$15`, `+$25`, `+$50`) or custom amount input.
   - **Duration Needed**: Radio selector for `(●) Temporary (This week only)` vs `( ) Permanent Upgrade`.
   - **Business Justification**: Required explanation describing project needs.
2. **Anti-Spam (Conflict 409)**:
   - A developer cannot submit multiple concurrent requests. Attempting to submit while another request is `PENDING` returns HTTP `409 Conflict`.
3. **Cooldown Window (Too Many Requests 429)**:
   - If an admin rejects a request, the developer enters a cooldown period lasting until the next weekly pool reset (`cooldown_until`). Subsequent submission attempts return HTTP `429 Too Many Requests`.
4. **Self-Service Cancellation (`DELETE /api/quota-requests/{id}`)**:
   - Developers can cancel their pending request at any time. This frees them to submit a revised request without waiting for admin review.

### 14.5 Administrative Review & Approval Flexibility (OpenAI Pattern)
1. **Quota Increase Requests Tab in Admin Console**:
   - Filterable sub-tabs: `Pending`, `Approved`, `Rejected`, `All`.
   - Header badge displaying pending count (e.g. `[1 Pending]`).
   - Developer avatar, group, current spend, requested quota, category chip, relative submission timestamp, and justification snippet.
2. **OpenAI-Style Approval Flexibility**:
   - Approvers are **not** restricted to an all-or-nothing binary decision.
   - In the approval dialog, the admin can:
     - Adjust the approved dollar quota (e.g. approve $40.00 instead of requested $75.00).
     - Override duration: switch a permanent request to `TEMPORARY_WEEKLY` (reverting at next reset).
     - Attach an optional administrative note explaining the rationale.
3. **Rejection & Cooldown Enforcement**:
   - Rejection requires an administrative note. The rejection dialog clearly warns the admin that the developer will be placed on cooldown until the next weekly reset.
4. **Immediate Auto-Unthrottling & Directory Reconcile**:
   - If an approved developer was in `AUTO_DISABLED` status and their spend is within the new approved quota + buffer, the approval API immediately updates their status to `ACTIVE` and reconciles Cloud Identity membership into `antigravity-active@` in real time (<1s).
5. **Multi-Select Bulk Approvals**:
   - Checkbox selection on pending requests with toolbar button **`[ Bulk Approve Selected (Temporary) ]`** to batch-approve routine sprint requests during peak delivery cycles.

### 14.6 Evaluator Weekly Reset & Temporary Quota Reversion
1. **Weekly Pool Reset Trigger**:
   - When the hourly evaluator detects that the upstream Cloud Monitoring pool window has rolled over (`weekly_reset_applied = True`):
2. **Automatic Reversion**:
   - If `user.is_temporary_quota` is `True`, the engine resets:
     - `user.has_custom_quota = False`
     - `user.custom_quota_usd = None`
     - `user.is_temporary_quota = False`
   - The user immediately reverts to their assigned Quota Group baseline (e.g. $50.00/wk for `developers`).
   - Dual-writes a structured audit event `TEMPORARY_QUOTA_EXPIRED` to Firestore and Cloud Logging.
3. **Permanent Quotas Preserved**:
   - Users with permanent custom quotas retain their custom allocation across cycles.

### 14.7 Enterprise FinOps Extensions
For enterprise organizations with centralized FinOps practices and multi-tiered IT service management (see [ROADMAP.md](ROADMAP.md)):
- **Phase 2.5: Jira / ServiceNow Bi-Directional Webhooks**:
  - Automatically open a Jira Service Management or ServiceNow approval ticket upon quota request submission.
  - Webhook callback endpoint (`POST /api/webhooks/jira-callback`) to update request status and apply quota approvals when closed in ITSM software.
- **Phase 3: Delegated Squad Approvers & Policy-Based Auto-Approval**:
  - Delegated group/squad leads who can approve requests only for members within their specific `QuotaGroup`.
  - Configurable auto-approval rules: e.g. automatically approve temporary sprint increases $\le +\$25.00/\text{wk}$ once per quarter if the organization's pooled WTU utilization is under 70%.

