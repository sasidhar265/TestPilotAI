"""Controlled execution of the repository's approved C# automation project."""

import asyncio
import os
import re
import time
from pathlib import Path

from app.agents import AgentKind, FunctionalAgentDescriptor
from app.config import Settings
from app.models import AutomationRunReport, AutomationRunRequest

_SUMMARY = re.compile(r"Failed:\s*(\d+),\s*Passed:\s*(\d+),\s*Skipped:\s*(\d+)")
_SAFE_ENVIRONMENT = (
    "PATH",
    "DOTNET_ROOT",
    "QUALITY_LIFECYCLE_BASE_URL",
    "API_AUTH_TOKEN",
    "API_BEARER_TOKEN",
    "API_FIXTURE_FILE",
    "APP_USERNAME",
    "APP_PASSWORD",
)


class AutomationExecutionError(RuntimeError):
    """The controlled automation process could not be started or completed."""


class AutomationExecutionAgent:
    descriptor = FunctionalAgentDescriptor(
        id="automation-execution-agent",
        name="Automation Execution Agent",
        kind=AgentKind.EXECUTION,
        purpose="Run the approved C# BDD UI, API, and security suite and return bounded evidence.",
        runtime="local-dotnet-process",
        capabilities=("csharp-bdd-execution", "ui-api-security-evidence", "bounded-process-output"),
        instruction_file=".github/agents/automation-execution.agent.md",
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def run(self, request: AutomationRunRequest) -> AutomationRunReport:
        automation_cases = [
            case
            for case in request.suite.test_cases
            if getattr(case.execution_mode, "value", case.execution_mode) == "automation"
        ]
        if not automation_cases:
            raise AutomationExecutionError(
                "The suite contains no automation cases. Generate BDD automation coverage first."
            )
        root = Path.cwd().resolve()
        project = Path(self.settings.automation_project_path).resolve()
        if root not in project.parents or project.suffix != ".csproj" or not project.is_file():
            raise AutomationExecutionError("The configured automation project is invalid.")
        command = (
            "dotnet",
            "test",
            str(project),
            "--no-restore",
            "--logger",
            "console;verbosity=minimal",
        )
        environment = {key: value for key in _SAFE_ENVIRONMENT if (value := os.environ.get(key))}
        started = time.perf_counter()
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(root),
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            raw_output, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=self.settings.automation_timeout_seconds,
            )
        except TimeoutError as error:
            process.kill()
            await process.communicate()
            raise AutomationExecutionError(
                "C# automation execution exceeded its time limit."
            ) from error
        except OSError as error:
            raise AutomationExecutionError(
                "Unable to start the approved C# automation project."
            ) from error
        output = _redact_output(raw_output.decode("utf-8", errors="replace"))
        match = _SUMMARY.search(output)
        failed, passed, skipped = (map(int, match.groups()) if match else (1, 0, 0))
        return AutomationRunReport(
            status="passed" if process.returncode == 0 and failed == 0 else "failed",
            project=str(project.relative_to(root)),
            suite_case_count=len(automation_cases),
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration_ms=round((time.perf_counter() - started) * 1000),
            output=output,
        )


def _redact_output(value: str) -> str:
    for key in ("API_AUTH_TOKEN", "API_BEARER_TOKEN", "APP_PASSWORD"):
        secret = os.environ.get(key)
        if secret:
            value = value.replace(secret, "[redacted]")
    return value[-12_000:]
