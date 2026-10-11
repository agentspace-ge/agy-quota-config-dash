# Technical Implementation Plan: Quota Groups Governance & Two-Tab UI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement enterprise Quota Groups support ("Developers" and "Business Users") alongside individual users in the Antigravity Quota Portal, featuring a 2-tab UI (Users & Groups), 3-tier quota inheritance, table pagination for 15,000+ licenses, bulk email membership assignment, modernized IAM Gatekeeper naming (`antigravity-active@` / `antigravity-throttled@`), and Phase 2 IAM sync readiness.

**Architecture:** Extend Firestore models and evaluation engine to resolve quotas hierarchically (`User Custom > Group Quota > Global Default`). Modernize IAM access gatekeeper default naming to `antigravity-active@` and `antigravity-throttled@` with clear UI labeling in Settings. Introduce a dedicated Groups REST API with bulk member operations, auto-seed default groups, add a two-tab Material Design interface (`Users` and `Groups`), add Table Pagination to `UserTable.tsx` for enterprise scale, and update documentation (`SPECIFICATION.md`, `README.md`) and UI mockup screenshots.

**Tech Stack:** FastAPI (Python 3.11+), Pydantic v2, Cloud Firestore Native / Mock DB, React 18, Vite, TypeScript, Material UI (MUI v5), Pytest, Selenium Headless Chrome.

**Spec:** [SPECIFICATION.md](../../../SPECIFICATION.md) and [README.md](../../../README.md)

---

## Global Constraints

- Python backend must pass all `pytest tests/ -v` without regressions or broken fixtures.
- Frontend must build cleanly with `npm --prefix frontend run build` (zero TypeScript errors).
- Quota precedence MUST follow: User Custom Quota (`has_custom_quota = true`) > Group Quota (`user.group_id`) > Global Default Quota (`config.default_quota_usd`).
- Single group membership per user: each user belongs to at most one group (`group_id`).
- Default seeding on initial startup: "Developers" ($50.00 / $10.00 buffer) and "Business Users" ($10.00 / $2.00 buffer). Unassigned/new users default to "Business Users".
- Modernized Gatekeeper Groups: Default to `antigravity-active@example.com` and `antigravity-throttled@example.com`, preserving full backwards compatibility for custom email overrides in Firestore and `terraform.tfvars`.
- Scalability for 15,000+ users: Add MUI `TablePagination` (25, 50, 100 rows per page) in `UserTable.tsx`.
- Phase 2 readiness: each group model includes an optional `iam_group_email` attribute.
- Documentation (`SPECIFICATION.md`, `README.md`) must be comprehensively updated to reflect groups, gatekeeper distinctions, and the two-tab UI.
- Visual mockup screenshots must be refreshed via `scripts/capture_screenshot.py`.

---

## User Review Required

> [!NOTE]
> **Clear Separation of Group Concepts**:
> 1. **Quota Policy Groups** (New "Groups" tab): Business-facing tiers ("Developers", "Business Users") configuring weekly allowances and overage buffers.
> 2. **IAM Access Gatekeeper Groups** (Settings): System-managed Cloud Identity groups (`antigravity-active@` and `antigravity-throttled@`) that physically bind/unbind GCP IAM role `roles/businessaicode.user`.

> [!IMPORTANT]
> **Enterprise Scale & UI Performance**: With 15,000+ licenses, rendering flat lists without pagination causes browser unresponsiveness. Table pagination (25 / 50 / 100) will be implemented with instant search and group filtering.

---

## File Structure & Responsibilities

| File | Action | Responsibility |
|---|---|---|
| `app/db/models.py` | Modify | Define `QuotaGroup`, `QuotaGroupStats`, request/response schemas; update default gatekeeper emails in `AppConfig`; update `User` with `group_id` |
| `app/db/firestore_client.py` | Modify | Firestore CRUD and bulk assignment methods for groups |
| `app/db/mock_db.py` | Modify | In-memory mock storage, default group seeding, modernized gatekeeper defaults |
| `app/core/evaluator.py` | Modify | 3-tier quota inheritance, group spend/token aggregation, group-level exemption |
| `app/api/routes_groups.py` | **Create** | REST API endpoints for Group CRUD, member listing, and bulk assignment |
| `app/api/routes_users.py` | Modify | Accept and return `group_id` in user create/update endpoints |
| `app/main.py` | Modify | Register groups router and initialize seed groups |
| `frontend/src/types.ts` | Modify | TypeScript interfaces for `QuotaGroup`, updated `User`, and API payloads |
| `frontend/src/services/api.ts` | Modify | API functions for groups endpoints |
| `frontend/src/components/GroupTable.tsx` | **Create** | Table of groups with spend dials, quotas, member counts, and action buttons |
| `frontend/src/components/GroupModal.tsx` | **Create** | Modal/Drawer for editing group quota settings and bulk member email input |
| `frontend/src/components/UserTable.tsx` | Modify | Add "Group" column with chip badges, Group filter dropdown, and `TablePagination` |
| `frontend/src/components/UserDrawer.tsx` | Modify | Add Group selector, display inherited quota details, and show physical IAM Gatekeeper group |
| `frontend/src/components/SettingsModal.tsx` | Modify | Update labels to "IAM Gatekeeper Groups" with modernized defaults and helpful tooltips |
| `frontend/src/components/AddUserModal.tsx` | Modify | Add Group selector for pre-provisioning users |
| `frontend/src/App.tsx` | Modify | 2-Tab navigation (`Users` and `Groups`), state management for groups |
| `terraform/variables.tf` | Modify | Update default values for `enabled_group_email` (`antigravity-active@`) and `disabled_group_email` (`antigravity-throttled@`) |
| `SPECIFICATION.md` | Modify | Architectural specification updates for Quota Groups, Gatekeepers, & 2-tab UI |
| `README.md` | Modify | Readme documentation updates, architecture diagrams, and feature docs |
| `scripts/seed_demo_data.py` | Modify | Seed demo users across "Developers" and "Business Users" |
| `scripts/capture_screenshot.py` | Modify | Capture both Users tab and Groups tab mockups |
| `tests/test_groups_api.py` | **Create** | Comprehensive unit & integration tests for groups API |
| `tests/test_evaluator.py` | Modify | Tests for 3-tier quota inheritance and group spend calculation |

---

## Step-by-Step Implementation Tasks

### Task 1: Backend Data Models, Gatekeeper Defaults & Database Abstraction

**Files:**
- Modify: `app/db/models.py`
- Modify: `app/db/firestore_client.py`
- Modify: `app/db/mock_db.py`
- Modify: `terraform/variables.tf`
- Test: `tests/test_mock_environment.py`

- [ ] **Step 1: Write test for group storage, seeding, and gatekeeper defaults in mock database**
  Add test asserting that `list_groups()` returns the seeded "Developers" and "Business Users" groups, that `create_group()`, `update_group()`, `delete_group()`, and `bulk_assign_group_members()` function properly, and that default gatekeeper groups are `antigravity-active@` and `antigravity-throttled@`.
- [ ] **Step 2: Run test to verify it fails**
  Run `./.venv/bin/pytest tests/test_mock_environment.py -k test_group_storage`
- [ ] **Step 3: Implement `QuotaGroup` models and modernize `AppConfig` in `app/db/models.py`**
  Add `QuotaGroup`, `QuotaGroupStats`, `QuotaGroupCreateRequest`, `QuotaGroupUpdateRequest`, `QuotaGroupMembersRequest`. Update `AppConfig` default `enabled_group = "antigravity-active@example.com"` and `disabled_group = "antigravity-throttled@example.com"`. Add `group_id: str | None = "business-users"` to `User`, `UserUpdateRequest`, `UserCreateRequest`.
- [ ] **Step 4: Implement group methods in `mock_db.py` and `firestore_client.py`**
  Support collection `groups` in Firestore and in-memory dict in mock DB with automatic seeding of `"developers"` and `"business-users"`. Update default gatekeeper emails in `terraform/variables.tf`.
- [ ] **Step 5: Run tests and verify they pass**
  Run `./.venv/bin/pytest tests/test_mock_environment.py -v`

---

### Task 2: Core Evaluator Engine Quota Inheritance & Group Aggregation

**Files:**
- Modify: `app/core/evaluator.py`
- Modify: `tests/test_evaluator.py`

- [ ] **Step 1: Write tests for 3-tier quota resolution**
  Test 1: User without custom quota inherits their group's quota credits & overage buffer.
  Test 2: User with custom quota retains their explicit custom override.
  Test 3: User in a group with `is_exempt = True` is treated as exempt from throttling.
  Test 4: Group aggregate spend, token counts, and member counts are calculated accurately.
- [ ] **Step 2: Run tests to verify failure**
  Run `./.venv/bin/pytest tests/test_evaluator.py -k test_group_inheritance`
- [ ] **Step 3: Update `QuotaEvaluator.run_evaluation`**
  Fetch groups, resolve effective quota per user following the hierarchy, compute group aggregated spend and token counts, and assign discovered new users to `default_group_id`.
- [ ] **Step 4: Run tests and verify they pass**
  Run `./.venv/bin/pytest tests/test_evaluator.py -v`

---

### Task 3: Groups REST API & Users API Integration

**Files:**
- Create: `app/api/routes_groups.py`
- Modify: `app/api/routes_users.py`
- Modify: `app/main.py`
- Create: `tests/test_groups_api.py`

- [ ] **Step 1: Write tests for `/api/groups` endpoints**
  Test listing groups, creating a new group, updating group quota, deleting a group, and bulk adding/removing member emails.
- [ ] **Step 2: Run tests to verify failure**
  Run `./.venv/bin/pytest tests/test_groups_api.py -v`
- [ ] **Step 3: Implement `routes_groups.py`**
  Implement `GET /api/groups`, `POST /api/groups`, `GET /api/groups/{group_id}`, `PUT /api/groups/{group_id}`, `DELETE /api/groups/{group_id}`, and `POST /api/groups/{group_id}/members`.
- [ ] **Step 4: Update `routes_users.py` and `app/main.py`**
  Update user create/update endpoints to handle `group_id`. Mount `routes_groups.router` in `app/main.py`.
- [ ] **Step 5: Run tests and verify all API tests pass**
  Run `./.venv/bin/pytest tests/test_groups_api.py tests/test_api.py -v`

---

### Task 4: Frontend Types, API Client, and Two-Tab Navigation with Pagination

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/services/api.ts`
- Create: `frontend/src/components/GroupTable.tsx`
- Create: `frontend/src/components/GroupModal.tsx`
- Modify: `frontend/src/components/UserTable.tsx`
- Modify: `frontend/src/components/UserDrawer.tsx`
- Modify: `frontend/src/components/SettingsModal.tsx`
- Modify: `frontend/src/components/AddUserModal.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Update TypeScript types in `frontend/src/types.ts`**
  Add `QuotaGroup` interface, update `User` interface with `group_id?: string`.
- [ ] **Step 2: Add Group API client functions in `frontend/src/services/api.ts`**
  Add `fetchGroups()`, `createGroup()`, `updateGroup()`, `deleteGroup()`, `updateGroupMembers()`.
- [ ] **Step 3: Build `GroupTable.tsx` component**
  Table rendering group names, descriptions, quota credits, overage buffers, member counts, aggregate spend, IAM email badges, and action buttons ("Edit Quota", "Manage Members", "Delete").
- [ ] **Step 4: Build `GroupModal.tsx` component**
  Modal for configuring group quotas/exemption and a multi-line textarea for bulk pasting emails (comma or newline-separated) with instant count feedback.
- [ ] **Step 5: Update `UserTable.tsx` with Pagination and Group filter**
  Add "Group" column with colored chips, Group Filter dropdown, and MUI `TablePagination` (25, 50, 100 per page) for fluid handling of up to 15,000+ users.
- [ ] **Step 6: Update `UserDrawer.tsx` and `SettingsModal.tsx`**
  In `UserDrawer`, add Group selector with inherited quota display and show physical IAM Gatekeeper group (`antigravity-active@` vs `antigravity-throttled@`). In `SettingsModal`, label gatekeeper groups as "IAM Gatekeeper Groups" with helpful tooltip explanations.
- [ ] **Step 7: Update `App.tsx` with 2 Tabs (`Users` and `Groups`)**
  Render MUI `<Tabs value={activeTab}>` below the KPI summary. Toggle between `UserTable` and `GroupTable`. Add "Add Group" action button.
- [ ] **Step 8: Build and verify frontend**
  Run `npm --prefix frontend run build` and ensure clean compilation.

---

### Task 5: Documentation Updates & UI Mockups/Screenshots

**Files:**
- Modify: `SPECIFICATION.md`
- Modify: `README.md`
- Modify: `scripts/seed_demo_data.py`
- Modify: `scripts/capture_screenshot.py`

- [ ] **Step 1: Update `SPECIFICATION.md`**
  Document the Three-Tier Quota Architecture (`User Custom > Group Quota > Global Fallback`), the `QuotaGroup` schema, REST API routes, IAM Gatekeeper naming rationale, and Phase 2 IAM synchronization design.
- [ ] **Step 2: Update `README.md`**
  Update feature breakdown, architecture diagrams, and operational guides to highlight Quota Groups, Gatekeeper distinctions, and the 2-tab interface.
- [ ] **Step 3: Update `scripts/seed_demo_data.py`**
  Assign demo users to "Developers" and "Business Users" groups.
- [ ] **Step 4: Update `scripts/capture_screenshot.py` and capture mockups**
  Capture `docs/images/portal_dashboard.png` (Users tab) and `docs/images/portal_groups.png` (Groups tab) using headless Chrome.

---

## Verification Plan

### Automated Tests
```bash
# 1. Run all backend tests
./.venv/bin/pytest tests/ -v

# 2. Build the frontend
npm --prefix frontend run build
```

### Manual Verification
1. Run local demo server: `python3 scripts/run_local_demo.py`
2. Open `http://localhost:8080`:
   - Verify KPI cards display accurately.
   - Click "Groups" tab: inspect "Developers" ($50.00) and "Business Users" ($10.00).
   - Click "Edit" on Developers: change quota to $60.00 and save; verify cascade.
   - Click "Manage Members": paste 3 emails to add them to Developers; verify member count updates.
   - Click "Users" tab: verify "Group" column shows correct chips; test filtering by group and pagination controls.
   - Open User Drawer for a user in Developers: verify inherited quota and IAM Gatekeeper status are displayed.
   - Open Settings Modal: verify "IAM Gatekeeper Groups" naming and tooltips.
