"""Persistence invariants independent of HTTP routing and provider calls."""

import pytest

from app.services.sdlc import SDLCError, SDLCStore


def test_projects_revisions_and_review_history_survive_reopening(tmp_path):
    store = SDLCStore(tmp_path / "memory.db")
    project = store.create("Quotation delivery", "owner")
    plan = store.save(project["id"], "owner", "planning", {"document": "Scope"}, 0, [])
    store.review(project["id"], "owner", "planning", 1, "approved", "Scope agreed")
    store.save(project["id"], "owner", "planning", {"document": "Revised scope"}, 1, [])
    store.save(
        project["id"],
        "owner",
        "design",
        {"document": "Contract"},
        0,
        [{"stage": "planning", "version": plan["version"]}],
    )
    reopened = SDLCStore(tmp_path / "memory.db").snapshot(project["id"], "owner")
    assert len(reopened["artifacts"]) == 3
    assert reopened["reviews"][0]["version"] == 1
    assert reopened["artifacts"][0]["links"] == [{"stage": "planning", "version": 1}]
    assert store.projects("other") == []
    with pytest.raises(SDLCError, match="not found"):
        store.snapshot(project["id"], "other")


def test_stale_writes_reviews_and_invalid_links_are_rejected(tmp_path):
    store = SDLCStore(tmp_path / "memory.db")
    project = store.create("Project", "owner")["id"]
    store.save(project, "owner", "planning", {"document": "Plan"}, 0, [])
    with pytest.raises(SDLCError, match="newer version"):
        store.save(project, "owner", "planning", {"document": "Stale"}, 0, [])
    with pytest.raises(SDLCError, match="does not exist"):
        store.save(
            project,
            "owner",
            "design",
            {"document": "Design"},
            0,
            [{"stage": "planning", "version": 99}],
        )
    store.save(project, "owner", "planning", {"document": "New"}, 1, [])
    with pytest.raises(SDLCError, match="latest"):
        store.review(project, "owner", "planning", 1, "approved", "Old")
    store.save(project, "owner", "workflow", {"version": 1, "state": {}}, 0, [])
    with pytest.raises(SDLCError, match="drafts"):
        store.review(project, "owner", "workflow", 1, "approved", "No")
    assert len(store.snapshot(project, "owner")["artifacts"]) == 3


def test_sdlc_role_permissions():
    from app.role_access import operation_allowed

    for role in ("ba", "functional_tester", "automation_tester", "non_functional_tester"):
        assert operation_allowed(role, "/api/sdlc/projects", "POST")
        assert operation_allowed(role, "/api/sdlc/projects/p/artifacts/workflow", "POST")
        assert not operation_allowed(role, "/api/sdlc/projects/p/artifacts/release", "POST")
        assert not operation_allowed(
            role, "/api/sdlc/projects/p/artifacts/planning/reviews", "POST"
        )
    assert not operation_allowed("ba", "/api/sdlc/projects/p/artifacts/design", "POST")
    assert operation_allowed("ba", "/api/sdlc/projects/p/artifacts/requirements-input", "POST")
    assert operation_allowed("functional_tester", "/api/sdlc/projects/p/artifacts/testing", "POST")
