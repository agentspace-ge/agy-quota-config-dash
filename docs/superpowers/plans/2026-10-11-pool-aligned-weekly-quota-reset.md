# Upstream Credit Pool-Aligned Weekly Quota Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transition weekly quota aggregation, developer spend calculation, and auto-unthrottling from an arbitrary Monday 00:00 calendar reset to the authoritative upstream Google Cloud Gemini Enterprise Credit Pool cycle (`window_start_utc` from Cloud Monitoring / Firestore `config/credit_pool`), with comprehensive UI cycle transparency and updated documentation.

**Architecture:** 
1. Use `resolve_pool_window()` to dynamically resolve the active weekly cycle: if `CreditPoolStats` is available, derive `(week_id, start_utc, end_utc, now_utc)` from `window_start_utc` and `next_reset_utc`; otherwise fall back gracefully to the configured local Monday window.
2. In `QuotaEvaluator`, inject `CloudMonitoringPoolClient` so BigQuery token queries strictly filter `WHERE timestamp >= window_start_utc`. Implement a monotonic guard ($\ge 5$ days advancement) and hybrid proactive reset check (`now >= next_reset_utc`), transitioning user status with reason `WEEKLY_POOL_RESET`.
3. Update the frontend UI with full cycle transparency: rename Settings to "Portal Display Timezone", display full cycle start/reset datetimes on the Hero Card, show exact re-enable times for auto-throttled developers, and update active cycle timestamps in User Drawer ledger.
4. Align `SPECIFICATION.md` and `README.md` to reflect the pool-aligned governance model.

**Tech Stack:** Python 3.14, FastAPI, APScheduler, Google Cloud Monitoring API, Google Cloud Firestore, BigQuery, React, TypeScript, Material-UI, Vite, Pytest.

**Spec:** [SPECIFICATION.md](file:///Users/ayratk/development/agy-quota-config-dash/SPECIFICATION.md)

## Global Constraints
- Target platform: Google Cloud Platform (Cloud Run, Firestore, BigQuery, Cloud Identity).
- Backward compatibility: Existing Firestore `User` records without `window_start_utc` must not trigger false resets or data loss.
- Non-breaking UI: Retain standard Material-UI theming (light/dark mode compatibility) and responsive layout.
- Unit testing: All backend business logic must have automated unit tests with `pytest`.
- Linting & formatting: Maintain Python PEP8 / standard formatting and TypeScript compilation without errors (`tsc -b`).

---

## File Structure & Responsibilities

| File Path | Responsibility |
| :--- | :--- |
| `app/core/timezone_engine.py` | Calculates pool-aligned cycle windows (`resolve_pool_window`) and detects cycle transitions (`is_new_pool_cycle`). |
| `app/db/models.py` | Schema definitions; adds `window_start_utc` to `CurrentWeekUsage` and `CreditPoolStats`. |
| `app/core/state_machine.py` | State transitions; updates transition reason to `WEEKLY_POOL_RESET`. |
| `app/monitoring/pool_client.py` | Queries Cloud Monitoring with widened 8-day window for `window_start_time` and caches to Firestore. |
| `scripts/validate_pool.py` | CLI validator; adds `--sync-firestore` / `--save` flags for manual or CI sync to Firestore `config/credit_pool`. |
| `app/core/evaluator.py` | Quota evaluator engine; resolves pool window, aggregates BigQuery logs from `window_start_utc`, executes monotonic resets, and archives snapshots. |
| `app/api/deps.py` | Injects `pool_client` into `QuotaEvaluator`. |
| `app/main.py` | Ensures background APScheduler job refreshes `pool_client` before running evaluation. |
| `app/api/routes_evaluator.py` | Updates KPI calculation to resolve `week_id` and pool window. |
| `app/api/routes_users.py` | Sets initial `window_start_utc` on user creation from active pool stats. |
| `frontend/src/types.ts` | Frontend type definitions for `CreditPoolStats` and `CurrentWeekUsage`. |
| `frontend/src/components/SettingsModal.tsx` | Updates timezone label to "Portal Display Timezone" with explanatory helper text. |
| `frontend/src/components/KPISummary.tsx` | Displays pool cycle start date and reset date in UTC + Local on Hero Card. |
| `frontend/src/components/UserTable.tsx` | Shows exact reset timestamp for auto-throttled developers. |
| `frontend/src/components/UserDrawer.tsx` | Shows active pool cycle range in the Financial Ledger header. |
| `SPECIFICATION.md` | Architectural specification updated to pool-aligned reset model. |
| `README.md` | System documentation updated to describe credit-pool aligned resets. |
| `tests/test_timezone.py` | Unit tests for pool window resolution and cycle detection. |
| `tests/test_evaluator.py` | Unit tests for pool-aligned evaluation, monotonic reset, and unthrottling. |

---

## Tasks

### Task 1: Timezone Engine & Pool Window Resolution

**Files:**
- Modify: `app/core/timezone_engine.py`
- Test: `tests/test_timezone.py`

**Interfaces:**
- Produces:
  - `resolve_pool_window(pool_stats: CreditPoolStats | None, fallback_timezone: str = "America/Los_Angeles", now_dt: datetime | None = None) -> tuple[str, datetime, datetime, datetime]`
    - Returns `(week_id, start_utc, end_utc, now_utc)`.
  - `is_new_pool_cycle(prev_window_start_utc: datetime | None, current_window_start_utc: datetime, now_utc: datetime | None = None, next_reset_utc: datetime | None = None) -> bool`
    - Returns `True` if `current_window_start_utc` advanced by $\ge 5$ days OR if `now_utc >= next_reset_utc` (hybrid proactive expiration).

- [ ] **Step 1: Write failing unit tests for `resolve_pool_window` and `is_new_pool_cycle` in `tests/test_timezone.py`**
  Add tests for:
  - Valid `CreditPoolStats` with `window_start_utc` returns matching `start_utc`, derived `end_utc`, and ISO `week_id`.
  - Missing/None `pool_stats` falls back to calendar Monday window.
  - `is_new_pool_cycle` returns `False` if previous is None (prevent initial wipe).
  - `is_new_pool_cycle` returns `True` when window advances by 7 days.
  - `is_new_pool_cycle` returns `False` if timestamp jumped backwards or changed by less than 5 days (monotonic guard).
  - `is_new_pool_cycle` returns `True` when `now_utc >= next_reset_utc` (proactive expiration).

- [ ] **Step 2: Run pytest to confirm tests fail**
  ```bash
  ./.venv/bin/pytest tests/test_timezone.py -k "test_resolve_pool_window or test_is_new_pool_cycle"
  ```

- [ ] **Step 3: Implement `resolve_pool_window` and `is_new_pool_cycle` in `app/core/timezone_engine.py`**
  Preserve `get_current_week_window` as the fallback implementation. Implement the monotonic 5-day delta check and proactive `next_reset_utc` expiry.

- [ ] **Step 4: Run pytest to ensure all timezone tests pass**
  ```bash
  ./.venv/bin/pytest tests/test_timezone.py
  ```

- [ ] **Step 5: Commit changes**
  ```bash
  git commit -am "feat(timezone): implement pool-aligned window resolution and cycle detection"
  ```

---

### Task 2: Data Models & Schema Updates

**Files:**
- Modify: `app/db/models.py`
- Modify: `app/core/state_machine.py`
- Test: `tests/test_evaluator.py`

**Interfaces:**
- `CurrentWeekUsage`: add optional field `window_start_utc: datetime | None = None`.
- `evaluate_user_state_and_group`: update reason string to `"WEEKLY_POOL_RESET"`.

- [ ] **Step 1: Update `CurrentWeekUsage` in `app/db/models.py`**
  Add `window_start_utc: datetime | None = Field(default=None, description="Active upstream credit pool start timestamp")`.

- [ ] **Step 2: Update transition reason in `app/core/state_machine.py`**
  Change line 73 `reason = "WEEKLY_MONDAY_RESET"` to `reason = "WEEKLY_POOL_RESET"`.

- [ ] **Step 3: Update existing tests in `tests/test_evaluator.py` checking for reset reason**
  Update any test assertions expecting `WEEKLY_MONDAY_RESET` to accept `WEEKLY_POOL_RESET`.

- [ ] **Step 4: Run pytest on state machine and models**
  ```bash
  ./.venv/bin/pytest tests/test_evaluator.py -k "test_evaluate_user_state_and_group"
  ```

- [ ] **Step 5: Commit changes**
  ```bash
  git commit -am "feat(models): add window_start_utc to CurrentWeekUsage and update reset reason to WEEKLY_POOL_RESET"
  ```

---

### Task 3: Cloud Monitoring Pool Client & Script Enhancement

**Files:**
- Modify: `app/monitoring/pool_client.py`
- Modify: `app/monitoring/mock_pool.py`
- Modify: `scripts/validate_pool.py`

**Interfaces:**
- `pool_client._query_window_timestamps`: query `[now - 8 days, now]` to always capture `window_start_time` even with idle periods.
- `scripts/validate_pool.py`: accept `--sync-firestore` / `--save` to write results directly to Firestore `config/credit_pool`.

- [ ] **Step 1: Modify `_query_window_timestamps` in `app/monitoring/pool_client.py`**
  Change search interval from `midnight_pacific` to `[now - timedelta(days=8), now]`, ensuring the `window_start_time` label is discovered even if no queries ran today.

- [ ] **Step 2: Update `MockCloudMonitoringPoolClient` in `app/monitoring/mock_pool.py`**
  Ensure mock pool client populates realistic `window_start_utc` and `next_reset_utc` matching the interface.

- [ ] **Step 3: Update `scripts/validate_pool.py` to support `--sync-firestore`**
  Add CLI argument `--sync-firestore` (or `--save`). When present, initialize Firestore client and persist `CreditPoolStats` to `config/credit_pool`.

- [ ] **Step 4: Test `scripts/validate_pool.py` dry-run**
  ```bash
  python3 scripts/validate_pool.py --help
  ```

- [ ] **Step 5: Commit changes**
  ```bash
  git commit -am "feat(monitoring): widen window_start query interval and add --sync-firestore flag"
  ```

---

### Task 4: Evaluator Pool-Aligned Reset & Monotonic Integration

**Files:**
- Modify: `app/core/evaluator.py`
- Modify: `app/api/deps.py`
- Modify: `app/main.py`
- Test: `tests/test_evaluator.py`

**Interfaces:**
- `QuotaEvaluator.__init__`: accept `pool_client: Any = None`.
- `run_evaluation()`:
  - Fetches pool stats via `self.pool_client.get_pool_stats()` or `self.db.get_credit_pool()`.
  - Resolves window via `resolve_pool_window(pool_stats, config.timezone, eval_time)`.
  - Queries BigQuery with resolved `start_utc`.
  - Uses `is_new_pool_cycle` to guard reset condition.
  - Updates `user.current_week.window_start_utc = start_utc`.
- `app/main.py`: ensures `pool_client.get_pool_stats(force_refresh=True)` executes *before* `evaluator.run_evaluation()` in `scheduled_evaluation_job`.

- [ ] **Step 1: Write failing tests in `tests/test_evaluator.py`**
  - `test_evaluator_uses_pool_window_start_time`: Verify BigQuery is queried with `pool_stats.window_start_utc`.
  - `test_evaluator_pool_reset_advancement`: Verify that when `window_start_utc` advances by 7 days, snapshots are saved, spend resets to $0, and throttled users are re-enabled.
  - `test_evaluator_no_reset_across_calendar_monday`: Verify that passing calendar Monday 00:00 does *not* reset spend if pool `window_start_utc` has not changed.
  - `test_evaluator_smooth_cutover_initial_run`: Verify that existing users with `window_start_utc: None` adopt the new timestamp without being falsely reset.

- [ ] **Step 2: Run pytest to confirm tests fail**
  ```bash
  ./.venv/bin/pytest tests/test_evaluator.py -k "test_evaluator_uses_pool_window_start_time or test_evaluator_pool_reset_advancement or test_evaluator_no_reset_across_calendar_monday"
  ```

- [ ] **Step 3: Update `app/core/evaluator.py`**
  - Accept `pool_client` in constructor.
  - Call `resolve_pool_window` at start of `run_evaluation`.
  - Pass resolved `start_utc` to `fetch_weekly_usage`.
  - Use `is_new_pool_cycle` for weekly reset detection.
  - Set `user.current_week.window_start_utc = start_utc`.

- [ ] **Step 4: Update `app/api/deps.py` and `app/main.py`**
  - In `deps.py`: pass `pool_client=get_pool_client()` to `QuotaEvaluator`.
  - In `main.py`: invert order in `scheduled_evaluation_job` so `pool_client.get_pool_stats(force_refresh=True)` runs *before* `evaluator.run_evaluation()`.

- [ ] **Step 5: Run all evaluator tests**
  ```bash
  ./.venv/bin/pytest tests/test_evaluator.py
  ```

- [ ] **Step 6: Commit changes**
  ```bash
  git commit -am "feat(evaluator): align weekly aggregation and reset cycles with upstream credit pool"
  ```

---

### Task 5: API Endpoints & User Creation Updates

**Files:**
- Modify: `app/api/routes_evaluator.py`
- Modify: `app/api/routes_users.py`
- Test: `tests/test_evaluator.py`

**Interfaces:**
- `get_kpi_stats()`: derive `week_id` and window using `resolve_pool_window()`.
- `create_user()`: set `window_start_utc` and `week_id` from `resolve_pool_window()`.

- [ ] **Step 1: Update `get_kpi_stats()` in `app/api/routes_evaluator.py`**
  Use `resolve_pool_window` to ensure KPI cards return the pool-aligned `week_id`.

- [ ] **Step 2: Update `create_user()` in `app/api/routes_users.py`**
  Resolve current pool window when creating a user so `user.current_week.window_start_utc` is set on creation.

- [ ] **Step 3: Run pytest across API tests**
  ```bash
  ./.venv/bin/pytest tests/
  ```

- [ ] **Step 4: Commit changes**
  ```bash
  git commit -am "feat(api): ensure KPI stats and user creation adopt pool-aligned window"
  ```

---

### Task 6: Frontend UI Components & Display Semantics

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/SettingsModal.tsx`
- Modify: `frontend/src/components/KPISummary.tsx`
- Modify: `frontend/src/components/UserTable.tsx`
- Modify: `frontend/src/components/UserDrawer.tsx`

**Interfaces:**
- `types.ts`: add `window_start_utc?: string | null` to `CurrentWeekUsage`.
- `SettingsModal.tsx`:
  - Label: `"Portal Display Timezone"`
  - Helper text: `"Weekly quota cycles follow the upstream GCP Credit Pool. This timezone formats portal timestamps and provides a fallback if telemetry is offline."`
- `KPISummary.tsx`:
  - Show active cycle range in Hero Card: `Start: Oct 11, 13:06 UTC · Reset: Oct 18, 13:06 UTC` (with local time equivalent).
- `UserTable.tsx`:
  - In `AUTO_DISABLED` status chip tooltip/subtext: show `"Re-enables at [pool.next_reset_utc]"` if available.
- `UserDrawer.tsx`:
  - Under Ledger title: display the active cycle start & reset range.

- [ ] **Step 1: Update `frontend/src/types.ts`**
  Add `window_start_utc?: string | null;` to `CurrentWeekUsage`.

- [ ] **Step 2: Update `frontend/src/components/SettingsModal.tsx`**
  Change label to `"Portal Display Timezone"` and update the helper text.

- [ ] **Step 3: Update `frontend/src/components/KPISummary.tsx`**
  Add a cycle window date range banner / sub-badge in the Hero Card displaying `window_start_utc` and `next_reset_utc`.

- [ ] **Step 4: Update `frontend/src/components/UserTable.tsx` & `frontend/src/components/UserDrawer.tsx`**
  Pass pool reset time to format re-enable expectations on auto-throttled status chips, and render the cycle range in the user ledger header.

- [ ] **Step 5: Verify frontend compilation**
  ```bash
  npm --prefix frontend run build
  ```

- [ ] **Step 6: Commit changes**
  ```bash
  git commit -am "feat(ui): update Settings timezone semantics and add credit pool cycle window transparency"
  ```

---

### Task 7: Documentation Updates (`SPECIFICATION.md` & `README.md`)

**Files:**
- Modify: `SPECIFICATION.md`
- Modify: `README.md`

**Documentation requirements:**
- In `SPECIFICATION.md`:
  - Update Section 1, Section 2.3, Section 3.1, and State Machine diagrams to specify that weekly quota windows and auto-resets are governed by the upstream Gemini Enterprise Credit Pool cycle (`window_start_time`), replacing the calendar Monday 00:00 model.
  - Document the fallback to local Monday calculation in cold-start/offline conditions.
  - Document the `WEEKLY_POOL_RESET` transition reason and monotonic guard.
- In `README.md`:
  - Update feature list and governance architecture to reflect the upstream credit pool alignment.
  - Update descriptions of weekly reset from "Every Monday at 00:00" to "Synchronized with Upstream Google Cloud Quota Pool Cycle (with Monday calendar fallback)".

- [ ] **Step 1: Update `SPECIFICATION.md`**
  Replace obsolete references to Monday 00:00 with the pool-aligned reset architecture and state machine rules.

- [ ] **Step 2: Update `README.md`**
  Update the system features, architecture overview, and governance description.

- [ ] **Step 3: Commit documentation updates**
  ```bash
  git commit -am "docs: update SPECIFICATION and README for pool-aligned quota reset"
  ```

---

### Task 8: End-to-End Verification & Test Suite

**Files:**
- Test: All unit and integration tests in `tests/`
- Build: Frontend production build

- [ ] **Step 1: Run full backend test suite**
  ```bash
  ./.venv/bin/pytest -v tests/
  ```

- [ ] **Step 2: Run frontend production build**
  ```bash
  npm --prefix frontend run build
  ```

- [ ] **Step 3: Run git status check to verify clean repository state**
  ```bash
  git status
  ```

---

## Plan Review Checkpoint

Please review this implementation plan. Once approved, we will begin execution using `superpowers:executing-plans` or `superpowers:subagent-driven-development`.
