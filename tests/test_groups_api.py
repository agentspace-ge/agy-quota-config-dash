"""Integration tests for Quota Groups REST API and User Group Integration."""

from starlette.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_groups():
    """Verify listing groups returns seeded default groups with aggregate metrics."""
    res = client.get("/api/groups")
    assert res.status_code == 200
    groups = res.json()
    assert len(groups) >= 2
    group_ids = [g["group_id"] for g in groups]
    assert "developers" in group_ids
    assert "business-users" in group_ids

    dev = next(g for g in groups if g["group_id"] == "developers")
    assert dev["weekly_quota_usd"] == 50.0
    assert dev["overage_buffer_usd"] == 10.0
    assert dev["member_count"] >= 2
    assert dev["gross_spend_usd"] >= 0.0


def test_create_and_get_group():
    """Verify creating a new quota group and retrieving it."""
    payload = {
        "group_id": "data-science",
        "display_name": "Data Science Team",
        "description": "Engineers and scientists doing model fine-tuning and evaluation",
        "weekly_quota_usd": 150.0,
        "overage_buffer_usd": 30.0,
        "is_exempt": False,
        "iam_group_email": "data-science-quota@example.com",
    }
    create_res = client.post("/api/groups", json=payload)
    assert create_res.status_code == 201
    group_data = create_res.json()
    assert group_data["group_id"] == "data-science"
    assert group_data["weekly_quota_usd"] == 150.0

    # Retrieve group
    get_res = client.get("/api/groups/data-science")
    assert get_res.status_code == 200
    assert get_res.json()["display_name"] == "Data Science Team"

    # Duplicate creation should fail
    dup_res = client.post("/api/groups", json=payload)
    assert dup_res.status_code == 400


def test_update_group_propagates_quota():
    """Verify updating group weekly quota updates non-custom members' quota."""
    # Create test group
    client.post(
        "/api/groups",
        json={
            "group_id": "qa-engineers",
            "display_name": "QA Engineers",
            "weekly_quota_usd": 30.0,
            "overage_buffer_usd": 5.0,
        },
    )

    # Create user in qa-engineers without custom quota
    client.post(
        "/api/users",
        json={
            "email": "qa.tester@example.com",
            "group_id": "qa-engineers",
            "has_custom_quota": False,
        },
    )

    user_before = client.get("/api/users/qa.tester@example.com").json()
    assert user_before["current_week"]["quota_credits_usd"] == 30.0

    # Update group quota to 45.0
    update_res = client.put(
        "/api/groups/qa-engineers",
        json={"weekly_quota_usd": 45.0, "overage_buffer_usd": 8.0},
    )
    assert update_res.status_code == 200

    user_after = client.get("/api/users/qa.tester@example.com").json()
    assert user_after["current_week"]["quota_credits_usd"] == 45.0
    assert user_after["current_week"]["overage_buffer_usd"] == 8.0


def test_delete_group_reassigns_users():
    """Verify deleting a group reassigns members to business-users and default group cannot be deleted."""
    # Attempt to delete business-users should be rejected
    del_default = client.delete("/api/groups/business-users")
    assert del_default.status_code == 400

    # Create temporary group and member
    client.post(
        "/api/groups",
        json={
            "group_id": "interns",
            "display_name": "Interns",
            "weekly_quota_usd": 5.0,
            "overage_buffer_usd": 1.0,
        },
    )
    client.post(
        "/api/users",
        json={
            "email": "intern.sam@example.com",
            "group_id": "interns",
        },
    )

    del_res = client.delete("/api/groups/interns")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True
    assert del_res.json()["reassigned_to"] == "business-users"

    # Verify user reassigned
    user = client.get("/api/users/intern.sam@example.com").json()
    assert user["group_id"] == "business-users"


def test_bulk_assign_group_members():
    """Verify bulk assigning users to a group."""
    # Create two users in business-users
    client.post(
        "/api/users",
        json={"email": "contractor1@example.com", "group_id": "business-users"},
    )
    client.post(
        "/api/users",
        json={"email": "contractor2@example.com", "group_id": "business-users"},
    )

    assign_res = client.post(
        "/api/groups/developers/members",
        json={
            "emails": ["contractor1@example.com", "contractor2@example.com"],
            "action": "add",
        },
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["assigned_count"] == 2

    # Verify both users are now in developers
    u1 = client.get("/api/users/contractor1@example.com").json()
    u2 = client.get("/api/users/contractor2@example.com").json()
    assert u1["group_id"] == "developers"
    assert u2["group_id"] == "developers"


def test_users_api_group_filter_and_update():
    """Verify filtering users by group_id and updating a user's group."""
    res = client.get("/api/users?group_id=developers")
    assert res.status_code == 200
    dev_users = res.json()
    assert len(dev_users) >= 2
    for u in dev_users:
        assert u["group_id"] == "developers"

    # Update a user's group from developers to business-users
    patch_res = client.patch(
        "/api/users/contractor1@example.com",
        json={"group_id": "business-users"},
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["group_id"] == "business-users"
    # Should inherit business-users quota ($10.0)
    assert updated["current_week"]["quota_credits_usd"] == 10.0
