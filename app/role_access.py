"""Authorize operations independently of the controls displayed in the browser."""

import hmac
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from app.auth import SESSION_COOKIE, session_username
from app.config import Settings, get_settings
from app.roles import capabilities
from app.users import get_user

GENERATION_PATHS = frozenset(
    {
        "/api/generate",
        "/api/agent/run",
        "/api/generate/document",
        "/api/generate/expand",
        "/api/jira/generate",
        "/api/workflow/test-cases",
        "/api/reviews",
    }
)
AUTOMATION_PREFIXES = (
    "/api/step-definitions/",
    "/api/automation/run",
    "/api/workflow/execute",
    "/api/workflow/execution-plan",
)
BA_WRITES = frozenset(
    {
        "/api/auth/logout",
        "/api/workflow/requirements/document",
        "/api/workflow/ba-review",
        "/api/workflow/validate-requirements",
        "/api/workflow/brd/pdf",
        "/api/workflow/stories",
        "/api/workflow/validate-stories",
        "/api/workflow/jira-stories",
        "/api/business-rules/document",
        "/api/finance/calculations",
        "/api/stlc/requirements",
        "/api/stlc/baselines",
    }
)


def operation_allowed(role: str, path: str, method: str, view: str = "") -> bool:
    access = capabilities(role)
    if path.startswith("/api/sdlc/projects/") and "/ba-reviews" in path:
        return method in {"GET", "HEAD", "OPTIONS"} or role in {"admin", "test_lead", "ba"}
    if path.startswith("/api/sdlc/") and (
        path.endswith(
            (
                "/lifecycle",
                "/transitions",
                "/evidence",
                "/members",
                "/queue",
                "/work-items",
                "/detail",
                "/annotations",
            )
        )
    ):
        return role in {
            "admin",
            "test_lead",
            "ba",
            "functional_tester",
            "automation_tester",
            "non_functional_tester",
            "business_stakeholder",
            "product_owner",
            "developer",
            "release_manager",
        }
    if role in {"business_stakeholder", "product_owner", "developer", "release_manager"}:
        if method in {"GET", "HEAD", "OPTIONS"}:
            return not (path.startswith("/api/admin/") or path == "/admin/users")
        return path == "/api/auth/logout" or (
            path.startswith("/api/sdlc/")
            and (
                path.endswith("/artifacts/workflow")
                or (role == "release_manager" and path.endswith(("/runs", "/cancel", "/resume")))
                or (role == "developer" and path.endswith(("/cancel", "/resume")))
            )
        )
    if role in {"admin", "test_lead"}:
        return not (role != "admin" and (path.startswith("/api/admin/") or path == "/admin/users"))
    if path.startswith("/api/admin/") or path == "/admin/users":
        return False
    if path.startswith("/api/stlc/cycles/") and path.endswith("/pack"):
        return access["automation"]
    if path.startswith(AUTOMATION_PREFIXES):
        return access["automation"]
    if path.startswith("/api/script-packs/"):
        return access["non_functional"]
    if path == "/" and view in {"automation", "execution"}:
        return access["automation"]
    if path == "/" and view in {"scenarios", "test-cases"}:
        return access["test_cases"]
    if path.startswith("/api/sdlc/") and method not in {"GET", "HEAD", "OPTIONS"}:
        permitted_stages = {
            "ba": ("requirements-input", "workflow"),
            "functional_tester": ("testing", "workflow"),
            "automation_tester": ("testing", "workflow"),
            "non_functional_tester": ("testing", "workflow"),
        }.get(role, ())
        return bool(permitted_stages) and (
            path.endswith("/projects")
            or (
                role == "ba"
                and (path.endswith("/runs") or path.endswith("/cancel") or path.endswith("/resume"))
            )
            or any(path.endswith("/artifacts/" + stage) for stage in permitted_stages)
        )
    if role == "ba":
        if path in {"/quality-lifecycle", "/progress"}:
            return False
        if method not in {"GET", "HEAD", "OPTIONS"}:
            return path in BA_WRITES or (
                path.startswith("/api/generation/") and path.endswith("/cancel")
            )
    return role in {"ba", "functional_tester", "automation_tester", "non_functional_tester"}


def payload_allowed(role: str, path: str, payload: dict[str, Any]) -> bool:
    if role in {"admin", "test_lead"}:
        return True
    if path.startswith("/api/sdlc/") and path.endswith("/runs"):
        return role == "release_manager" or (
            role == "ba" and payload.get("target", "design") == "design"
        )
    request = payload.get("request", payload)
    if path in GENERATION_PATHS:
        if not isinstance(request, dict):
            return False
        target = request.get("generation_target", "auto")
        discipline = request.get("manual_testing_type", "api")
        allowed = {
            "functional_tester": target == "manual" and discipline in {"api", "ui"},
            "automation_tester": target == "automation" and discipline in {"api", "ui"},
            "non_functional_tester": target == "manual"
            and discipline in {"performance", "database"},
        }
        if not allowed.get(role, False):
            return False
    # Prevent exporting, reviewing or executing a suite of a different execution mode.
    suite = payload.get("suite")
    if isinstance(suite, dict):
        cases = suite.get("test_cases", [])
        expected = "automation" if role == "automation_tester" else "manual"
        if any(
            not isinstance(case, dict) or case.get("execution_mode") != expected for case in cases
        ):
            return False
    if role != "automation_tester" and path.startswith("/api/context-converter/"):
        return path.endswith("/normal")
    if role == "automation_tester" and path.startswith("/api/context-converter/"):
        return path.endswith("/bdd")
    return True


def principal_role(request: Request, settings: Settings) -> str | None:
    username = session_username(request.cookies.get(SESSION_COOKIE, ""), settings)
    if username:
        user = get_user(settings, username)
        return user["role"] if user else None
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if (
        settings.api_auth_token_value
        and scheme.casefold() == "bearer"
        and hmac.compare_digest(token, settings.api_auth_token_value)
    ):
        return "admin"  # The configured service token remains a privileged integration credential.
    if not settings.browser_login_enabled and not settings.api_auth_token_value:
        return "admin"
    return None


async def enforce_role_access(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> None:
    path = request.url.path
    if path in {
        "/login",
        "/guest",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/profile",
        "/api/health",
        "/api/live",
        "/api/ready",
    }:
        return
    role = principal_role(request, settings)
    if role is None:
        return  # OrganizationHttpMiddleware handles authentication and view-only guests.
    if not operation_allowed(role, path, request.method, request.query_params.get("view", "")):
        raise HTTPException(403, "Your role does not permit this operation")
    if request.method not in {"POST", "PUT", "PATCH"} or role in {"admin", "test_lead"}:
        return
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = await request.json()
        except ValueError:
            return  # Let the endpoint return its normal malformed-JSON validation error.
    elif path in GENERATION_PATHS and "multipart/form-data" in content_type:
        payload = dict(await request.form())
    else:
        payload = {}
    if isinstance(payload, dict) and not payload_allowed(role, path, payload):
        raise HTTPException(
            403, "Your role does not permit the selected testing type or execution mode"
        )
