"""Integration tests for all REST API endpoints."""


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "antigravity-quota-portal"


def test_list_users(client):
    response = client.get("/api/users")
    assert response.status_code == 200
    users = response.json()
    assert len(users) >= 5


def test_get_user_detail(client):
    response = client.get("/api/users/alice.chen@example.com")
    assert response.status_code == 200
    user = response.json()
    assert user["email"] == "alice.chen@example.com"
    assert "current_week" in user
    assert user["current_week"]["quota_credits_usd"] == 25.0


def test_create_user_sets_window_start_utc(client):
    payload = {
        "email": "new.developer@example.com",
        "is_exempt": False,
        "has_custom_quota": False,
    }
    response = client.post("/api/users", json=payload)
    assert response.status_code == 201
    user = response.json()
    assert user["email"] == "new.developer@example.com"
    assert user["current_week"]["window_start_utc"] is not None
    assert "week_id" in user["current_week"]


def test_update_user_quota(client):
    payload = {
        "has_custom_quota": True,
        "custom_quota_usd": 50.0,
        "custom_overage_usd": 10.0,
    }
    response = client.patch("/api/users/bob.martin@example.com", json=payload)
    assert response.status_code == 200
    updated = response.json()
    assert updated["has_custom_quota"] is True
    assert updated["custom_quota_usd"] == 50.0
    assert updated["current_week"]["quota_credits_usd"] == 50.0


def test_toggle_user_lock(client):
    response = client.post("/api/users/bob.martin@example.com/lock")
    assert response.status_code == 200
    user = response.json()
    assert user["status"] == "MANUALLY_DISABLED"

    # Unlock again
    response_unlock = client.post("/api/users/bob.martin@example.com/lock")
    assert response_unlock.status_code == 200
    user_unlocked = response_unlock.json()
    assert user_unlocked["status"] == "ACTIVE"


def test_get_and_update_config(client):
    response = client.get("/api/config")
    assert response.status_code == 200
    config = response.json()
    assert "default_quota_usd" in config

    update_payload = {"default_quota_usd": 15.0}
    response_put = client.put("/api/config", json=update_payload)
    assert response_put.status_code == 200
    assert response_put.json()["default_quota_usd"] == 15.0


def test_publish_and_sync(client):
    response = client.post("/api/evaluator/publish")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["users_evaluated"] >= 5


def test_kpi_stats(client):
    response = client.get("/api/evaluator/kpis")
    assert response.status_code == 200
    kpis = response.json()
    assert "active_developers" in kpis
    assert "total_gross_usage_usd" in kpis
    assert "total_tokens_this_week" in kpis


def test_audit_log_endpoint(client):
    response = client.get("/api/audit?limit=10")
    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)
    assert len(events) >= 1


def test_create_and_delete_user(client):
    new_email = "new.dev@example.com"
    # Create user
    res_create = client.post("/api/users", json={"email": new_email, "is_exempt": False})
    assert res_create.status_code == 201
    assert res_create.json()["email"] == new_email

    # Get user
    res_get = client.get(f"/api/users/{new_email}")
    assert res_get.status_code == 200

    # Delete user
    res_del = client.delete(f"/api/users/{new_email}")
    assert res_del.status_code == 200
    assert res_del.json()["email"] == new_email

    # Verify deleted
    res_get2 = client.get(f"/api/users/{new_email}")
    assert res_get2.status_code == 404


def test_kpis_handles_pool_client_exception(client):
    """Verify /api/evaluator/kpis returns 200 even if pool_client raises exception."""
    from unittest.mock import MagicMock
    from app.api.deps import get_pool_client
    from app.main import app

    mock_pool = MagicMock()
    mock_pool.get_pool_stats.side_effect = RuntimeError("Telemetry API unreachable")

    app.dependency_overrides[get_pool_client] = lambda: mock_pool
    try:
        response = client.get("/api/evaluator/kpis")
        assert response.status_code == 200
        data = response.json()
        assert "active_developers" in data
    finally:
        app.dependency_overrides.pop(get_pool_client, None)


def test_create_user_handles_pool_client_exception(client):
    """Verify /api/users succeeds and resolves fallback window even if pool_client raises exception."""
    from unittest.mock import MagicMock
    from app.api.deps import get_pool_client
    from app.main import app

    mock_pool = MagicMock()
    mock_pool.get_pool_stats.side_effect = RuntimeError("Telemetry API unreachable")

    app.dependency_overrides[get_pool_client] = lambda: mock_pool
    try:
        payload = {
            "email": "resilient.user@example.com",
            "is_exempt": False,
            "has_custom_quota": False,
        }
        response = client.post("/api/users", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "resilient.user@example.com"
        assert data["current_week"]["window_start_utc"] is not None
    finally:
        app.dependency_overrides.pop(get_pool_client, None)


def test_auth_me_dual_mode_iap_and_proxy_impersonation(client):
    """Verify /api/auth/me works seamlessly across GCLB+IAP headers and Proxy/Direct headers, including Concierge SA impersonation."""
    # 1. Direct browser user via GCLB + IAP header
    res_iap_user = client.get(
        "/api/auth/me",
        headers={"X-Goog-Authenticated-User-Email": "accounts.google.com:alice.chen@example.com"},
    )
    assert res_iap_user.status_code == 200
    data_iap_user = res_iap_user.json()
    assert data_iap_user["email"] == "alice.chen@example.com"
    assert data_iap_user["caller_email"] == "alice.chen@example.com"
    assert data_iap_user["is_impersonating"] is False

    # 2. Concierge Agent calling through GCLB + IAP on behalf of an employee
    res_iap_concierge = client.get(
        "/api/auth/me",
        headers={
            "X-Goog-Authenticated-User-Email": "accounts.google.com:antigravity-concierge@example.iam.gserviceaccount.com",
            "X-Impersonate-User": "alice.chen@example.com",
        },
    )
    assert res_iap_concierge.status_code == 200
    data_iap_concierge = res_iap_concierge.json()
    assert data_iap_concierge["email"] == "alice.chen@example.com"
    assert data_iap_concierge["caller_email"] == "antigravity-concierge@example.iam.gserviceaccount.com"
    assert data_iap_concierge["is_impersonating"] is True

    # 3. Vertex AI Reasoning Engine Service Agent calling directly in Proxy / Direct Cloud Run mode
    res_proxy_re = client.get(
        "/api/auth/me",
        headers={
            "X-User-Email": "service-123456789@gcp-sa-aiplatform-re.iam.gserviceaccount.com",
            "X-Impersonate-User": "bob.martin@example.com",
        },
    )
    assert res_proxy_re.status_code == 200
    data_proxy_re = res_proxy_re.json()
    assert data_proxy_re["email"] == "bob.martin@example.com"
    assert data_proxy_re["caller_email"] == "service-123456789@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
    assert data_proxy_re["is_impersonating"] is True
