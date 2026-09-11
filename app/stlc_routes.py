"""Versioned requirement review, execution cycles, and evidence endpoints."""

import re
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.agents.test_case_validator import TestCaseValidatorAgent
from app.auth import SESSION_COOKIE, session_username
from app.config import Settings, get_settings
from app.models import BusinessRule, GenerateRequest, TestSuite
from app.services.stlc import LifecycleError, LifecycleStore
from app.stlc_models import (
    AttemptInput,
    BaselineInput,
    CycleInput,
    DefectInput,
    DefectUpdate,
    ImportInput,
    JiraDefectInput,
    PackInput,
    RequirementInput,
    ReviewInput,
    SuiteVersionInput,
)

router = APIRouter(prefix="/api/stlc", tags=["STLC"])
Config = Annotated[Settings, Depends(get_settings)]


def store(settings: Config) -> LifecycleStore:
    return LifecycleStore(settings.organizational_memory_path)


Store = Annotated[LifecycleStore, Depends(store)]


def actor(request: Request, settings: Config) -> str:
    username = session_username(request.cookies.get(SESSION_COOKIE, ""), settings)
    if username:
        return username
    # Authentication is enforced by OrganizationHttpMiddleware before routing.
    if settings.api_auth_token_value:
        return "api-service"
    if settings.browser_login_enabled:
        raise HTTPException(401, "Sign in before changing lifecycle records")
    return "local-development"


Actor = Annotated[str, Depends(actor)]


@router.get("")
def snapshot(storage: Store) -> dict[str, Any]:
    return storage.snapshot()


@router.post("/requirements", status_code=201)
def requirement(payload: RequirementInput, storage: Store, identity: Actor) -> dict[str, Any]:
    return storage.requirement(payload, identity)


@router.post("/{kind}/{identifier}/review")
def review(
    kind: str, identifier: str, payload: ReviewInput, storage: Store, identity: Actor
) -> dict[str, Any]:
    return storage.review(kind, identifier, payload, identity)


@router.post("/baselines", status_code=201)
def baseline(payload: BaselineInput, storage: Store, identity: Actor) -> dict[str, Any]:
    return storage.baseline(payload, identity)


@router.post("/suites", status_code=201)
def suite(payload: SuiteVersionInput, storage: Store, identity: Actor) -> dict[str, Any]:
    return storage.suite(payload, identity)


@router.post("/cycles", status_code=201)
def cycle(payload: CycleInput, storage: Store, identity: Actor) -> dict[str, Any]:
    return storage.cycle(payload, identity)


@router.get("/cycles/{identifier}/report")
def report(identifier: str, storage: Store) -> dict[str, Any]:
    return storage.report(identifier)


@router.post("/cycles/{identifier}/attempts", status_code=201)
def attempt(
    identifier: str, payload: AttemptInput, storage: Store, identity: Actor
) -> dict[str, Any]:
    return storage.record_attempt(identifier, payload, identity)


@router.post("/cycles/{identifier}/import")
def import_results(
    identifier: str, payload: ImportInput, storage: Store, identity: Actor
) -> list[dict[str, Any]]:
    return storage.import_results(identifier, payload, identity)


@router.post("/cycles/{identifier}/pack")
def pack(identifier: str, payload: PackInput, storage: Store, identity: Actor) -> Response:
    content = storage.pack(identifier, payload, identity)
    return Response(
        content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{identifier}.zip"'},
    )


@router.post("/defects", status_code=201)
def defect(payload: DefectInput, storage: Store, identity: Actor) -> dict[str, Any]:
    return storage.defect(payload, identity)


@router.patch("/defects/{identifier}")
def update_defect(
    identifier: str, payload: DefectUpdate, storage: Store, identity: Actor
) -> dict[str, Any]:
    return storage.update_defect(identifier, payload, identity)


@router.post("/defects/{identifier}/sync-jira")
async def sync_defect(
    identifier: str, storage: Store, identity: Actor, settings: Config
) -> dict[str, Any]:
    with storage.transaction() as db:
        item = storage.get(db, identifier, "defect")
    if not item.get("jira_key"):
        raise LifecycleError("Link a Jira issue before synchronizing")
    if not all((settings.jira_base_url, settings.jira_email, settings.jira_api_token)):
        raise LifecycleError("Configure Jira connection settings first")
    try:
        async with httpx.AsyncClient(
            auth=(settings.jira_email, settings.jira_api_token), timeout=30
        ) as client:
            response = await client.get(
                f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue/{item['jira_key']}",
                params={"fields": "status"},
            )
            response.raise_for_status()
            status = response.json()["fields"]["status"]["name"]
    except (httpx.HTTPError, KeyError, ValueError) as error:
        raise HTTPException(
            502, "Unable to read Jira status; check issue access and connection settings"
        ) from error
    with storage.transaction() as db:
        current = storage.get(db, identifier, "defect")
        if current.get("jira_key") != item["jira_key"]:
            raise LifecycleError("Jira link changed during synchronization; retry")
        current["jira_status"] = status
        storage.put(db, "defect", current)
        storage.event(db, identifier, "jira-status-synced", identity, str(status))
        return current


@router.get("/suites/{identifier}")
def load_suite(identifier: str, storage: Store) -> dict[str, Any]:
    with storage.transaction() as db:
        item = storage.get(db, identifier, "suite")
        baseline = storage.get(db, item["baseline_id"], "baseline")
    source = GenerateRequest(
        description=(
            "Baseline requirements: "
            + "\n".join(r["description"] for r in baseline["requirements"])
        )[:30000],
        output_format=item["suite"]["output_format"],
        business_rules=[
            BusinessRule(id=r["key"], description=r["description"][:2000])
            for r in baseline["requirements"]
            if re.fullmatch(r"BR-[A-Za-z0-9_-]+", r["key"]) and len(r["description"]) >= 3
        ],
    )
    suite = TestSuite.model_validate(item["suite"])
    return {
        "suite": item["suite"],
        "source_request": source.model_dump(mode="json"),
        "validation": TestCaseValidatorAgent().validate(source, suite).model_dump(mode="json"),
    }


@router.post("/defects/{identifier}/publish-jira")
async def publish_defect(
    identifier: str, payload: JiraDefectInput, storage: Store, identity: Actor, settings: Config
) -> dict[str, Any]:
    if not all((settings.jira_base_url, settings.jira_email, settings.jira_api_token)):
        raise LifecycleError("Configure Jira connection settings first")
    with storage.transaction() as db:
        item = storage.get(db, identifier, "defect")
        if item.get("jira_key") or item.get("jira_publish_pending"):
            raise LifecycleError(
                "Defect is linked or publication needs reconciliation; link the existing Jira issue"
            )
        attempt = storage.get(db, item["attempt_id"], "attempt")
        cycle = storage.get(db, item["cycle_id"], "cycle")
        item["jira_publish_pending"] = True
        storage.put(db, "defect", item)
        storage.event(db, identifier, "jira-publication-requested", identity, payload.project_key)
    description = (
        f"Lifecycle defect: {identifier}\nCase: {item['case_id']}\n"
        f"Build: {cycle['build']}\nEnvironment: {cycle['environment']}\n"
        f"Actual result: {attempt['actual']}\nEvidence: " + ", ".join(attempt["evidence"])
    )
    try:
        async with httpx.AsyncClient(
            auth=(settings.jira_email, settings.jira_api_token), timeout=30
        ) as client:
            response = await client.post(
                f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue",
                json={
                    "fields": {
                        "project": {"key": payload.project_key},
                        "issuetype": {"name": "Bug"},
                        "summary": item["title"][:255],
                        "description": {
                            "type": "doc",
                            "version": 1,
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": description}],
                                }
                            ],
                        },
                    }
                },
            )
            response.raise_for_status()
            key = response.json()["key"]
            validated = DefectUpdate(
                status=item["status"], comment="Published to Jira", jira_key=key
            )
    except (httpx.HTTPError, KeyError, ValueError) as error:
        # A timeout can follow successful remote creation. Never retry it automatically.
        raise HTTPException(
            502,
            "Jira publication could not be confirmed. Check Jira for this lifecycle defect ID "
            "and link the issue before retrying.",
        ) from error
    return storage.update_defect(identifier, validated, identity)
