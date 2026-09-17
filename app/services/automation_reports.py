"""Standalone Allure reports for the fixed repository BDD runner."""

import asyncio
import json
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from app.config import Settings


def report_directory(settings: Settings) -> Path:
    return settings.automation_project_path.resolve().parent / "TestResults" / "Reports"


def report_path(settings: Settings, identifier: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise ValueError("Invalid report identifier")
    current = report_directory(settings) / f"{identifier}.html"
    legacy = (
        settings.organizational_memory_path.resolve().parent
        / "automation-reports"
        / f"{identifier}.html"
    )
    return legacy if not current.exists() and legacy.is_file() else current


def _redact(value: object, secrets: list[str]) -> object:
    if isinstance(value, str):
        for secret in sorted(filter(None, secrets), key=len, reverse=True):
            value = value.replace(secret, "[redacted]")
        return value
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: _redact(item, secrets) for key, item in value.items()}
    return value


def _redact_bytes(value: bytes, secrets: list[str]) -> bytes:
    """Redact known credentials from copied Allure attachment files."""
    for secret in sorted(filter(None, secrets), key=len, reverse=True):
        value = value.replace(secret.encode("utf-8"), b"[redacted]")
    return value


async def generate_report(
    settings: Settings, results: Path, secrets: list[str]
) -> tuple[str | None, str | None]:
    from app.agents.automation_execution_agent import _read_output, _stop_process_tree

    if not any(results.glob("*-result.json")):
        return (
            None,
            "No Allure results produced. Restore the BDD project dependencies.",
        )
    sanitized = results.parent / "allure-sanitized"
    output = results.parent / "allure-html"
    try:
        sanitized.mkdir()
        for source in results.glob("*.json"):
            data = _redact(json.loads(source.read_text(encoding="utf-8")), secrets)
            (sanitized / source.name).write_text(json.dumps(data), encoding="utf-8")
        for source in results.iterdir():
            if source.suffix == ".json" or not source.is_file():
                continue
            (sanitized / source.name).write_bytes(_redact_bytes(source.read_bytes(), secrets))
        process = await asyncio.create_subprocess_exec(
            settings.allure_executable,
            "generate",
            str(sanitized),
            "--single-file",
            "--clean",
            "--output",
            str(output),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=os.name == "posix",
        )
        try:
            await asyncio.wait_for(_read_output(process, secrets), settings.allure_timeout_seconds)
        except (TimeoutError, asyncio.CancelledError):
            await asyncio.shield(_stop_process_tree(process))
            raise
        html = output / "index.html"
        if process.returncode != 0 or not html.is_file():
            return (
                None,
                "Allure HTML generation failed. Check the Allure CLI and Java.",
            )
        identifier = uuid4().hex
        destination = report_path(settings, identifier)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(html, destination.with_suffix(".tmp"))
        destination.with_suffix(".tmp").replace(destination)
        # Bound stored report history independently from other workspace activity.
        reports = sorted(destination.parent.glob("*.html"), key=lambda path: path.stat().st_mtime)
        for old in reports[:-200]:
            if re.fullmatch(r"[a-f0-9]{32}\.html", old.name):
                old.unlink(missing_ok=True)
        return identifier, None
    except TimeoutError:
        return (
            None,
            "Allure HTML generation timed out. Test results are still available.",
        )
    except (OSError, ValueError):
        return None, "Allure report unavailable. Check the Allure CLI, Java, and report storage."
