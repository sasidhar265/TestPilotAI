"""Review storage tests use explicitly synthetic agent documents, never fake live AI."""

import pytest
from test_project_lifecycle import item, reach

from app.services.project_lifecycle import ProjectLifecycle
from app.services.project_reviews import ProjectReviews
from app.services.project_work_items import ProjectWorkItems
from app.services.sdlc import SDLCError, SDLCStore


@pytest.fixture
def review_project(tmp_path):
    store = SDLCStore(tmp_path / "memory.db")
    project = store.create("Inline review", "ba-user")["id"]
    store.save(project, "ba-user", "requirements-input", {"document": "Synthetic BRD"}, 0, [])
    records = ProjectWorkItems(store)
    requirement = records.save(project, "ba-user", "ba", item("requirement", "Reviewed scope"))
    return store, project, records, requirement, ProjectReviews(store)


def annotation(version=1, **changes):
    return (
        dict(
            base_version=version,
            action="comment",
            comment="Clarify the acceptance criteria",
            source=None,
        )
        | changes
    )


def test_comments_versions_and_approval_are_distinct_and_persist(review_project):
    store, project, records, requirement, reviews = review_project
    with store.connect() as db:
        db.execute("INSERT INTO project_members VALUES (?,?)", (project, "stakeholder"))
    reviews.annotate(
        project, requirement["id"], "stakeholder", "business_stakeholder", annotation()
    )
    records.save(
        project, "ba-user", "ba", dict(requirement, base_version=1, description="Clarified")
    )
    detail = ProjectReviews(SDLCStore(store.path.parent / "memory.db")).detail(
        project, requirement["id"], "stakeholder", "business_stakeholder"
    )
    assert [v["version"] for v in detail["versions"]] == [2, 1]
    assert detail["annotations"][0]["base_version"] == 1
    assert detail["annotations"][0]["actor"] == "stakeholder"
    assert detail["editable_fields"] == []
    assert not records.list(project, "stakeholder")[0]["approved"]
    flow = ProjectLifecycle(store)
    reach(flow, project, "stakeholder_approval")
    state = flow.snapshot(project, "stakeholder", "business_stakeholder")
    flow.transition(
        project,
        "stakeholder",
        "business_stakeholder",
        dict(revision=state["revision"], decision="approved", comment="Reviewed clarified v2"),
        human=True,
    )
    assert records.list(project, "stakeholder")[0]["approved"]
    saved = records.save(
        project,
        "ba-user",
        "ba",
        dict(detail["item"], base_version=2, description="Changed after approval"),
    )
    assert saved["version"] == 3
    assert not records.list(project, "stakeholder")[0]["approved"]
    assert flow.snapshot(project, "ba-user", "ba")["stage"] == "requirements_analysis"


def test_stale_or_cross_project_comments_cannot_write(review_project):
    store, project, records, requirement, reviews = review_project
    records.save(project, "ba-user", "ba", dict(requirement, base_version=1, title="Newer"))
    with pytest.raises(SDLCError, match="Record changed"):
        reviews.annotate(project, requirement["id"], "ba-user", "ba", annotation())
    other = store.create("Other project", "ba-user")["id"]
    with pytest.raises(SDLCError, match="Work item not found"):
        reviews.detail(other, requirement["id"], "ba-user", "ba")
    with pytest.raises(SDLCError, match="Project not found"):
        reviews.detail(project, requirement["id"], "outsider", "admin")
    assert reviews.detail(project, requirement["id"], "ba-user", "ba")["annotations"] == []


def test_suggestions_require_real_current_artifact_and_never_apply_record_changes(review_project):
    store, project, records, requirement, reviews = review_project
    source = dict(stage="requirements", version=1, task="synthetic-task")
    payload = annotation(action="use_draft", source=source)
    with pytest.raises(SDLCError, match="Suggestion source"):
        reviews.annotate(project, requirement["id"], "ba-user", "ba", payload)
    store.save(
        project,
        "ba-user",
        "requirements",
        dict(
            document="Synthetic unit-test agent fixture, not a live result",
            tasks=[
                dict(
                    id="synthetic-task",
                    title="Clarify scope",
                    acceptance_criteria=["Supplied fixture criterion"],
                    requirement_refs=["BRD:1"],
                )
            ],
        ),
        0,
        [dict(stage="requirements-input", version=1)],
    )
    reviews.annotate(project, requirement["id"], "ba-user", "ba", payload)
    detail = reviews.detail(project, requirement["id"], "ba-user", "ba")
    assert detail["suggestions"][0]["source_references"] == ["BRD:1"]
    assert detail["item"]["version"] == 1 and detail["item"]["acceptance_criteria"] == []
    assert detail["annotations"][0]["action"] == "use_draft"
    with pytest.raises(PermissionError, match="role"):
        reviews.annotate(project, requirement["id"], "ba-user", "business_stakeholder", payload)
    store.save(project, "ba-user", "requirements-input", {"document": "Revised source"}, 1, [])
    assert reviews.detail(project, requirement["id"], "ba-user", "ba")["suggestions"] == []
    with pytest.raises(SDLCError, match="Suggestion source"):
        reviews.annotate(project, requirement["id"], "ba-user", "ba", payload)


def test_developer_field_policy_matches_story_scope_enforcement(review_project):
    store, project, records, requirement, reviews = review_project
    story = records.save(
        project, "ba-user", "product_owner", item("story", "Story", links=[requirement["id"]])
    )
    detail = reviews.detail(project, story["id"], "ba-user", "developer")
    assert detail["editable_fields"] == ["status", "references"]
    with pytest.raises(PermissionError, match="scope"):
        records.save(
            project, "ba-user", "developer", dict(story, base_version=1, title="Unauthorized")
        )
    assert reviews.detail(project, story["id"], "ba-user", "product_owner")["editable_fields"]
