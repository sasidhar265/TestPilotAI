"""Project-isolated, immutable-baseline BA runs with optimistic human review and audit."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.agents.inline_business_analyst import InlineBusinessAnalyst, fingerprint, source_sections
from app.ba_review_models import FindingDecision, ReviewSignoff, ReviewStart
from app.config import Settings
from app.models import GenerateRequest
from app.services.ba_brd_revision import revised_document
from app.services.ba_supporting_records import populate_supporting_records
from app.services.project_lifecycle import ProjectLifecycle
from app.services.sdlc import SDLCError, SDLCStore
from app.uploaded_brd import verify_brd_receipt

logger = logging.getLogger(__name__)
ACTIVE = {"queued", "running"}
REVIEW_ROLES = {"ba", "admin", "test_lead"}
TASKS: dict[str, asyncio.Task] = {}


def now() -> str:
    return datetime.now(UTC).isoformat()


def review_blockers(db, project: str, baseline: int) -> list[str]:
    rows = db.execute(
        "SELECT data FROM ba_review_runs WHERE project=? ORDER BY rowid DESC", (project,)
    )
    runs = [json.loads(row[0]) for row in rows]
    current = next((run for run in runs if run["baseline"] == baseline), None)
    if not current:
        return ["The changed BRD requires a new inline BA review and sign-off."] if runs else []
    if current["status"] != "completed" or not current.get("signoff"):
        return ["Complete the current BRD's inline BA review and human BA sign-off first."]
    return []


class BAReviews:
    def __init__(self, store: SDLCStore, settings: Settings):
        self.store, self.settings = store, settings

    @staticmethod
    def writer(role: str, human: bool):
        if role not in REVIEW_ROLES or not human:
            raise PermissionError(
                "BA review actions require an authenticated BA, test lead or administrator"
            )

    @staticmethod
    def put(db, run):
        db.execute(
            "INSERT OR REPLACE INTO ba_review_runs VALUES (?,?,?)",
            (run["id"], run["project"], json.dumps(run)),
        )

    def get(self, db, project: str, actor: str, identifier: str) -> dict:
        self.store.project(db, project, actor)
        row = db.execute(
            "SELECT data FROM ba_review_runs WHERE project=? AND id=?", (project, identifier)
        ).fetchone()
        if not row:
            raise SDLCError("BA review not found")
        run = json.loads(row[0])
        if run["status"] in ACTIVE and run["expires_at"] < now():
            run.update(
                status="failed",
                progress="Analysis interrupted or timed out. Start reanalysis.",
                updated_at=now(),
                revision=run["revision"] + 1,
            )
            self.put(db, run)
        return run

    def snapshot(self, project: str, actor: str, identifier: str | None = None) -> dict:
        with self.store.connect() as db:
            self.store.project(db, project, actor)
            state = ProjectLifecycle.state(db, project)
            rows = db.execute(
                "SELECT id FROM ba_review_runs WHERE project=? ORDER BY rowid DESC", (project,)
            ).fetchall()
            history = []
            selected = None
            for (key,) in rows:
                run = self.get(db, project, actor, key)
                history.append(
                    {k: run[k] for k in ("id", "baseline", "status", "created_at", "revision")}
                )
                if (identifier == key) or (
                    identifier is None and selected is None and run["baseline"] == state["baseline"]
                ):
                    selected = run
            if identifier and selected is None:
                raise SDLCError("BA review not found")
            return dict(
                run=selected,
                history=history,
                baseline=state["baseline"],
                impacted_runs=[r["id"] for r in history if r["baseline"] != state["baseline"]],
            )

    def start(
        self, project: str, actor: str, role: str, payload: ReviewStart, *, human: bool
    ) -> tuple[dict, bool]:
        self.writer(role, human)
        # Read only server-held versioned source, never a browser-submitted document.
        with self.store.connect() as db:
            self.store.project(db, project, actor)
            state = ProjectLifecycle.state(db, project)
            if state["baseline"] != payload.baseline:
                raise SDLCError("BRD version changed. Reload before analysis")
            if state["stage"] not in {
                "requirements_analysis",
                "ba_validation",
                "clarification",
                "stakeholder_approval",
            }:
                raise SDLCError(
                    "Business approval is complete. Save a revised BRD baseline "
                    "before requesting a new BA analysis"
                )
            row = db.execute(
                "SELECT data FROM revisions WHERE project=? "
                "AND stage='requirements-input' AND version=?",
                (project, payload.baseline),
            ).fetchone()
            if not row:
                raise SDLCError("Save the BRD requirements baseline first")
            source = json.loads(row[0])
        try:
            request = GenerateRequest.model_validate(source["content"]["source_request"])
        except (KeyError, ValueError) as error:
            raise SDLCError("The saved BRD source is incomplete; return to Requirements") from error
        if request.uploaded_brd_receipt or request.uploaded_brd_text:
            if (
                not request.uploaded_brd_text
                or not request.uploaded_brd_receipt
                or not verify_brd_receipt(
                    request.uploaded_brd_text, request.uploaded_brd_receipt, self.settings
                )
            ):
                raise SDLCError("BRD verification failed. Upload and validate the source again")
        document = source["content"].get("document") or request.description
        if document.strip() != request.description.strip():
            raise SDLCError("Saved document and analysed source differ; re-save requirements")
        reviewer = InlineBusinessAnalyst(self.settings)
        sources, knowledge_key, limitations, scope = reviewer.review_knowledge(request)
        limitations = [
            *limitations,
            "Source locations refer to extracted text lines; original page and table layout "
            "metadata is unavailable for this baseline.",
        ]
        sections = source_sections(document)
        key = fingerprint(
            [payload.baseline, document, request.model_dump(mode="json"), knowledge_key, "1.0"]
        )
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.store.project(db, project, actor)
            if ProjectLifecycle.state(db, project)["baseline"] != payload.baseline:
                raise SDLCError("BRD version changed. Reload before analysis")
            prior = [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT data FROM ba_review_runs WHERE project=? ORDER BY rowid DESC",
                    (project,),
                )
            ]
            latest_for_baseline = next(
                (item["id"] for item in prior if item["baseline"] == payload.baseline), None
            )
            for item in prior:
                item = self.get(db, project, actor, item["id"])
                if item["status"] in ACTIVE:
                    if item["baseline"] == payload.baseline:
                        return item, False
                    item.update(
                        status="cancelled",
                        progress="Superseded by a changed BRD baseline",
                        revision=item["revision"] + 1,
                        updated_at=now(),
                    )
                    self.put(db, item)
                    if task := TASKS.get(item["id"]):
                        task.get_loop().call_soon_threadsafe(task.cancel)
                if (
                    not payload.force
                    and item["id"] == latest_for_baseline
                    and item["key"] == key
                    and item["status"] == "completed"
                ):
                    return item, False
            run = dict(
                id=uuid4().hex,
                project=project,
                baseline=payload.baseline,
                document_id=f"{project}:requirements-input",
                document_version=payload.baseline,
                key=key,
                schema_version="1.0",
                revision=1,
                status="queued",
                progress="Saved BRD queued for source-grounded BA analysis",
                actor=actor,
                provider=request.llm_model.value,
                created_at=now(),
                updated_at=now(),
                expires_at=(datetime.now(UTC) + timedelta(minutes=35)).isoformat(),
                sections=sections,
                knowledge_sources=sources,
                knowledge_fingerprint=knowledge_key,
                limitations=limitations,
                scope=scope,
                request=request.model_dump(mode="json"),
                focus_requirement=payload.requirement_id,
                output=None,
                decisions=[],
                signoff=None,
                brd_revision=source["content"].get("ba_revision"),
            )
            if payload.requirement_id and not any(
                r["baseline"] == payload.baseline
                and r.get("output")
                and any(
                    req["requirement_id"] == payload.requirement_id
                    for req in r["output"]["requirements"]
                )
                for r in prior
            ):
                raise SDLCError("Select an existing requirement for reanalysis")
            self.put(db, run)
            self.audit(db, run, actor, "analysis_requested", None, dict(provider=run["provider"]))
            return run, True

    @staticmethod
    def audit(db, run, actor, action, before, after):
        state = ProjectLifecycle.state(db, run["project"])
        state["revision"] += 1
        ProjectLifecycle.put(db, run["project"], state)
        ProjectLifecycle.event(
            db,
            run["project"],
            dict(
                action="ba_review_" + action,
                actor=actor,
                review_id=run["id"],
                baseline=run["baseline"],
                review_revision=run["revision"],
                before=before,
                after=after,
                created_at=now(),
            ),
        )

    async def execute(self, project: str, actor: str, identifier: str):
        task = asyncio.current_task()
        TASKS[identifier] = task
        try:
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                run = self.get(db, project, actor, identifier)
                if run["status"] != "queued":
                    return
                run.update(
                    status="running",
                    progress="Extracting requirements and reviewing in-house domain evidence",
                    updated_at=now(),
                    revision=run["revision"] + 1,
                )
                self.put(db, run)
            async with asyncio.timeout(1800):
                output = await InlineBusinessAnalyst(self.settings).analyse(
                    GenerateRequest.model_validate(run["request"]),
                    run["sections"],
                    run["knowledge_sources"],
                    run["limitations"],
                    run["focus_requirement"],
                )
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                run = self.get(db, project, actor, identifier)
                if run["status"] != "running":
                    return
                if ProjectLifecycle.state(db, project)["baseline"] != run["baseline"]:
                    raise SDLCError("BRD changed during analysis. Review the new baseline")
                # Unchanged proposals retain human rejection/resolution; no reapplication.
                previous = [
                    json.loads(row[0])
                    for row in db.execute(
                        "SELECT data FROM ba_review_runs WHERE project=? AND id<>? "
                        "ORDER BY rowid DESC",
                        (project, identifier),
                    )
                ]
                for finding in output["findings"]:
                    for old in previous:
                        if old["baseline"] != run["baseline"] or not old.get("output"):
                            continue
                        match = next(
                            (
                                f
                                for f in old["output"]["findings"]
                                if f["finding_id"] == finding["finding_id"]
                            ),
                            None,
                        )
                        if match:
                            finding["version"] = match["version"] + (
                                match["proposal_fingerprint"] != finding["proposal_fingerprint"]
                            )
                            if match["proposal_fingerprint"] == finding["proposal_fingerprint"]:
                                finding["review_status"] = match["review_status"]
                                finding["decision_origin_review"] = old["id"]
                                if "human_proposed_text" in match:
                                    finding["human_proposed_text"] = match["human_proposed_text"]
                            break
                run.update(
                    output=output,
                    status="completed",
                    progress="BA review required; no approval granted",
                    updated_at=now(),
                    revision=run["revision"] + 1,
                )
                run["review"] = dict(
                    document_id=run["document_id"],
                    document_version=run["baseline"],
                    analysis_run_id=run["id"],
                    readiness_status=output["readiness_status"],
                    summary=output["summary"],
                    scope=output["scope"],
                    analysis_limitations=output["analysis_limitations"],
                )
                run["handoff"] = dict(
                    ready_for_human_BA_review=True,
                    blockers=[
                        f["finding_id"] for f in output["findings"] if f["severity"] == "BLOCKER"
                    ],
                    outstanding_decisions=[
                        q["question_id"]
                        for q in output["business_questions"]
                        if q["blocking_status"]
                    ],
                    recommended_next_action="BA reviews findings before sign-off; "
                    "business approval is separate",
                )
                run["supporting_records"] = populate_supporting_records(db, run)
                self.put(db, run)
                self.audit(
                    db,
                    run,
                    actor,
                    "analysis_completed",
                    None,
                    dict(readiness=output["readiness_status"]),
                )
        except (Exception, asyncio.CancelledError) as error:
            logger.warning("ba_review_failed run=%s type=%s", identifier, type(error).__name__)
            with self.store.connect() as db:
                run = self.get(db, project, actor, identifier)
                if run["status"] in ACTIVE:
                    cancelled = isinstance(error, asyncio.CancelledError)
                    rejected = isinstance(error, ValueError) and not isinstance(error, SDLCError)
                    run.update(
                        status="cancelled" if cancelled else "failed",
                        progress="Analysis cancelled"
                        if cancelled
                        else (
                            "AI output failed source or schema validation. Retry analysis or "
                            "review source quality; no approval was granted."
                            if rejected
                            else "Analysis failed, timed out or its source changed. Check the "
                            "BRD and provider access before retrying; no approval was granted."
                        ),
                        error_code="CANCELLED"
                        if cancelled
                        else "OUTPUT_REJECTED"
                        if rejected
                        else "EXECUTION_FAILED",
                        revision=run["revision"] + 1,
                        updated_at=now(),
                    )
                    self.put(db, run)
                    self.audit(
                        db,
                        run,
                        actor,
                        "analysis_stopped",
                        None,
                        dict(status=run["status"], error_code=run["error_code"]),
                    )
        finally:
            if TASKS.get(identifier) is task:
                TASKS.pop(identifier, None)

    def current(self, db, project, actor, identifier, revision):
        run = self.get(db, project, actor, identifier)
        state = ProjectLifecycle.state(db, project)
        latest = db.execute(
            "SELECT id FROM ba_review_runs WHERE project=? ORDER BY rowid DESC LIMIT 1", (project,)
        ).fetchone()
        if state["baseline"] != run["baseline"] or not latest or latest[0] != identifier:
            raise SDLCError("Review was superseded. Reload the current BRD analysis")
        if run["revision"] != revision:
            raise SDLCError("Review changed. Reload before recording your decision")
        if run["status"] != "completed":
            raise SDLCError("Wait for completed BA analysis before reviewing findings")
        return run

    def decide(self, project, actor, role, identifier, payload: FindingDecision, *, human):
        self.writer(role, human)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = self.current(db, project, actor, identifier, payload.revision)
            finding = next(
                (f for f in run["output"]["findings"] if f["finding_id"] == payload.finding_id),
                None,
            )
            if not finding or finding["version"] != payload.finding_version:
                raise SDLCError("Finding changed or does not belong to this review")
            if payload.action == "edit" and not (payload.proposed_text or "").strip():
                raise SDLCError("Enter revised proposal wording")
            before = json.loads(json.dumps(finding))
            statuses = dict(
                accept="ACCEPTED_DRAFT",
                edit="EDITED_DRAFT",
                reject="REJECTED",
                clarify="CLARIFICATION_REQUESTED",
                resolve="RESOLVED",
            )
            if payload.action != "comment":
                finding["review_status"] = statuses[payload.action]
            if payload.action == "edit":
                finding["human_proposed_text"] = payload.proposed_text
            event = dict(
                id=uuid4().hex,
                actor=actor,
                role=role,
                human=True,
                baseline=run["baseline"],
                finding_id=finding["finding_id"],
                finding_version=finding["version"],
                action=payload.action,
                comment=payload.comment,
                created_at=now(),
                before=before,
                after=json.loads(json.dumps(finding)),
            )
            run["decisions"].append(event)
            run.update(signoff=None, revision=run["revision"] + 1, updated_at=now())
            self.put(db, run)
            self.audit(db, run, actor, "finding_decision", before, event)
            return run

    def revise_brd(self, project, actor, role, identifier, revision, *, human):
        self.writer(role, human)
        with self.store.connect() as db:
            run = self.current(db, project, actor, identifier, revision)
            row = db.execute(
                "SELECT data FROM revisions WHERE project=? AND stage='requirements-input' "
                "AND version=?",
                (project, run["baseline"]),
            ).fetchone()
            source = json.loads(row[0])
        document, provenance = revised_document(source["content"]["document"], run)
        prior = source["content"].get("ba_revision", {}).get("pending_feedback", [])
        provenance["pending_feedback"] = list(
            {item["finding_id"]: item for item in prior + provenance["pending_feedback"]}.values()
        )
        try:
            request = GenerateRequest.model_validate(
                {
                    **source["content"]["source_request"],
                    "description": document,
                    "uploaded_brd_text": None,
                    "uploaded_brd_receipt": None,
                }
            )
        except ValueError as error:
            raise SDLCError(
                "Updated BRD is not a valid requirements document; revise its wording"
            ) from error
        content = dict(
            document=document,
            source_request=request.model_dump(mode="json"),
            ba_revision=provenance,
        )
        return self.store.save(
            project,
            actor,
            "requirements-input",
            content,
            run["baseline"],
            [],
            review_guard=(identifier, revision),
        )

    async def execute_revalidation(self, project, actor, identifier):
        from app.agents.business_analyst import BusinessAnalystAgent
        from app.agents.requirements_validation import RequirementsValidationAgent
        from app.services.requirements_reviews import record_assessment

        def progress(status, text, **extra):
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                current = self.get(db, project, actor, identifier)
                if current["status"] not in ACTIVE:
                    raise SDLCError("Updated BRD revalidation was cancelled or superseded")
                current.update(
                    status=status,
                    progress=text,
                    updated_at=now(),
                    revision=current["revision"] + 1,
                    **extra,
                )
                self.put(db, current)
                return current

        task = asyncio.current_task()
        TASKS[identifier] = task
        try:
            run = progress("running", "Revalidating updated BRD: business scope and requirements")
            request = GenerateRequest.model_validate(run["request"])
            report = await asyncio.wait_for(
                BusinessAnalystAgent(self.settings).review(request), 900
            )
            record_assessment(
                self.store, actor, request, "business_analysis", report.model_dump(mode="json")
            )
            progress("running", "Revalidating updated BRD: approved-source alignment")
            alignment = await asyncio.wait_for(
                RequirementsValidationAgent(self.settings).assess(request), 900
            )
            record_assessment(
                self.store, actor, request, "alignment", alignment.model_dump(mode="json")
            )
            progress(
                "queued",
                "Updated BRD assessments saved; generating fresh BA findings",
                revalidation=dict(
                    status="completed", alignment_status=alignment.status, ba_outcome=report.outcome
                ),
            )
            await self.execute(project, actor, identifier)
        except (Exception, asyncio.CancelledError) as error:
            with self.store.connect() as db:
                current = self.get(db, project, actor, identifier)
                if current["status"] in ACTIVE:
                    current.update(
                        status="cancelled"
                        if isinstance(error, asyncio.CancelledError)
                        else "failed",
                        progress="Updated BRD saved, but revalidation did not finish. "
                        "Retry AI analysis to revalidate this version.",
                        error_code="REVALIDATION_FAILED",
                        updated_at=now(),
                        revision=current["revision"] + 1,
                    )
                    self.put(db, current)
            logger.warning(
                "Revalidation did not finish for revised BRD review %s: %s",
                identifier,
                type(error).__name__,
            )
        finally:
            if TASKS.get(identifier) is task:
                TASKS.pop(identifier, None)

    def signoff(self, project, actor, role, identifier, payload: ReviewSignoff, *, human):
        self.writer(role, human)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = self.current(db, project, actor, identifier, payload.revision)
            output = run["output"]
            if run.get("brd_revision"):
                if run["brd_revision"].get("pending_feedback"):
                    raise SDLCError(
                        "Resolve the open BA change requests in the BRD before sign-off"
                    )
                if run.get("revalidation", {}).get("status") != "completed":
                    raise SDLCError("Revalidate the updated BRD before sign-off")
                if run["revalidation"].get("ba_outcome") == "blocked":
                    raise SDLCError(
                        "Updated BRD business assessment is blocked; correct and revalidate it"
                    )
                if run["revalidation"].get("alignment_status") == "blocked":
                    raise SDLCError(
                        "Updated BRD alignment is blocked; correct and revalidate the BRD"
                    )
            _, knowledge_key, _, _ = InlineBusinessAnalyst(self.settings).review_knowledge(
                GenerateRequest.model_validate(run["request"])
            )
            if knowledge_key != run["knowledge_fingerprint"]:
                raise SDLCError("In-house knowledge changed. Reanalyse before BA sign-off")
            if output["readiness_status"] == "BLOCKED" or any(
                f["severity"] in {"BLOCKER", "HIGH"} and f["review_status"] != "REJECTED"
                for f in output["findings"]
            ):
                raise SDLCError(
                    "Blocking or high-impact issues require corrected BRD evidence "
                    "and reanalysis before sign-off"
                )
            if any(f["review_status"] not in {"REJECTED", "RESOLVED"} for f in output["findings"]):
                raise SDLCError("Review and resolve or reject every finding before BA sign-off")
            if any(
                req["readiness"] != "READY_FOR_BA_REVIEW"
                and not any(
                    req["requirement_id"] in finding["requirement_ids"]
                    for finding in output["findings"]
                )
                for req in output["requirements"]
            ):
                raise SDLCError("Unexplained requirement readiness gaps require reanalysis")
            if any(
                q["blocking_status"]
                and (
                    not q["linked_finding_ids"]
                    or any(
                        f["finding_id"] in q["linked_finding_ids"]
                        and f["review_status"] not in {"REJECTED", "RESOLVED"}
                        for f in output["findings"]
                    )
                )
                for q in output["business_questions"]
            ):
                raise SDLCError("Outstanding stakeholder decisions prevent BA sign-off")
            run["signoff"] = dict(
                actor=actor,
                role=role,
                human=True,
                comment=payload.comment,
                baseline=run["baseline"],
                review_revision=run["revision"],
                created_at=now(),
            )
            run.update(revision=run["revision"] + 1, updated_at=now())
            self.put(db, run)
            self.audit(db, run, actor, "signed_off", None, run["signoff"])
            return run

    def cancel(self, project, actor, role, identifier, *, human):
        self.writer(role, human)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = self.get(db, project, actor, identifier)
            if run["status"] in ACTIVE:
                run.update(
                    status="cancelled",
                    progress="Analysis cancelled; no approval granted",
                    revision=run["revision"] + 1,
                    updated_at=now(),
                )
                self.put(db, run)
                self.audit(db, run, actor, "cancelled", None, dict(status="cancelled"))
        if task := TASKS.get(identifier):
            task.get_loop().call_soon_threadsafe(task.cancel)
        return run
