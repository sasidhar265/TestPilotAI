"""Operation and migration boundaries, without provider or HTTP dependencies."""

import sqlite3

import pytest

from app.config import Settings
from app.role_access import operation_allowed, payload_allowed
from app.roles import ROLE_LABELS, capabilities
from app.users import database, password_hash


@pytest.mark.parametrize("role", ROLE_LABELS)
def test_role_targets_are_explicit_and_unknown_roles_have_no_access(role):
    assert capabilities(role)["admin"] == (role == "admin")
    assert not operation_allowed("unknown", "/api/workflow/test-cases", "POST")


@pytest.mark.parametrize(
    "role,target,discipline",
    [
        ("functional_tester", "manual", "api"),
        ("automation_tester", "automation", "ui"),
        ("non_functional_tester", "manual", "performance"),
        ("non_functional_tester", "manual", "database"),
    ],
)
def test_tester_generation_rejects_other_routes_and_implicit_defaults(role, target, discipline):
    assert payload_allowed(
        role,
        "/api/workflow/test-cases",
        {"request": {"generation_target": target, "manual_testing_type": discipline}},
    )
    assert not payload_allowed(role, "/api/generate", {})
    assert not payload_allowed(role, "/api/generate", {"generation_target": "both"})


def test_ba_cannot_generate_or_execute_tests_through_alternate_routes():
    for path in [
        "/api/generate",
        "/api/agent/run",
        "/api/generate/document",
        "/api/jira/generate",
        "/api/workflow/test-cases",
        "/api/workflow/scenarios",
        "/api/output/accept",
        "/api/stlc/suites",
        "/api/stlc/cycles/example/pack",
        "/api/automation/run",
    ]:
        assert not operation_allowed("ba", path, "POST"), path
    assert operation_allowed("ba", "/api/workflow/stories", "POST")


def test_admin_management_and_script_boundaries():
    assert not operation_allowed("test_lead", "/api/admin/users", "GET")
    assert operation_allowed("admin", "/api/admin/users", "GET")
    assert not operation_allowed("functional_tester", "/api/step-definitions/reqnroll", "POST")
    assert not operation_allowed("automation_tester", "/api/script-packs/generate", "POST")
    assert operation_allowed("non_functional_tester", "/api/script-packs/generate", "POST")
    assert not payload_allowed(
        "automation_tester",
        "/api/export/csv",
        {"suite": {"test_cases": [{"execution_mode": "manual"}]}},
    )


def test_legacy_account_migration_preserves_identity_and_password_and_revokes_session(tmp_path):
    settings = Settings(_env_file=None, user_database_path=tmp_path / "users.db")
    hashed = password_hash("synthetic-test-password")
    with sqlite3.connect(settings.user_database_path) as connection:
        connection.execute("""CREATE TABLE users (
            username TEXT PRIMARY KEY COLLATE NOCASE, display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','user')),
            enabled INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1)""")
        connection.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
            ("Tester", "Test Person", hashed, "user", 1, 7),
        )
    with database(settings) as connection:
        row = dict(connection.execute("SELECT * FROM users").fetchone())
        assert row["role"] == "test_lead"
        assert row["password_hash"] == hashed
        assert row["first_name"] == "Test"
        assert row["last_name"] == "Person"
        assert row["version"] == 8
    with database(settings) as connection:
        assert connection.execute("SELECT version FROM users").fetchone()[0] == 8
