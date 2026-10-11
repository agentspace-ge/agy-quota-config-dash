"""Dependency injection providers for database, BigQuery, and identity clients."""

import logging

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

