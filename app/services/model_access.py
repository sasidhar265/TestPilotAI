"""Read-only permission checks for Copilot, OpenAI API, and Codex CLI."""

import asyncio
import re
import shutil
from typing import Any

import httpx

from app.config import Settings


async def inspect_model_access(settings: Settings, requested_model: str) -> dict[str, Any]:
    """Return access details without consuming a generation request."""
    if requested_model == "auto-fallback":
        providers = await asyncio.gather(
            *(
                inspect_model_access(settings, model)
                for model in ("organization-default", "openai", "codex")
            )
        )
        can_use = any(provider["can_use"] for provider in providers)
        result = _access_result(
            requested_model,
            "Automatic fallback",
            can_use,
            "Copilot → OpenAI API → Codex CLI",
            "At least one provider is ready; unavailable providers will be skipped."
            if can_use
            else "No fallback provider is currently available.",
        )
        result["providers"] = providers
        return result
    name = {"openai": "OpenAI API", "codex": "Codex CLI"}.get(requested_model, "GitHub Copilot")
    try:
        if requested_model == "openai":
            check = _inspect_openai(settings)
        elif requested_model == "codex":
            check = _inspect_codex(settings)
        else:
            check = _inspect_copilot(settings, requested_model)
        return await asyncio.wait_for(check, timeout=30)
    except Exception as error:
        return _access_result(
            requested_model,
            name,
            False,
            "check-failed",
            f"{name} access check failed: {failure_reason(settings, error)}",
        )


def failure_reason(settings: Settings, error: Exception) -> str:
    """Preserve provider diagnostics without returning credentials to the browser."""
    detail = str(error).strip() or type(error).__name__
    if isinstance(error, TimeoutError):
        detail = "Access check timed out."
    for secret in (
        settings.copilot_github_token,
        settings.openai_api_key_value,
        settings.api_auth_token.get_secret_value(),
        settings.app_password.get_secret_value(),
        settings.session_secret.get_secret_value(),
        settings.jira_api_token,
    ):
        if secret:
            detail = detail.replace(secret, "[redacted]")
    detail = re.sub(r"(?i)Bearer\s+[^\s\"']+", "Bearer [redacted]", detail)
    detail = re.sub(r"(?:gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]+", "[redacted]", detail)
    return detail[:1500]


async def _inspect_openai(settings: Settings) -> dict[str, Any]:
    model = settings.openai_model
    if not settings.openai_api_key_value:
        return _access_result(
            "openai",
            f"OpenAI API · {model}",
            False,
            "not-configured",
            "OPENAI_API_KEY is not configured. ChatGPT billing does not include API usage.",
        )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{settings.openai_base_url.rstrip('/')}/models/{model}",
                headers={"Authorization": f"Bearer {settings.openai_api_key_value}"},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        try:
            payload = error.response.json()
            provider_error = payload.get("error", {})
            message = provider_error.get("message", "") if isinstance(provider_error, dict) else ""
        except (ValueError, AttributeError):
            message = ""
        detail = failure_reason(settings, RuntimeError(message or error.response.reason_phrase))
        reason = f"Model access failed (HTTP {status}): {detail}"
        return _access_result("openai", f"OpenAI API · {model}", False, "denied", reason)
    return _access_result(
        "openai",
        f"OpenAI API · {model}",
        True,
        "enabled",
        "The API key can access this model. Remaining spend is managed in the API dashboard.",
    )


async def _inspect_codex(settings: Settings) -> dict[str, Any]:
    executable = shutil.which(settings.codex_executable)
    model = settings.codex_model or "account default"
    if executable is None:
        return _access_result(
            "codex", "Codex CLI", False, "not-installed", "Codex CLI is not on the server PATH."
        )
    try:
        process = await asyncio.create_subprocess_exec(
            executable,
            "login",
            "status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
    except TimeoutError:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    detail = (stdout + stderr).decode("utf-8", errors="replace").strip()
    signed_in = process.returncode == 0 and "logged in" in detail.casefold()
    reason = (
        "Codex CLI is signed in. Exact remaining ChatGPT/Codex usage is not exposed by the CLI."
        if signed_in
        else (
            f"Codex login status failed (exit {process.returncode}): "
            + failure_reason(settings, RuntimeError(detail or "No diagnostic output."))
        )
    )
    return _access_result(
        "codex",
        f"Codex CLI · {model}",
        signed_in,
        "signed-in" if signed_in else "signed-out",
        reason,
    )


async def _inspect_copilot(settings: Settings, requested_model: str) -> dict[str, Any]:
    from copilot import CopilotClient
    from copilot.generated.rpc import AccountGetQuotaRequest

    client_options: dict[str, Any] = {
        "working_directory": str(settings.copilot_working_directory),
        "use_logged_in_user": not bool(settings.copilot_github_token),
        "mode": "copilot-cli",
    }
    if settings.copilot_github_token:
        client_options["github_token"] = settings.copilot_github_token

    async with CopilotClient(**client_options) as client:
        models = await client.list_models()
        quota_result = await client.rpc.account.get_quota(
            AccountGetQuotaRequest(git_hub_token=settings.copilot_github_token or None)
        )

    selectable = [
        model
        for model in models
        if model.policy is None or model.policy.state.casefold() != "disabled"
    ]
    automatic = requested_model in {"auto", "organization-default"}
    selected = (
        None
        if automatic
        else next((model for model in models if model.id == requested_model), None)
    )
    available = bool(selectable) if automatic else selected in selectable
    policy = "available" if automatic and available else "unavailable"
    if selected is not None and selected.policy is not None:
        policy = selected.policy.state
    elif selected is not None:
        policy = "enabled"

    snapshots = quota_result.quota_snapshots
    quota = snapshots.get("premium_interactions") or snapshots.get("chat")
    quota_details: dict[str, Any] | None = None
    quota_allows_use = True
    if quota is not None:
        quota_allows_use = bool(
            quota.is_unlimited_entitlement
            or quota.remaining_percentage > 0
            or quota.usage_allowed_with_exhausted_quota
            or quota.overage_allowed_with_exhausted_quota
        )
        quota_details = {
            "entitlement_requests": quota.entitlement_requests,
            "used_requests": quota.used_requests,
            "remaining_percentage": quota.remaining_percentage,
            "reset_date": quota.reset_date,
            "is_unlimited": quota.is_unlimited_entitlement,
            "usage_allowed_when_exhausted": quota.usage_allowed_with_exhausted_quota,
            "overage_allowed": quota.overage_allowed_with_exhausted_quota,
        }

    multiplier = None
    display_name = "GitHub Copilot · Organization default"
    if requested_model == "auto":
        display_name = "GitHub Copilot · Auto"
    if selected is not None:
        display_name = f"GitHub Copilot · {selected.name}"
        if selected.billing is not None:
            multiplier = selected.billing.multiplier

    can_use = available and quota_allows_use
    if not available:
        reason = "This Copilot model is unavailable or disabled by organization policy."
    elif not quota_allows_use:
        reason = (
            "Copilot quota does not permit usage: "
            f"{quota_details['used_requests']} of {quota_details['entitlement_requests']} "
            f"requests used, {quota_details['remaining_percentage']}% remaining; "
            "usage after exhaustion and overage are both disabled."
            if quota_details is not None
            else "Copilot quota does not permit usage."
        )
    else:
        reason = "The Copilot model is available and the current quota permits usage."

    result = _access_result(requested_model, display_name, can_use, policy, reason)
    result.update(
        {"available": available, "billing_multiplier": multiplier, "quota": quota_details}
    )
    return result


def _access_result(
    model: str, display_name: str, can_use: bool, policy: str, reason: str
) -> dict[str, Any]:
    return {
        "model": model,
        "display_name": display_name,
        "available": can_use,
        "policy": policy,
        "billing_multiplier": None,
        "quota": None,
        "can_use": can_use,
        "reason": reason,
    }
