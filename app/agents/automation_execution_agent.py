"""Controlled execution of the repository's approved C# automation project."""

import asyncio
import os
import signal
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from app.agents import AgentKind, FunctionalAgentDescriptor
from app.config import Settings
from app.models import AutomationRunReport, AutomationRunRequest

_OUTPUT_LIMIT = 12_000
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
        environment = {key: value for key in _SAFE_ENVIRONMENT if (value := os.environ.get(key))}
        environment.update(
            API_AUTH_TOKEN=self.settings.api_auth_token_value,
            APP_USERNAME=self.settings.app_username,
            APP_PASSWORD=self.settings.app_password_value,
        )
        secrets = [
            environment.get(key, "")
            for key in ("API_AUTH_TOKEN", "API_BEARER_TOKEN", "APP_PASSWORD")
        ]
        started = time.perf_counter()
        timeout = min(
            request.timeout_seconds or self.settings.automation_timeout_seconds,
            self.settings.automation_timeout_seconds,
        )
        # Each run owns its result directory, preventing stale or concurrent result reuse.
        with tempfile.TemporaryDirectory(prefix="automation-results-") as results:
            command = (
                "dotnet",
                "test",
                str(project),
                "--no-restore",
                "--logger",
                "trx;LogFileName=results.trx",
                "--results-directory",
                results,
            )
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=str(root),
                    env=environment,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    start_new_session=os.name == "posix",
                )
            except OSError as error:
                raise AutomationExecutionError(
                    "Unable to start the approved C# automation project."
                ) from error
            try:
                output = await asyncio.wait_for(_read_output(process, secrets), timeout=timeout)
            except (TimeoutError, asyncio.CancelledError) as error:
                await asyncio.shield(_stop_process_tree(process))
                if isinstance(error, asyncio.CancelledError):
                    raise
                raise AutomationExecutionError(
                    "C# automation execution exceeded its time limit."
                ) from error
            passed, failed, skipped, result_error = _read_results(Path(results) / "results.trx")
            return AutomationRunReport(
                status=(
                    "error"
                    if result_error or (process.returncode != 0 and failed == 0)
                    else "failed"
                    if failed
                    else "passed"
                ),
                project=str(project.relative_to(root)),
                suite_case_count=len(automation_cases),
                passed=passed,
                failed=failed,
                skipped=skipped,
                duration_ms=round((time.perf_counter() - started) * 1000),
                output=output,
                error=result_error
                or (
                    "The automation runner exited unsuccessfully."
                    if process.returncode != 0 and failed == 0
                    else None
                ),
            )


async def _read_output(process: asyncio.subprocess.Process, secrets: list[str]) -> str:
    assert process.stdout is not None
    # Retain extra bytes so truncation cannot expose part of a secret at the boundary.
    limit = _OUTPUT_LIMIT * 4 + max((len(s.encode()) for s in secrets), default=0)
    tail = bytearray()
    while chunk := await process.stdout.read(4096):
        tail.extend(chunk)
        if len(tail) > limit:
            del tail[:-limit]
    await process.wait()
    value = tail.decode("utf-8", errors="replace")
    for secret in sorted(filter(None, secrets), key=len, reverse=True):
        value = value.replace(secret, "[redacted]")
    return value[-_OUTPUT_LIMIT:]


async def _stop_process_tree(process: asyncio.subprocess.Process) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif process.returncode is None:
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
    except ProcessLookupError:
        pass
    if process.stdout is not None:
        while await process.stdout.read(4096):
            pass
    await process.wait()


def _read_results(path: Path) -> tuple[int, int, int, str | None]:
    try:
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("Result file exceeds limit")
        root = ET.parse(path).getroot()
        outcomes = [item.attrib.get("outcome", "") for item in root.findall(".//{*}UnitTestResult")]
        if not outcomes or any(o not in {"Passed", "Failed", "NotExecuted"} for o in outcomes):
            raise ValueError("Missing or unsupported test outcomes")
        return (
            outcomes.count("Passed"),
            outcomes.count("Failed"),
            outcomes.count("NotExecuted"),
            None,
        )
    except (OSError, ET.ParseError, ValueError):
        return 0, 0, 0, "No usable structured test results were produced; inspect runner output."
