"""In-memory mock database for testing and local development sandbox."""

import threading
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from app.audit.emitter import BaseAuditEmitter
from app.db.models import (
    AppConfig,
    AuditEvent,
    CreditPoolStats,
    CurrentWeekUsage,
    QuotaGroup,
    SpendBreakdown,
    User,
    UserStatus,
    WeeklySnapshot,
)


class MockDatabase:
    """Thread-safe in-memory database simulating Cloud Firestore."""

    def __init__(self, audit_emitter: BaseAuditEmitter | None = None):
        self._lock = threading.RLock()
        self.audit_emitter = audit_emitter
        self._config: AppConfig = AppConfig()
        self._groups: dict[str, QuotaGroup] = {}
        self._users: dict[str, User] = {}
        self._audit_events: list[AuditEvent] = []
        self._snapshots: dict[str, list[WeeklySnapshot]] = {}
        self._credit_pool: CreditPoolStats | None = None
        self._init_mock_data()

    def _init_default_groups(self, now: datetime | None = None):
        if not now:
            now = datetime.now(UTC)
        if not self._groups:
            self._groups["developers"] = QuotaGroup(
                group_id="developers",
                display_name="Developers",
                description="Engineering and development teams with higher inference quotas",
                weekly_quota_usd=50.0,
                overage_buffer_usd=10.0,
                is_exempt=False,
                iam_group_email=None,
                created_at=now - timedelta(days=90),
                updated_at=now,
            )
            self._groups["business-users"] = QuotaGroup(
                group_id="business-users",
                display_name="Business Users",
                description="Standard business users with standard tier quotas",
                weekly_quota_usd=10.0,
                overage_buffer_usd=2.0,
                is_exempt=False,
                iam_group_email=None,
                created_at=now - timedelta(days=90),
                updated_at=now,
            )

    def _init_mock_data(self):
        """Seed realistic demo users and groups for the sandbox environment."""
        now = datetime.now(UTC)
        self._init_default_groups(now)

        # Compute realistic start/reset timestamps matching current weekly cycle (Saturday cycle)
        days_since_cycle = (now.weekday() - 5) % 7
        cycle_start = (now - timedelta(days=days_since_cycle)).replace(hour=12, minute=47, second=20, microsecond=0)
        cycle_reset = cycle_start + timedelta(days=7)
        iso_year, iso_week, _ = cycle_start.isocalendar()
        week_id = f"{iso_year}-W{iso_week:02d}"

        # Initialize mock credit pool stats
        self._credit_pool = CreditPoolStats(
            tier_key="plus",
            tier_name="Gemini Enterprise Plus",
            usage_wtu=3_900_567,
            limit_wtu=37_500_000,
            usage_usd=7.80,
            limit_usd=75.00,
            utilization_pct=10.4,
            window_start_utc=cycle_start,
            next_reset_utc=cycle_reset,
            last_synced_at=now,
        )

        # 1. Alice - Active heavy user under quota
        alice_tokens = {"gemini-3-pro": 2500000, "gemini-3.6-flash": 1500000}
        self._users["alice.chen@example.com"] = User(
            email="alice.chen@example.com",
            group_id="developers",
            status=UserStatus.ACTIVE,
            is_exempt=False,
            has_custom_quota=True,
            custom_quota_usd=25.00,
            custom_overage_usd=5.00,
            current_week=CurrentWeekUsage(
                week_id=week_id,
                window_start_utc=cycle_start,
                total_tokens=4000000,
                total_requests=320,
                gross_spend_usd=6.15,
                quota_credits_usd=25.00,
                remaining_credit_usd=18.85,
                net_billable_cost_usd=0.00,
                overage_buffer_usd=5.00,
                spend_breakdown=SpendBreakdown(
                    input_spend_usd=4.20,
                    output_spend_usd=1.65,
                    cached_spend_usd=0.30,
                ),
                tokens_by_model=alice_tokens,
                spend_by_model={"gemini-3-pro": 5.75, "gemini-3.6-flash": 0.40},
                credit_utilization_percentage=24.6,
                last_active=now - timedelta(minutes=15),
            ),
            created_at=now - timedelta(days=60),
            updated_at=now - timedelta(minutes=15),
        )

        # 2. Bob - Warning pace (near 85% quota)
        bob_tokens = {"gemini-3-pro": 3800000}
        self._users["bob.martin@example.com"] = User(
            email="bob.martin@example.com",
            group_id="developers",
            status=UserStatus.ACTIVE,
            is_exempt=False,
            has_custom_quota=False,
            custom_quota_usd=None,
            custom_overage_usd=None,
            current_week=CurrentWeekUsage(
                week_id=week_id,
                window_start_utc=cycle_start,
                total_tokens=3800000,
                total_requests=210,
                gross_spend_usd=8.74,
                quota_credits_usd=10.00,
                remaining_credit_usd=1.26,
                net_billable_cost_usd=0.00,
                overage_buffer_usd=2.00,
                spend_breakdown=SpendBreakdown(
                    input_spend_usd=6.12,
                    output_spend_usd=2.28,
                    cached_spend_usd=0.34,
                ),
                tokens_by_model=bob_tokens,
                spend_by_model={"gemini-3-pro": 8.74},
                credit_utilization_percentage=87.4,
                last_active=now - timedelta(minutes=4),
            ),
            created_at=now - timedelta(days=45),
            updated_at=now - timedelta(minutes=4),
        )

        # 3. Charlie - Auto Throttled (Breached Quota + Overage)
        charlie_tokens = {"gemini-3-pro": 5500000, "gemini-2.5-pro": 1000000}
        self._users["charlie.davis@example.com"] = User(
            email="charlie.davis@example.com",
            group_id="business-users",
            status=UserStatus.AUTO_DISABLED,
            is_exempt=False,
            has_custom_quota=False,
            custom_quota_usd=None,
            custom_overage_usd=None,
            current_week=CurrentWeekUsage(
                week_id=week_id,
                window_start_utc=cycle_start,
                total_tokens=6500000,
                total_requests=480,
                gross_spend_usd=14.95,
                quota_credits_usd=10.00,
                remaining_credit_usd=0.00,
                net_billable_cost_usd=4.95,
                overage_buffer_usd=2.00,
                spend_breakdown=SpendBreakdown(
                    input_spend_usd=10.45,
                    output_spend_usd=3.90,
                    cached_spend_usd=0.60,
                ),
                tokens_by_model=charlie_tokens,
                spend_by_model={"gemini-3-pro": 12.65, "gemini-2.5-pro": 2.30},
                credit_utilization_percentage=149.5,
                last_active=now - timedelta(hours=2),
            ),
            created_at=now - timedelta(days=30),
            updated_at=now - timedelta(hours=2),
        )

        # 4. Dana - Exempt Tech Lead
        dana_tokens = {"gemini-3-pro": 12000000}
        self._users["dana.scully@example.com"] = User(
            email="dana.scully@example.com",
            group_id="developers",
            status=UserStatus.ACTIVE,
            is_exempt=True,
            has_custom_quota=False,
            custom_quota_usd=None,
            custom_overage_usd=None,
            current_week=CurrentWeekUsage(
                week_id=week_id,
                window_start_utc=cycle_start,
                total_tokens=12000000,
                total_requests=950,
                gross_spend_usd=27.60,
                quota_credits_usd=10.00,
                remaining_credit_usd=0.00,
                net_billable_cost_usd=17.60,
                overage_buffer_usd=2.00,
                spend_breakdown=SpendBreakdown(
                    input_spend_usd=19.32,
                    output_spend_usd=7.20,
                    cached_spend_usd=1.08,
                ),
                tokens_by_model=dana_tokens,
                spend_by_model={"gemini-3-pro": 27.60},
                credit_utilization_percentage=276.0,
                last_active=now - timedelta(minutes=45),
            ),
            created_at=now - timedelta(days=90),
            updated_at=now - timedelta(minutes=45),
        )

        # 5. Evan - Manually Disabled by Security Admin
        self._users["evan.wright@example.com"] = User(
            email="evan.wright@example.com",
            group_id="business-users",
            status=UserStatus.MANUALLY_DISABLED,
            is_exempt=False,
            has_custom_quota=False,
            custom_quota_usd=None,
            custom_overage_usd=None,
            current_week=CurrentWeekUsage(
                week_id=week_id,
                window_start_utc=cycle_start,
                total_tokens=120000,
                total_requests=12,
                gross_spend_usd=0.28,
                quota_credits_usd=10.00,
                remaining_credit_usd=9.72,
                net_billable_cost_usd=0.00,
                overage_buffer_usd=2.00,
                spend_breakdown=SpendBreakdown(
                    input_spend_usd=0.19,
                    output_spend_usd=0.07,
                    cached_spend_usd=0.02,
                ),
                tokens_by_model={"gemini-3-pro": 120000},
                spend_by_model={"gemini-3-pro": 0.28},
                credit_utilization_percentage=2.8,
                last_active=now - timedelta(days=3),
            ),
            created_at=now - timedelta(days=120),
            updated_at=now - timedelta(days=1),
        )

        # Initial Audit Trail
        self._audit_events.append(
            AuditEvent(
                event_id="evt-seed-1",
                timestamp=now - timedelta(hours=2),
                action="GROUP_SWAP",
                triggered_by="SYSTEM_WORKER",
                target_user="charlie.davis@example.com",
                details={
                    "from_group": "antigravity-active@example.com",
                    "to_group": "antigravity-throttled@example.com",
                    "reason": "HARD_LIMIT_BREACHED: Spend $14.95 >= Limit $12.00",
                },
            )
        )
        self._audit_events.append(
            AuditEvent(
                event_id="evt-seed-2",
                timestamp=now - timedelta(days=1),
                action="MANUAL_LOCK",
                triggered_by="admin@example.com",
                target_user="evan.wright@example.com",
                details={"reason": "Security review pending"},
            )
        )

    def get_config(self) -> AppConfig:
        with self._lock:
            return self._config.model_copy(deep=True)

    def update_config(self, config: AppConfig) -> AppConfig:
        with self._lock:
            self._config = config.model_copy(deep=True)
            return self._config.model_copy(deep=True)

    def get_user(self, email: str) -> User | None:
        with self._lock:
            user = self._users.get(email.lower().strip())
            return user.model_copy(deep=True) if user else None

    def list_users(self) -> list[User]:
        with self._lock:
            return [user.model_copy(deep=True) for user in self._users.values()]

    def save_user(self, user: User) -> User:
        with self._lock:
            user.updated_at = datetime.now(UTC)
            self._users[user.email.lower().strip()] = user.model_copy(deep=True)
            return user.model_copy(deep=True)

    def delete_user(self, email: str) -> bool:
        with self._lock:
            key = email.lower().strip()
            if key in self._users:
                del self._users[key]
                return True
            return False

    def save_users(self, users: list[User]) -> None:
        with self._lock:
            now = datetime.now(UTC)
            for user in users:
                user.updated_at = now
                self._users[user.email.lower().strip()] = user.model_copy(deep=True)

    def add_audit_event(self, event: AuditEvent) -> None:
        with self._lock:
            self._audit_events.insert(0, event.model_copy(deep=True))
            # Keep latest 500 events
            if len(self._audit_events) > 500:
                self._audit_events = self._audit_events[:500]
        if self.audit_emitter:
            self.audit_emitter.emit(event)

    def list_audit_events(self, limit: int = 100) -> list[AuditEvent]:
        with self._lock:
            return [evt.model_copy(deep=True) for evt in self._audit_events[:limit]]

    def save_weekly_snapshot(self, user_email: str, snapshot: WeeklySnapshot) -> None:
        with self._lock:
            key = user_email.lower().strip()
            if key not in self._snapshots:
                self._snapshots[key] = []
            self._snapshots[key].append(snapshot.model_copy(deep=True))

    def list_weekly_snapshots(self, user_email: str) -> list[WeeklySnapshot]:
        with self._lock:
            key = user_email.lower().strip()
            return [snap.model_copy(deep=True) for snap in self._snapshots.get(key, [])]

    def get_credit_pool(self) -> CreditPoolStats | None:
        with self._lock:
            return self._credit_pool.model_copy(deep=True) if self._credit_pool else None

    def save_credit_pool(self, pool: CreditPoolStats) -> None:
        with self._lock:
            self._credit_pool = pool.model_copy(deep=True)

    def _enrich_group_stats(self, group: QuotaGroup) -> QuotaGroup:
        """Enrich a group with live aggregated stats from user records."""
        member_count = 0
        gross_spend = 0.0
        total_tokens = 0
        for user in self._users.values():
            if user.group_id == group.group_id:
                member_count += 1
                gross_spend += user.current_week.gross_spend_usd
                total_tokens += user.current_week.total_tokens
        group.member_count = member_count
        group.gross_spend_usd = round(gross_spend, 4)
        group.total_tokens = total_tokens
        return group

    def list_groups(self) -> list[QuotaGroup]:
        with self._lock:
            result = []
            for group in self._groups.values():
                copied = group.model_copy(deep=True)
                result.append(self._enrich_group_stats(copied))
            return result

    def get_group(self, group_id: str) -> QuotaGroup | None:
        with self._lock:
            group = self._groups.get(group_id.strip().lower())
            if not group:
                return None
            copied = group.model_copy(deep=True)
            return self._enrich_group_stats(copied)

    def create_group(self, group: QuotaGroup) -> QuotaGroup:
        with self._lock:
            key = group.group_id.strip().lower()
            now = datetime.now(UTC)
            group.created_at = now
            group.updated_at = now
            self._groups[key] = group.model_copy(deep=True)
            copied = self._groups[key].model_copy(deep=True)
            return self._enrich_group_stats(copied)

    def update_group(self, group_id: str, updates: dict) -> QuotaGroup | None:
        with self._lock:
            key = group_id.strip().lower()
            group = self._groups.get(key)
            if not group:
                return None
            group_data = group.model_dump()
            for k, v in updates.items():
                if v is not None and k in group_data and k not in ("group_id", "created_at"):
                    group_data[k] = v
            group_data["updated_at"] = datetime.now(UTC)
            self._groups[key] = QuotaGroup(**group_data)
            copied = self._groups[key].model_copy(deep=True)
            return self._enrich_group_stats(copied)

    def delete_group(self, group_id: str) -> bool:
        with self._lock:
            key = group_id.strip().lower()
            # Protect default group
            if key == "business-users":
                return False
            if key not in self._groups:
                return False
            del self._groups[key]
            # Reassign members of deleted group to business-users
            now = datetime.now(UTC)
            for user in self._users.values():
                if user.group_id == key:
                    user.group_id = "business-users"
                    user.updated_at = now
            return True

    def bulk_assign_group_members(self, group_id: str, emails: list[str]) -> int:
        with self._lock:
            now = datetime.now(UTC)
            count = 0
            for email in emails:
                clean_email = email.strip().lower()
                if not clean_email:
                    continue
                if clean_email in self._users:
                    self._users[clean_email].group_id = group_id
                    self._users[clean_email].updated_at = now
                else:
                    self._users[clean_email] = User(
                        email=clean_email,
                        group_id=group_id,
                        status=UserStatus.ACTIVE,
                        is_exempt=False,
                        has_custom_quota=False,
                        current_week=CurrentWeekUsage(
                            week_id="2026-W41",
                            quota_credits_usd=10.0,
                            remaining_credit_usd=10.0,
                            overage_buffer_usd=2.0,
                            window_start_utc=now,
                        ),
                        created_at=now,
                        updated_at=now,
                    )
                count += 1
            return count

