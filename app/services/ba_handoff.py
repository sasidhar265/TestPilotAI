"""Current-baseline human BA sign-off controls BA backlog authoring."""

import json


def backlog_drafting(db, project: str, baseline: int, role: str) -> dict:
    rows = db.execute(
        "SELECT data FROM ba_review_runs WHERE project=? ORDER BY rowid DESC", (project,)
    )
    runs = (json.loads(row[0]) for row in rows)
    current = next((run for run in runs if run["baseline"] == baseline), None)
    signoff = (current or {}).get("signoff") or {}
    invalidated = any(
        event["created_at"] > signoff.get("created_at", "")
        and (
            event["action"] in {"source_changed", "requirement_changed"}
            or (
                event.get("decision") == "changes_requested"
                and event.get("target")
                in {
                    "brd_upload",
                    "requirements_analysis",
                    "ba_validation",
                    "clarification",
                    "stakeholder_approval",
                }
            )
        )
        for (raw,) in db.execute("SELECT data FROM lifecycle_events WHERE project=?", (project,))
        for event in [json.loads(raw)]
    )
    signed = bool(
        current
        and current["status"] == "completed"
        and signoff.get("human")
        and signoff.get("baseline") == baseline
        and not invalidated
    )
    return dict(
        allowed=signed and role in {"ba", "admin", "product_owner"},
        signed_off=signed,
        baseline=baseline,
        review_id=(current or {}).get("id"),
        reason=(
            "Create linked user-story drafts in Backlog. "
            "Business approval and product-owner planning remain separate."
        )
        if signed
        else (
            "Complete the current BRD's AI review and human BA sign-off "
            "before creating user stories."
        ),
    )
