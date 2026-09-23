"""Controlled execution of the repository's approved C# automation project."""

import asyncio
import json
import os
import re
import signal
import tempfile
import time
import xml.etree.ElementTree as ET
from contextlib import suppress
from pathlib import Path

from app.agents import AgentKind, FunctionalAgentDescriptor
from app.auth import SESSION_COOKIE, issue_browser_session
from app.config import Settings
from app.models import AutomationRunReport, AutomationRunRequest
from app.observability import publish_lifecycle_event
from app.services.automation_reports import generate_report
from app.users import authenticate

_OUTPUT_LIMIT = 12_000
_SAFE_ENVIRONMENT = (
    "PATH",
    "DOTNET_ROOT",
    "HOME",
    "DOTNET_CLI_HOME",
    "NUGET_PACKAGES",
    "PLAYWRIGHT_BROWSERS_PATH",
    "QUALITY_LIFECYCLE_BASE_URL",
    "API_BASE_URL",
    "API_REQUEST_METHOD",
    "API_REQUEST_PATH",
    "API_AUTH_TOKEN",
    "API_BEARER_TOKEN",
    "API_FIXTURE_FILE",
    "APP_USERNAME",
    "APP_PASSWORD",
)


class AutomationExecutionError(RuntimeError):
    """The controlled automation process could not be started or completed."""

    def __init__(self, message: str, output: str = "") -> None:
        super().__init__(message)
        self.output = output


class RunnerProgress:
    """Retain a redacted tail while publishing only fixed, payload-free progress labels."""

    def __init__(self, secrets: list[str], timeout: float, skip_build: bool) -> None:
        self.secrets = secrets
        self.timeout = timeout
        self.started = time.monotonic()
        self.last_output = self.started
        self.phase = "Starting prebuilt BDD tests" if skip_build else "Building the BDD project"
        self.tail = bytearray()
        self.limit = _OUTPUT_LIMIT * 4 + max((len(s.encode()) for s in secrets), default=0)

    def feed(self, chunk: bytes) -> None:
        self.tail.extend(chunk)
        del self.tail[: -self.limit]
        self.last_output = time.monotonic()
        previous = self.phase
        if b"Starting test execution" in self.tail:
            self.phase = "Executing BDD scenarios"
        elif b"Test run for " in self.tail:
            self.phase = "Discovering BDD scenarios"
        if previous != self.phase:
            self.publish()

    def text(self) -> str:
        value = self.tail.decode("utf-8", errors="replace")
        for secret in sorted(filter(None, self.secrets), key=len, reverse=True):
            value = value.replace(secret, "[redacted]")
        return value[-_OUTPUT_LIMIT:]

    def publish(self) -> None:
        elapsed = round(time.monotonic() - self.started)
        silent = round(time.monotonic() - self.last_output)
        publish_lifecycle_event(
            "Automation Execution Agent",
            "bdd_progress",
            "running",
            f"{self.phase} · {elapsed}s elapsed · {self.timeout:g}s total limit · "
            f"last runner output {silent}s ago.",
        )

    async def heartbeat(self) -> None:
        self.publish()
        while True:
            await asyncio.sleep(5)
            self.publish()


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
        root = Path.cwd().resolve()
        project = Path(self.settings.automation_project_path).resolve()
        if root not in project.parents or project.suffix != ".csproj" or not project.is_file():
            raise AutomationExecutionError("The configured automation project is invalid.")
        environment = {key: value for key in _SAFE_ENVIRONMENT if (value := os.environ.get(key))}
        environment.update(
            API_AUTH_TOKEN=self.settings.api_auth_token_value,
            APP_USERNAME=self.settings.app_username,
            APP_PASSWORD=self.settings.app_password_value,
            ENVIRONMENT=self.settings.environment,
            # The server resolves secrets once and forwards only approved runner values.
            # Do not reload a different local store in the child process.
            USER_SECRETS_ENABLED="false",
        )
        if not self.settings.api_auth_token_value and self.settings.browser_login_enabled:
            user = authenticate(
                self.settings, self.settings.app_username, self.settings.app_password_value
            )
            if user is None:
                raise AutomationExecutionError(
                    "BDD login failed. Configure valid APP_USERNAME/APP_PASSWORD or API_AUTH_TOKEN."
                )
            environment["API_SESSION_COOKIE"] = f"{SESSION_COOKIE}=" + issue_browser_session(
                str(user["username"]), self.settings
            )
        # Existing Render services may not have reapplied the Blueprint environment.
        # Derive the local app port rather than silently testing localhost:8000 there.
        environment.setdefault(
            "QUALITY_LIFECYCLE_BASE_URL",
            self.settings.quality_lifecycle_base_url
            or f"http://127.0.0.1:{os.environ.get('PORT', '8000')}",
        )
        target_configuration = {
            "API_BASE_URL": self.settings.api_base_url,
            "API_BEARER_TOKEN": self.settings.api_bearer_token.get_secret_value(),
            "API_FIXTURE_FILE": self.settings.api_fixture_file,
            "API_REQUEST_METHOD": self.settings.api_request_method,
            "API_REQUEST_PATH": self.settings.api_request_path,
        }
        environment.update({key: value for key, value in target_configuration.items() if value})
        secrets = [
            environment.get(key, "")
            for key in ("API_AUTH_TOKEN", "API_BEARER_TOKEN", "APP_PASSWORD", "API_SESSION_COOKIE")
        ]
        build_marker = project.parent / ".automation-build-required"
        build_revision = build_marker.read_text(encoding="utf-8") if build_marker.exists() else None
        skip_build = self.settings.automation_skip_build and build_revision is None
        started = time.perf_counter()
        timeout = min(
            request.timeout_seconds or self.settings.automation_timeout_seconds,
            self.settings.automation_timeout_seconds,
        )
        # Each run owns its result directory, preventing stale or concurrent result reuse.
        with tempfile.TemporaryDirectory(prefix="automation-results-") as results:
            allure_results = Path(results) / "allure-results"
            allure_config = Path(results) / "allureConfig.json"
            allure_config.write_text(
                json.dumps({"allure": {"directory": str(allure_results)}}), encoding="utf-8"
            )
            environment["ALLURE_CONFIG"] = str(allure_config)
            command = (
                "dotnet",
                "test",
                str(project),
                *(("--no-build", "--no-restore") if skip_build else ()),
                "--blame-hang-timeout",
                f"{min(self.settings.automation_test_timeout_seconds, timeout):g}s",
                "--blame-hang-dump-type",
                "none",
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
            progress = RunnerProgress(secrets, timeout, skip_build)
            heartbeat = asyncio.create_task(progress.heartbeat())
            try:
                output = await asyncio.wait_for(
                    _read_output(process, secrets, progress), timeout=timeout
                )
            except (TimeoutError, asyncio.CancelledError) as error:
                await asyncio.shield(_stop_process_tree(process))
                if isinstance(error, asyncio.CancelledError):
                    raise
                raise AutomationExecutionError(
                    f"C# automation execution exceeded its {timeout:g}s time limit during "
                    f"{progress.phase.lower()}. The runner was stopped. Inspect the saved output.",
                    output=progress.text(),
                ) from error
            finally:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat
            passed, failed, skipped, result_error = _read_results(Path(results) / "results.trx")
            # A TRX proves the build reached test execution, even when assertions failed.
            # Retain the marker on build/startup failures or a newer installation.
            if result_error is None and build_revision is not None:
                if (
                    build_marker.exists()
                    and build_marker.read_text(encoding="utf-8") == build_revision
                ):
                    build_marker.unlink()
            remaining = timeout - (time.perf_counter() - started)
            report_id: str | None = None
            report_error: str | None = "Run time limit reached; Allure report was not generated."
            if remaining > 0:
                publish_lifecycle_event(
                    "Automation Execution Agent",
                    "bdd_report",
                    "running",
                    f"BDD execution finished. Preparing Allure HTML "
                    f"(up to {min(remaining, self.settings.allure_timeout_seconds):.0f}s).",
                )
                report_settings = self.settings.model_copy(
                    update={
                        "allure_timeout_seconds": min(
                            remaining, self.settings.allure_timeout_seconds
                        )
                    }
                )
                report_id, report_error = await generate_report(
                    report_settings, allure_results, secrets
                )
            return AutomationRunReport(
                status=(
                    "error"
                    if result_error or (process.returncode != 0 and failed == 0)
                    else "failed"
                    if failed
                    else "passed"
                ),
                project=str(project.relative_to(root)),
                suite_case_count=passed + failed + skipped,
                passed=passed,
                failed=failed,
                skipped=skipped,
                not_run=skipped,
                results_available=result_error is None,
                report_id=report_id,
                report_error=report_error,
                duration_ms=round((time.perf_counter() - started) * 1000),
                output=output,
                test_results=_test_results(Path(results) / "results.trx", secrets),
                error=result_error
                or (
                    "The automation runner exited unsuccessfully."
                    if process.returncode != 0 and failed == 0
                    else None
                ),
            )


async def _read_output(
    process: asyncio.subprocess.Process, secrets: list[str], progress: RunnerProgress | None = None
) -> str:
    assert process.stdout is not None
    # Retain extra bytes so truncation cannot expose part of a secret at the boundary.
    limit = _OUTPUT_LIMIT * 4 + max((len(s.encode()) for s in secrets), default=0)
    tail = bytearray()
    while chunk := await process.stdout.read(4096):
        if progress is not None:
            progress.feed(chunk)
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


def _test_results(path: Path, secrets: list[str] | None = None) -> list[dict[str, str]]:
    """Expose runner-reported case names, including each Scenario Outline example."""
    try:
        if path.stat().st_size > 10 * 1024 * 1024:
            return []
        root = ET.parse(path).getroot()
        catalog_path = Path(__file__).resolve().parents[2] / "automation/Input/CaseTitles.Json"
        try:
            titles = json.loads(catalog_path.read_text())
        except (OSError, ValueError):
            titles = {}

        def safe_name(value: str) -> str:
            for secret in sorted(filter(None, secrets or []), key=len, reverse=True):
                value = value.replace(secret, "[redacted]")
            return value[:1000]

        results = []
        for item in root.findall(".//{*}UnitTestResult"):
            name = item.attrib.get("testName", "Unnamed case")
            case_id = re.search(r"\bTC[-_]([A-Z]+)[-_](\d{3})(?=_|\b)", name)
            if case_id:
                identifier = f"TC-{case_id[1]}-{case_id[2]}"
                if identifier in titles:
                    name = f"{identifier} - {titles[identifier]}"
            result = {
                "name": safe_name(name),
                "status": item.attrib.get("outcome", "Unknown"),
                "duration": item.attrib.get("duration", ""),
            }
            failure = item.find(".//{*}ErrorInfo/{*}Message")
            if failure is not None and failure.text:
                result["error"] = safe_name(failure.text)[:3000]
            results.append(result)
        return results
    except (OSError, ET.ParseError):
        return []
