"""Google Cloud Firestore Native mode client."""

import logging
from datetime import UTC, datetime

from google.cloud import firestore

from app.audit.emitter import BaseAuditEmitter
from app.db.models import (
    DEFAULT_MODEL_PRICING,
    AppConfig,
    AuditEvent,
    CreditPoolStats,
    CurrentWeekUsage,
    ModelPricing,
    QuotaGroup,
    User,
    UserStatus,
    WeeklySnapshot,
)

logger = logging.getLogger(__name__)


class FirestoreDatabase:
    """Production client for Google Cloud Firestore Native Database."""

    def __init__(
        self,
        project_id: str,
        database: str = "(default)",
        audit_emitter: BaseAuditEmitter | None = None,
    ):
        self.project_id = project_id
        self.audit_emitter = audit_emitter
        self.client = firestore.Client(project=project_id, database=database)
        self.config_collection = self.client.collection("config")
        self.users_collection = self.client.collection("users")
        self.groups_collection = self.client.collection("groups")
        self.audit_collection = self.client.collection("audit_events")

    def get_config(self) -> AppConfig:
        try:
            doc_ref = self.config_collection.document("app_config")
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict() or {}
                # Parse models dict
                models_data = data.get("models", {})
                models = {}
                for k, v in models_data.items():
                    models[k] = ModelPricing(**v)
                if not models:
                    models = DEFAULT_MODEL_PRICING
                else:
                    # Auto-merge any newly defined default models (e.g. gemini-3.8-flash)
                    for def_k, def_v in DEFAULT_MODEL_PRICING.items():
                        if def_k not in models:
                            models[def_k] = def_v
                data["models"] = models
                return AppConfig(**data)
            else:
                # Initialize default config doc
                default_config = AppConfig()
                self.update_config(default_config)
                return default_config
        except Exception as e:
            logger.error(f"Error fetching Firestore app config: {e}", exc_info=True)
            return AppConfig()

    def update_config(self, config: AppConfig) -> AppConfig:
        doc_ref = self.config_collection.document("app_config")
        doc_ref.set(config.model_dump(mode="json"), merge=True)
        return config

    def get_user(self, email: str) -> User | None:
        key = email.lower().strip()
        doc = self.users_collection.document(key).get()
        if doc.exists:
            return User(**doc.to_dict())
        return None

    def list_users(self) -> list[User]:
        docs = self.users_collection.stream()
        users = []
        for doc in docs:
            try:
                users.append(User(**doc.to_dict()))
            except Exception as e:
                logger.error(f"Error deserializing user {doc.id}: {e}")
        return users

    def save_user(self, user: User) -> User:
        user.updated_at = datetime.now(UTC)
        key = user.email.lower().strip()
        self.users_collection.document(key).set(user.model_dump(mode="json"), merge=True)
        return user

    def delete_user(self, email: str) -> bool:
        key = email.lower().strip()
        doc_ref = self.users_collection.document(key)
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.delete()
            return True
        return False

    def save_users(self, users: list[User]) -> None:
        batch = self.client.batch()
        now = datetime.now(UTC)
        for user in users:
            user.updated_at = now
            key = user.email.lower().strip()
            doc_ref = self.users_collection.document(key)
            batch.set(doc_ref, user.model_dump(mode="json"), merge=True)
        batch.commit()

    def add_audit_event(self, event: AuditEvent) -> None:
        doc_ref = self.audit_collection.document(event.event_id)
        doc_ref.set(event.model_dump(mode="json"))
        if self.audit_emitter:
            self.audit_emitter.emit(event)

    def list_audit_events(self, limit: int = 100) -> list[AuditEvent]:
        query = self.audit_collection.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit)
        docs = query.stream()
        events = []
        for doc in docs:
            try:
                events.append(AuditEvent(**doc.to_dict()))
            except Exception as e:
                logger.error(f"Error deserializing audit event {doc.id}: {e}")
        return events

    def save_weekly_snapshot(self, user_email: str, snapshot: WeeklySnapshot) -> None:
        key = user_email.lower().strip()
        snap_ref = self.users_collection.document(key).collection("snapshots").document(snapshot.week_id)
        snap_ref.set(snapshot.model_dump(mode="json"))

    def list_weekly_snapshots(self, user_email: str, limit: int = 52) -> list[WeeklySnapshot]:
        key = user_email.lower().strip()
        snaps = (
            self.users_collection.document(key)
            .collection("snapshots")
            .order_by("week_id", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        return [WeeklySnapshot(**doc.to_dict()) for doc in snaps if doc.exists]

    def get_credit_pool(self) -> CreditPoolStats | None:
        try:
            doc = self.config_collection.document("credit_pool").get()
            if doc.exists:
                return CreditPoolStats(**(doc.to_dict() or {}))
        except Exception as e:
            logger.error(f"Error fetching credit pool doc from Firestore: {e}")
        return None

    def save_credit_pool(self, pool: CreditPoolStats) -> None:
        try:
            self.config_collection.document("credit_pool").set(pool.model_dump(mode="json"))
        except Exception as e:
            logger.error(f"Error saving credit pool doc to Firestore: {e}")

    def _enrich_group_stats(self, group: QuotaGroup) -> QuotaGroup:
        try:
            users_docs = self.users_collection.where("group_id", "==", group.group_id).stream()
            member_count = 0
            gross_spend = 0.0
            total_tokens = 0
            for doc in users_docs:
                user_data = doc.to_dict() or {}
                member_count += 1
                cw = user_data.get("current_week", {})
                gross_spend += cw.get("gross_spend_usd", 0.0)
                total_tokens += cw.get("total_tokens", 0)
            group.member_count = member_count
            group.gross_spend_usd = round(gross_spend, 4)
            group.total_tokens = total_tokens
        except Exception as e:
            logger.error(f"Error enriching stats for group {group.group_id}: {e}")
        return group

    def list_groups(self) -> list[QuotaGroup]:
        try:
            docs = self.groups_collection.stream()
            groups = []
            for doc in docs:
                try:
                    g = QuotaGroup(**doc.to_dict())
                    groups.append(self._enrich_group_stats(g))
                except Exception as e:
                    logger.error(f"Error deserializing group {doc.id}: {e}")
            if not groups:
                self._seed_default_groups()
                return self.list_groups()
            return groups
        except Exception as e:
            logger.error(f"Error listing groups from Firestore: {e}")
            return []

    def _seed_default_groups(self):
        now = datetime.now(UTC)
        dev_group = QuotaGroup(
            group_id="developers",
            display_name="Developers",
            description="Engineering and development teams with higher inference quotas",
            weekly_quota_usd=50.0,
            overage_buffer_usd=10.0,
            is_exempt=False,
            created_at=now,
            updated_at=now,
        )
        biz_group = QuotaGroup(
            group_id="business-users",
            display_name="Business Users",
            description="Standard business users with standard tier quotas",
            weekly_quota_usd=10.0,
            overage_buffer_usd=2.0,
            is_exempt=False,
            created_at=now,
            updated_at=now,
        )
        self.groups_collection.document("developers").set(dev_group.model_dump(mode="json"))
        self.groups_collection.document("business-users").set(biz_group.model_dump(mode="json"))

    def get_group(self, group_id: str) -> QuotaGroup | None:
        try:
            key = group_id.strip().lower()
            doc = self.groups_collection.document(key).get()
            if doc.exists:
                g = QuotaGroup(**doc.to_dict())
                return self._enrich_group_stats(g)
        except Exception as e:
            logger.error(f"Error fetching group {group_id}: {e}")
        return None

    def create_group(self, group: QuotaGroup) -> QuotaGroup:
        key = group.group_id.strip().lower()
        now = datetime.now(UTC)
        group.created_at = now
        group.updated_at = now
        self.groups_collection.document(key).set(group.model_dump(mode="json"))
        return self._enrich_group_stats(group)

    def update_group(self, group_id: str, updates: dict) -> QuotaGroup | None:
        key = group_id.strip().lower()
        doc_ref = self.groups_collection.document(key)
        doc = doc_ref.get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        for k, v in updates.items():
            if v is not None and k not in ("group_id", "created_at"):
                data[k] = v
        data["updated_at"] = datetime.now(UTC).isoformat()
        doc_ref.set(data, merge=True)
        return self.get_group(key)

    def delete_group(self, group_id: str) -> bool:
        key = group_id.strip().lower()
        if key == "business-users":
            return False
        doc_ref = self.groups_collection.document(key)
        if not doc_ref.get().exists:
            return False
        doc_ref.delete()
        now = datetime.now(UTC)
        users_docs = self.users_collection.where("group_id", "==", key).stream()
        for doc in users_docs:
            self.users_collection.document(doc.id).update({"group_id": "business-users", "updated_at": now.isoformat()})
        return True

    def bulk_assign_group_members(self, group_id: str, emails: list[str]) -> int:
        now = datetime.now(UTC)
        count = 0
        batch = self.client.batch()
        for email in emails:
            clean_email = email.strip().lower()
            if not clean_email:
                continue
            user_ref = self.users_collection.document(clean_email)
            user_doc = user_ref.get()
            if user_doc.exists:
                batch.update(user_ref, {"group_id": group_id, "updated_at": now.isoformat()})
            else:
                new_user = User(
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
                batch.set(user_ref, new_user.model_dump(mode="json"))
            count += 1
            if count % 400 == 0:
                batch.commit()
                batch = self.client.batch()
        batch.commit()
        return count

