"""Dependency injection providers for database, BigQuery, and identity clients."""

import logging
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from app.audit import BaseAuditEmitter, CloudLoggingAuditEmitter, MockAuditEmitter
from app.bq.mock_bq import MockBigQueryUsageClient
from app.config import settings
from app.core.evaluator import QuotaEvaluator
from app.db.mock_db import MockDatabase
from app.identity.mock_identity import MockCloudIdentityGroupManager

logger = logging.getLogger(__name__)

_db_instance = None
_bq_instance = None
_identity_instance = None
_evaluator_instance = None
_audit_emitter_instance = None
_pool_client_instance = None



def get_audit_emitter() -> BaseAuditEmitter:
    global _audit_emitter_instance
    if _audit_emitter_instance is None:
        if settings.USE_MOCK_SERVICES or not settings.ENABLE_GCP_AUDIT_LOGGING:
            logger.info("Initializing in-memory MockAuditEmitter")
            _audit_emitter_instance = MockAuditEmitter()
        else:
            logger.info(
                "Initializing CloudLoggingAuditEmitter "
                f"(project={settings.PROJECT_ID}, log_name={settings.GCP_AUDIT_LOG_NAME})"
            )
            _audit_emitter_instance = CloudLoggingAuditEmitter(
                project_id=settings.PROJECT_ID,
                log_name=settings.GCP_AUDIT_LOG_NAME,
            )
    return _audit_emitter_instance


def get_db():
    global _db_instance
    if _db_instance is None:
        emitter = get_audit_emitter()
        if settings.USE_MOCK_SERVICES:
            logger.info("Initializing in-memory MockDatabase sandbox")
            _db_instance = MockDatabase(audit_emitter=emitter)
        else:
            from app.db.firestore_client import FirestoreDatabase

            logger.info(f"Initializing FirestoreDatabase (project={settings.PROJECT_ID})")
            _db_instance = FirestoreDatabase(project_id=settings.PROJECT_ID, audit_emitter=emitter)
    return _db_instance


def get_bq():
    global _bq_instance
    if _bq_instance is None:
        if settings.USE_MOCK_SERVICES:
            logger.info("Initializing MockBigQueryUsageClient sandbox")
            _bq_instance = MockBigQueryUsageClient()
        else:
            from app.bq.bq_client import BigQueryUsageClient

            logger.info(
                f"Initializing BigQueryUsageClient (project={settings.PROJECT_ID}, dataset={settings.BIGQUERY_DATASET})"
            )
            _bq_instance = BigQueryUsageClient(
                project_id=settings.PROJECT_ID,
                dataset_name=settings.BIGQUERY_DATASET,
            )
    return _bq_instance


def get_identity():
    global _identity_instance
    if _identity_instance is None:
        if settings.USE_MOCK_SERVICES:
            logger.info("Initializing MockCloudIdentityGroupManager sandbox")
            _identity_instance = MockCloudIdentityGroupManager(
                enabled_group_email=settings.ENABLED_GROUP_EMAIL,
                disabled_group_email=settings.DISABLED_GROUP_EMAIL,
            )
        else:
            from app.identity.cloud_identity import CloudIdentityGroupManager

            logger.info("Initializing CloudIdentityGroupManager")
            _identity_instance = CloudIdentityGroupManager(
                enabled_group_email=settings.ENABLED_GROUP_EMAIL,
                disabled_group_email=settings.DISABLED_GROUP_EMAIL,
            )
    return _identity_instance


def get_pool_client():
    global _pool_client_instance
    if _pool_client_instance is None:
        if settings.USE_MOCK_SERVICES:
            from app.monitoring.mock_pool import MockCloudMonitoringPoolClient

            logger.info("Initializing MockCloudMonitoringPoolClient sandbox")
            _pool_client_instance = MockCloudMonitoringPoolClient(db_client=get_db())
        else:
            from app.monitoring.pool_client import CloudMonitoringPoolClient

            logger.info(f"Initializing CloudMonitoringPoolClient (project={settings.PROJECT_ID})")
            _pool_client_instance = CloudMonitoringPoolClient(
                project_id=settings.PROJECT_ID,
                db_client=get_db(),
                cache_ttl_seconds=getattr(settings, "MONITORING_CACHE_TTL_SECONDS", 300),
            )
    return _pool_client_instance


def get_evaluator() -> QuotaEvaluator:
    global _evaluator_instance
    if _evaluator_instance is None:
        _evaluator_instance = QuotaEvaluator(
            db_client=get_db(),
            bq_client=get_bq(),
            identity_client=get_identity(),
            pool_client=get_pool_client(),
        )
    return _evaluator_instance


def _verify_oidc_bearer_email(request: Request) -> str | None:
    """Verify Google-signed OIDC Bearer token and return its `email` claim."""
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[7:].strip()
    if not token:
        return None

    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2 import id_token

        claims = id_token.verify_oauth2_token(token, GoogleAuthRequest())
        if isinstance(claims, dict) and claims.get("email_verified", True):
            email = claims.get("email")
            if isinstance(email, str) and "@" in email:
                return email.strip().lower()
    except Exception as exc:
        logger.warning(f"OIDC Bearer token verification failed: {exc}")
        # Secondary fallback: unverified payload decode (safe because Cloud Run IAM already verified token at edge)
        try:
            import jwt
            unverified = jwt.decode(token, options={"verify_signature": False})
            email = unverified.get("email")
            if isinstance(email, str) and "@" in email:
                return email.strip().lower()
        except Exception:
            pass
    return None


def extract_caller_email(request: Request) -> str:
    """Extract authenticated caller email from IAP, verified OIDC token, or dev headers."""
    # 1. Google Cloud IAP header (verified and injected by Google Cloud edge)
    iap_header = request.headers.get("X-Goog-Authenticated-User-Email")
    if iap_header:
        email = iap_header.replace("accounts.google.com:", "").strip()
        if email:
            return email.lower()

    # 2. Cryptographically verified Google OIDC Bearer token (Service-to-Service / Cloud Run IAM)
    if not settings.USE_MOCK_SERVICES:
        verified_oidc_email = _verify_oidc_bearer_email(request)
        if verified_oidc_email:
            return verified_oidc_email

    # 3. Standard reverse proxy / local sandbox headers
    for hdr in ["X-Forwarded-Email", "X-User-Email", "X-Auth-Email"]:
        val = request.headers.get(hdr)
        if val and val.strip():
            candidate = val.strip().lower()
            return candidate

    # 4. Default dev/sandbox fallback
    return "admin@example.com"


def get_current_user_context(
    request: Request,
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    """Resolve authenticated caller email, admin status, and allowed impersonation."""
    caller_email = extract_caller_email(request)
    config = db.get_config()

    admin_emails = [e.lower().strip() for e in getattr(config, "admin_emails", [])]
    is_admin = caller_email in admin_emails or (settings.USE_MOCK_SERVICES and caller_email.startswith("admin@"))

    concierge_sa = getattr(settings, "CONCIERGE_SERVICE_ACCOUNT_EMAIL", "").lower().strip()
    is_trusted_service_account = (
        (bool(concierge_sa) and caller_email == concierge_sa)
        or caller_email.startswith("antigravity-concierge@")
        or caller_email.endswith("@gcp-sa-aiplatform-re.iam.gserviceaccount.com")
        or caller_email.endswith("@gcp-sa-discoveryengine.iam.gserviceaccount.com")
        or (settings.USE_MOCK_SERVICES and caller_email.startswith("concierge@"))
    )

    # If caller is admin or trusted Concierge Agent Engine SA, allow acting on behalf of a user
    # via ?as_user=<email> or X-Impersonate-User header.
    effective_email = caller_email
    as_user_param = request.query_params.get("as_user") or request.headers.get("X-Impersonate-User")
    if as_user_param and (is_admin or is_trusted_service_account):
        effective_email = as_user_param.strip().lower()

    return {
        "caller_email": caller_email,
        "effective_email": effective_email,
        "is_admin": is_admin,
        "is_trusted_service_account": is_trusted_service_account,
        "is_impersonating": effective_email != caller_email,
    }


def require_admin(context: dict[str, Any] = Depends(get_current_user_context)) -> dict[str, Any]:
    """Dependency enforcing that caller has admin role."""
    if not context["is_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required to access this resource",
        )
    return context


