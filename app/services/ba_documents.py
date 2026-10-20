"""Downloadable business review evidence, derived only from saved project records."""

import csv
import io
import json
import zipfile
from collections import Counter

from app.services.ba_handoff import backlog_drafting
from app.services.project_lifecycle import ProjectLifecycle
from app.services.sdlc import SDLCError, SDLCStore


def business_documents(
    store: SDLCStore, project: str, actor: str, document: str
) -> tuple[bytes, str, str]:
    with store.connect() as db:
        db.execute("BEGIN")
        info = store.project(db, project, actor)
        state = ProjectLifecycle.state(db, project)
        baseline = state["baseline"]
        row = db.execute(
            "SELECT data FROM revisions WHERE project=? "
            "AND stage='requirements-input' AND version=?",
            (project, baseline),
        ).fetchone()
        if not row:
            raise SDLCError("Save the BRD baseline before downloading business documents")
        source = json.loads(row[0])
        runs = [
            json.loads(row[0])
            for row in db.execute(
                "SELECT data FROM ba_review_runs WHERE project=? ORDER BY rowid DESC", (project,)
            )
        ]
        current = next((run for run in runs if run["baseline"] == baseline), None)
        records = [
            json.loads(row[0])
            for row in db.execute("SELECT data FROM work_items WHERE project=?", (project,))
        ]
        audit = [
            json.loads(row[0])
            for row in db.execute(
                "SELECT data FROM lifecycle_events WHERE project=? ORDER BY sequence", (project,)
            )
        ]
        from app.services.requirements_reviews import approval_context

        context = approval_context(db, project, state, audit)
        drafting = backlog_drafting(db, project, baseline, "ba")
    report = (current or {}).get("output") or context.get("assessments", {}).get(
        "business_analysis", {}
    ).get("report", {})
    lines = [
        f"# Business review · BRD v{baseline}",
        f"Project: {info['name']}",
        f"Project ID: {project}",
        f"Lifecycle stage: {state['stage']}",
        "",
        "## Business summary",
        report.get("summary", "Not yet assessed."),
        "",
        "## Business scope",
    ]
    lines.extend(f"- {item}" for item in report.get("scope", []))
    lines.append("\n## Deliverables and business impact")
    for item in report.get("business_deliverables", []):
        for field in (
            "expectation",
            "deliverable",
            "business_benefit",
            "delivery_impact",
            "benefit_basis",
            "success_measure",
            "document_quote",
        ):
            lines.append(
                f"- {field.replace('_', ' ').capitalize()}: "
                f"{item.get(field) or 'Not specified in the BRD'}"
            )
        lines.append("")
    if not report.get("business_deliverables"):
        lines.append("Structured business deliverables have not been assessed for this baseline.")
    lines.extend(
        [
            "\n## BA sign-off",
            json.dumps((current or {}).get("signoff"), indent=2),
            "\nBusiness benefits are reported expectations, not measured financial outcomes. "
            "Human BA sign-off does not grant business or release approval.",
            "\n## Review limitations",
            *[
                f"- {item}"
                for item in report.get(
                    "analysis_limitations", report.get("knowledge_limitations", [])
                )
            ],
        ]
    )
    metrics = io.StringIO(newline="")
    writer = csv.writer(metrics)
    writer.writerow(["metric", "value", "basis"])
    writer.writerow(["BRD baseline", baseline, "Saved project baseline"])
    writer.writerow(
        [
            "Current review status",
            (current or {}).get("status", "not_started"),
            "Latest review for this baseline",
        ]
    )
    writer.writerow(
        [
            "Extracted requirements",
            len(report.get("requirements", [])),
            "Current review output; not a completeness score",
        ]
    )
    findings = report.get("findings", [])
    writer.writerow(["Findings", len(findings), "Current saved assessment"])
    for status, count in sorted(
        Counter(item.get("review_status", "unreviewed") for item in findings).items()
    ):
        writer.writerow([f"Findings: {status}", count, "Recorded human finding dispositions"])
    for key in ("topics_reviewed", "covered", "gaps", "conflicts"):
        writer.writerow(
            [
                f"Domain {key}",
                report.get("domain_validation", {}).get(key, "not_reported"),
                "Reported domain assessment; not inferred",
            ]
        )
    writer.writerow(
        [
            "Human BA sign-off",
            bool((current or {}).get("signoff", {}).get("human"))
            if (current or {}).get("signoff")
            else False,
            "Current saved review",
        ]
    )
    writer.writerow(
        [
            "Effective current BA sign-off",
            drafting["signed_off"],
            "Invalidated by source changes or review rework",
        ]
    )
    history = dict(
        requirements_assessments=context.get("assessments", {}),
        project=project,
        baseline=baseline,
        reviews=runs,
        lifecycle_events=audit,
        supporting_requirements=[item for item in records if item["kind"] == "requirement"],
    )
    docs = {
        "business-review": (
            "business-review.md",
            "text/markdown; charset=utf-8",
            "\n".join(lines).encode(),
        ),
        "metrics": ("review-metrics.csv", "text/csv; charset=utf-8", metrics.getvalue().encode()),
        "brd": (
            "saved-brd.txt",
            "text/plain; charset=utf-8",
            source["content"].get("document", "").encode(),
        ),
        "history": (
            "review-history.json",
            "application/json",
            json.dumps(history, ensure_ascii=False, indent=2).encode(),
        ),
    }
    prefix = f"ba-review-v{baseline}-"
    if document != "all":
        filename, media, data = docs[document]
        return data, prefix + filename, media
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as pack:
        for filename, _, data in docs.values():
            pack.writestr(filename, data)
    return archive.getvalue(), prefix + "business-documents.zip", "application/zip"
