"""Authenticated project and lifecycle artifact operations."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, TypeVar

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.auth import SESSION_COOKIE, session_username
from app.ba_review_models import BRDRevisionRequest, FindingDecision, ReviewSignoff, ReviewStart
from app.config import Settings, get_settings
from app.models import GenerateRequest
from app.role_access import principal_role
from app.sdlc_models import DeliveryMission, DeliveryStart
from app.services.ba_documents import business_documents
from app.services.ba_reviews import BAReviews
from app.services.project_lifecycle import ProjectLifecycle
from app.services.project_work_items import ProjectWorkItems
from app.services.sdlc import SDLCError, SDLCStore, repository_snapshot
from app.services.sdlc_delivery import DeliveryCoordinator, capabilities
from app.services.sdlc_tools import DeliveryTools
from app.stlc_routes import Actor
from app.users import get_user

router = APIRouter(prefix="/api/sdlc", tags=["SDLC"])


def storage(settings: Annotated[Settings, Depends(get_settings)]) -> SDLCStore:
    return SDLCStore(settings.organizational_memory_path)


Store = Annotated[SDLCStore, Depends(storage)]


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=160, pattern=r"\S")


class ArtifactLink(BaseModel):
    stage: str = Field(max_length=30)
    version: int = Field(ge=1)


class ArtifactInput(BaseModel):
    content: dict[str, Any]
    base_version: int = Field(ge=0)
    links: list[ArtifactLink] = Field(default_factory=list, max_length=50)


class ReviewInput(BaseModel):
    version: int = Field(ge=1)
    decision: Literal["approved", "changes_requested"]
    comment: str = Field(min_length=1, max_length=4000, pattern=r"\S")


T = TypeVar("T")


def perform(action: Callable[[], T]) -> T:
    try:
        return action()
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    except SDLCError as error:
        code = (
            404
            if str(error) in {"Project not found", "Delivery run not found", "BA review not found"}
            else 409
        )
        raise HTTPException(code, str(error)) from error


@router.get("/projects")
def projects(store: Store, actor: Actor) -> list[dict[str, Any]]:
    return store.projects(actor)


def ba_identity(request: Request, settings: Settings) -> tuple[str, bool]:
    return principal_role(request, settings) or "", bool(
        session_username(request.cookies.get(SESSION_COOKIE, ""), settings)
    )


@router.get("/projects/{identifier}/ba-reviews")
def ba_reviews(
    identifier: str,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    return perform(lambda: BAReviews(store, settings).snapshot(identifier, actor))


@router.get("/projects/{identifier}/ba-documents")
def download_ba_documents(
    identifier: str,
    store: Store,
    actor: Actor,
    document: Literal["all", "business-review", "metrics", "brd", "history"] = "all",
) -> Response:
    data, filename, media = perform(lambda: business_documents(store, identifier, actor, document))
    return Response(
        data,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/projects/{identifier}/ba-reviews/{review_id}")
def ba_review_detail(
    identifier: str,
    review_id: str,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    return perform(lambda: BAReviews(store, settings).snapshot(identifier, actor, review_id))


@router.post("/projects/{identifier}/ba-reviews", status_code=202)
def start_ba_review(
    identifier: str,
    payload: ReviewStart,
    request: Request,
    background: BackgroundTasks,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    role, human = ba_identity(request, settings)
    service = BAReviews(store, settings)
    run, created = perform(lambda: service.start(identifier, actor, role, payload, human=human))
    if created:
        background.add_task(
            service.execute_revalidation if run.get("brd_revision") else service.execute,
            identifier,
            actor,
            run["id"],
        )
    return dict(run=run, created=created)


@router.post("/projects/{identifier}/ba-reviews/{review_id}/decisions")
def ba_finding_decision(
    identifier: str,
    review_id: str,
    payload: FindingDecision,
    request: Request,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    role, human = ba_identity(request, settings)
    return perform(
        lambda: BAReviews(store, settings).decide(
            identifier, actor, role, review_id, payload, human=human
        )
    )


@router.post("/projects/{identifier}/ba-reviews/{review_id}/revised-brd", status_code=202)
def revise_ba_brd(
    identifier: str,
    review_id: str,
    payload: BRDRevisionRequest,
    request: Request,
    background: BackgroundTasks,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    role, human = ba_identity(request, settings)
    service = BAReviews(store, settings)
    source = perform(
        lambda: service.revise_brd(
            identifier, actor, role, review_id, payload.revision, human=human
        )
    )
    run, created = perform(
        lambda: service.start(
            identifier, actor, role, ReviewStart(baseline=source["version"]), human=human
        )
    )
    if created:
        background.add_task(service.execute_revalidation, identifier, actor, run["id"])
    return dict(source=source, run=run, created=created)


@router.post("/projects/{identifier}/ba-reviews/{review_id}/signoff")
def ba_signoff(
    identifier: str,
    review_id: str,
    payload: ReviewSignoff,
    request: Request,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    role, human = ba_identity(request, settings)
    return perform(
        lambda: BAReviews(store, settings).signoff(
            identifier, actor, role, review_id, payload, human=human
        )
    )


@router.post("/projects/{identifier}/ba-reviews/{review_id}/cancel")
def cancel_ba_review(
    identifier: str,
    review_id: str,
    request: Request,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    role, human = ba_identity(request, settings)
    return perform(
        lambda: BAReviews(store, settings).cancel(identifier, actor, role, review_id, human=human)
    )


@router.post("/projects", status_code=201)
def create(payload: ProjectInput, store: Store, actor: Actor) -> dict[str, Any]:
    return store.create(payload.name.strip(), actor)


@router.get("/projects/{identifier}")
def snapshot(identifier: str, store: Store, actor: Actor) -> dict[str, Any]:
    return perform(lambda: store.snapshot(identifier, actor))


@router.post("/projects/{identifier}/artifacts/{stage}", status_code=201)
def artifact(
    identifier: str, stage: str, payload: ArtifactInput, store: Store, actor: Actor
) -> dict[str, Any]:
    if stage not in {"requirements-input", "workflow"}:
        raise HTTPException(
            409, "Lifecycle outputs are agent-owned. Change Requirements and start a new run."
        )
    if stage == "requirements-input":
        try:
            source = GenerateRequest.model_validate(payload.content.get("source_request", {}))
        except ValueError as error:
            raise HTTPException(422, "A valid Requirements source request is required") from error
        payload.content = {
            "document": source.description,
            "source_request": source.model_dump(mode="json"),
        }
        payload.links = []
    return perform(
        lambda: store.save(
            identifier,
            actor,
            stage,
            payload.content,
            payload.base_version,
            [link.model_dump() for link in payload.links],
        )
    )


@router.post("/projects/{identifier}/artifacts/{stage}/reviews", status_code=201)
def review(
    identifier: str, stage: str, payload: ReviewInput, store: Store, actor: Actor
) -> dict[str, Any]:
    return perform(
        lambda: store.review(
            identifier, actor, stage, payload.version, payload.decision, payload.comment
        )
    )


@router.get("/repository")
def repository() -> dict[str, str]:
    return perform(repository_snapshot)


@router.get("/agents")
def agents(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    return capabilities(settings)


@router.post("/projects/{identifier}/runs", status_code=202)
async def start_delivery(
    identifier: str,
    payload: DeliveryStart,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    def launch() -> dict[str, Any]:
        snapshot = store.snapshot(identifier, actor)
        source = next(
            (item for item in snapshot["artifacts"] if item["stage"] == "requirements-input"), None
        )
        if source is None or source["version"] != payload.requirements_version:
            raise SDLCError("Save Requirements and start from their latest version.")
        request = GenerateRequest.model_validate(source["content"]["source_request"])
        mission = DeliveryMission(
            brief=request.description,
            constraints=request.additional_context,
            source_request=request,
            llm_model=request.llm_model,
            target=payload.target,
            requirements_version=source["version"],
        )
        return DeliveryCoordinator(settings, store).start(identifier, actor, mission)

    return perform(launch)


@router.get("/runs/{identifier}")
def delivery(identifier: str, store: Store, actor: Actor) -> dict[str, Any]:
    store.recover_runs(actor)
    return perform(lambda: store.run(identifier, actor))


@router.post("/runs/{identifier}/cancel")
async def cancel_delivery(
    identifier: str,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    try:
        return await DeliveryCoordinator(settings, store).cancel(identifier, actor)
    except SDLCError as error:
        raise HTTPException(404, str(error)) from error


@router.get("/runs/{identifier}/bundle")
def delivery_bundle(
    identifier: str,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    run = perform(lambda: store.run(identifier, actor))
    tools = DeliveryTools(settings, run["project"], identifier)
    if run["status"] in {"queued", "running", "cancelling"}:
        raise HTTPException(409, "Wait until the delivery worker stops before exporting its files")
    return Response(
        tools.bundle(),
        media_type="application/gzip",
        headers={"Content-Disposition": 'attachment; filename="sdlc-delivery.tar.gz"'},
    )


@router.post("/runs/{identifier}/resume", status_code=202)
async def resume_delivery(
    request: Request,
    identifier: str,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    run = perform(lambda: store.run(identifier, actor))
    if principal_role(request, settings) == "ba" and run["mission"]["target"] != "design":
        raise HTTPException(403, "Business analysts can resume design-only delivery runs")
    return perform(lambda: DeliveryCoordinator(settings, store).resume(identifier, actor))


class TransitionInput(BaseModel):
    revision: int = Field(ge=0)
    decision: Literal["approved", "changes_requested"]
    comment: str = Field(min_length=1, max_length=4000, pattern=r"\S")


class EvidenceInput(BaseModel):
    revision: int = Field(ge=0)
    kind: str = Field(min_length=1, max_length=60)
    reference: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    outcome: Literal["passed", "failed", "blocked"]
    comment: str = Field(min_length=1, max_length=4000, pattern=r"\S")


class MemberInput(BaseModel):
    username: str = Field(min_length=1, max_length=100)


@router.get("/queue")
def queue(
    request: Request,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[dict[str, Any]]:
    role = principal_role(request, settings) or ""
    rows = []
    for project in store.projects(actor):
        records = ProjectWorkItems(store).list(project["id"], actor)
        rows.append(
            dict(
                project=project,
                lifecycle=ProjectLifecycle(store).snapshot(project["id"], actor, role),
                metrics=dict(
                    requirements=sum(item["kind"] == "requirement" for item in records),
                    approved_requirements=sum(item["approved"] for item in records),
                    stories=sum(item["kind"] == "story" for item in records),
                    test_cases=sum(item["kind"] == "test_case" for item in records),
                    open_defects=sum(
                        item["kind"] == "defect" and item["status"] != "done" for item in records
                    ),
                    impacted=sum(item["impacted"] for item in records),
                    documentation=sum(item["kind"] == "documentation" for item in records),
                ),
            )
        )
    return rows


@router.get("/projects/{identifier}/lifecycle")
def lifecycle(
    identifier: str,
    request: Request,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    return perform(
        lambda: ProjectLifecycle(store).snapshot(
            identifier, actor, principal_role(request, settings) or ""
        )
    )


@router.post("/projects/{identifier}/transitions", status_code=201)
def transition(
    identifier: str,
    payload: TransitionInput,
    request: Request,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    return perform(
        lambda: ProjectLifecycle(store).transition(
            identifier,
            actor,
            principal_role(request, settings) or "",
            payload.model_dump(),
            human=bool(session_username(request.cookies.get(SESSION_COOKIE, ""), settings)),
        )
    )


@router.post("/projects/{identifier}/evidence", status_code=201)
def evidence(
    identifier: str,
    payload: EvidenceInput,
    request: Request,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    if not session_username(request.cookies.get(SESSION_COOKIE, ""), settings):
        raise HTTPException(403, "Evidence attestation requires an authenticated human session")
    return perform(
        lambda: ProjectLifecycle(store).evidence(
            identifier, actor, principal_role(request, settings) or "", payload.model_dump()
        )
    )


@router.post("/projects/{identifier}/members", status_code=201)
def add_member(
    identifier: str,
    payload: MemberInput,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    def add() -> dict[str, str]:
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            project = store.project(db, identifier, actor)
            if project["owner"] != actor:
                raise PermissionError("Only the project owner can add team members")
            user = get_user(settings, payload.username)
            if not user or not user["enabled"]:
                raise SDLCError("An enabled account is required")
            db.execute(
                "INSERT OR IGNORE INTO project_members VALUES (?,?)", (identifier, user["username"])
            )
            ProjectLifecycle.event(
                db,
                identifier,
                dict(
                    action="member_added",
                    actor=actor,
                    username=user["username"],
                    created_at=datetime.now(UTC).isoformat(),
                ),
            )
            return dict(username=user["username"])

    return perform(add)


class WorkItemInput(BaseModel):
    id: str | None = Field(default=None, max_length=40)
    base_version: int = Field(ge=0)
    kind: Literal["requirement", "epic", "story", "test_case", "defect", "release", "documentation"]
    title: str = Field(min_length=1, max_length=300, pattern=r"\S")
    description: str = Field(default="", max_length=30000)
    status: Literal["draft", "ready", "active", "blocked", "resolved", "done"] = "draft"
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    estimate: float | None = Field(default=None, ge=0, le=10000)
    assignee: str = Field(default="", max_length=100)
    sprint: str = Field(default="", max_length=100)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=100)
    links: list[str] = Field(default_factory=list, max_length=100)
    references: list[str] = Field(default_factory=list, max_length=100)


@router.get("/projects/{identifier}/work-items")
def work_items(identifier: str, store: Store, actor: Actor) -> list[dict[str, Any]]:
    return perform(lambda: ProjectWorkItems(store).list(identifier, actor))


@router.post("/projects/{identifier}/work-items", status_code=201)
def save_work_item(
    identifier: str,
    payload: WorkItemInput,
    request: Request,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    user = get_user(settings, payload.assignee) if payload.assignee else None
    return perform(
        lambda: ProjectWorkItems(store).save(
            identifier, actor, principal_role(request, settings) or "", payload.model_dump(), user
        )
    )


class SuggestionSource(BaseModel):
    stage: Literal[
        "planning", "requirements", "design", "development", "testing", "release", "operations"
    ]
    version: int = Field(ge=1)
    task: str = Field(min_length=1, max_length=100)


class AnnotationInput(BaseModel):
    base_version: int = Field(ge=1)
    action: Literal["comment", "use_draft", "dismiss"] = "comment"
    comment: str = Field(min_length=1, max_length=4000, pattern=r"\S")
    source: SuggestionSource | None = None


@router.get("/projects/{identifier}/work-items/{item}/detail")
def record_detail(
    identifier: str,
    item: str,
    request: Request,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    from app.services.project_reviews import ProjectReviews

    return perform(
        lambda: ProjectReviews(store).detail(
            identifier, item, actor, principal_role(request, settings) or ""
        )
    )


@router.post("/projects/{identifier}/work-items/{item}/annotations", status_code=201)
def annotate_record(
    identifier: str,
    item: str,
    payload: AnnotationInput,
    request: Request,
    store: Store,
    actor: Actor,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    from app.services.project_reviews import ProjectReviews

    if not session_username(request.cookies.get(SESSION_COOKIE, ""), settings):
        raise HTTPException(403, "Review annotations require an authenticated human session")
    return perform(
        lambda: ProjectReviews(store).annotate(
            identifier, item, actor, principal_role(request, settings) or "", payload.model_dump()
        )
    )
