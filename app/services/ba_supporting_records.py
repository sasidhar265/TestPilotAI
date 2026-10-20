"""Persist source-linked AI drafts atomically with their completed BA review."""

import hashlib
import json

from app.services.project_lifecycle import ProjectLifecycle, timestamp
from app.services.sdlc import SDLCError


def populate_supporting_records(db, run: dict) -> dict:
    project, baseline = run["project"], run["baseline"]
    state = ProjectLifecycle.state(db, project)
    if state["baseline"] != baseline or state["stage"] not in {
        "requirements_analysis",
        "ba_validation",
        "clarification",
        "stakeholder_approval",
    }:
        raise SDLCError("The BRD or approval stage changed before supporting drafts were saved")
    created, existing = [], []
    for requirement in run["output"]["requirements"]:
        identity = f"{project}:{baseline}:{requirement['requirement_id']}"
        identifier = hashlib.sha256(identity.encode()).hexdigest()[:32]
        if db.execute(
            "SELECT 1 FROM work_items WHERE id=? AND project=?", (identifier, project)
        ).fetchone():
            existing.append(identifier)
            continue
        references = [
            f"BRD v{baseline} · {ref['section_id']}: {ref['quote']}"
            for ref in requirement["source_references"]
            if ref["source_id"] == "BRD"
        ]
        references.append(f"/api/sdlc/projects/{project}/ba-reviews/{run['id']}")
        record = dict(
            id=identifier,
            base_version=0,
            version=1,
            kind="requirement",
            baseline=baseline,
            title=requirement["title"],
            description=requirement["description"],
            status="draft",
            priority="medium",
            estimate=None,
            assignee="",
            sprint="",
            links=[],
            link_versions={},
            acceptance_criteria=requirement["acceptance_criteria_drafts"],
            references=references,
            author="BA Agent",
            updated_at=timestamp(),
            ai_origin=dict(
                review_id=run["id"],
                requirement_id=requirement["requirement_id"],
                baseline=baseline,
                requested_by=run["actor"],
                human=False,
            ),
        )
        raw = json.dumps(record)
        db.execute("INSERT INTO work_items VALUES (?,?,?)", (identifier, project, raw))
        db.execute("INSERT INTO work_item_versions VALUES (?,?,?,?)", (identifier, project, 1, raw))
        created.append(identifier)
    if created:
        state["revision"] += 1
        ProjectLifecycle.put(db, project, state)
        ProjectLifecycle.event(
            db,
            project,
            dict(
                action="ai_requirements_drafted",
                actor="BA Agent",
                requested_by=run["actor"],
                baseline=baseline,
                review_id=run["id"],
                work_items=created,
                human=False,
                comment=(
                    f"Created {len(created)} draft requirements from BRD v{baseline}; "
                    "human review required."
                ),
                created_at=timestamp(),
            ),
        )
    return dict(created=created, existing=existing, baseline=baseline)
