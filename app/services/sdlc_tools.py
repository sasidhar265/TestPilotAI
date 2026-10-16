"""Bounded repository, build and deployment tools. Models never choose shell commands."""

import asyncio
import hashlib
import io
import json
import os
import re
import tarfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

import httpx

from app.config import Settings
from app.sdlc_models import SourceFile
from app.services.sdlc import SDLCError
from app.subprocess_cleanup import stop_process_tree

FORBIDDEN = {".git", ".env", ".aws", ".codex", ".agent-memory", "node_modules", "__pycache__"}


def safe_path(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if (
        relative.is_absolute()
        or not relative.parts
        or ".." in relative.parts
        or "\\" in name
        or any(
            part.casefold() in FORBIDDEN or part.casefold().startswith(".env.")
            for part in relative.parts
        )
    ):
        raise SDLCError("Generated file path is outside the permitted source tree")
    path = root.joinpath(*relative.parts)
    if root.resolve() not in path.resolve().parents:
        raise SDLCError("Generated file follows a path outside the workspace")
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != root):
        raise SDLCError("Generated files cannot follow symbolic links")
    return path


class DeliveryTools:
    def __init__(self, settings: Settings, project: str, run: str):
        self.settings = settings
        self.project_id, self.run_id = project, run
        self.root = (
            settings.organizational_memory_path.resolve().parent / "sdlc-workspaces" / project / run
        )
        self.checkout = self.root / "source"
        self.pack = self.root / "automation"
        self.cancel_requested: Callable[[], bool] = lambda: False
        self.on_action: Callable[[str], None] = lambda _: None

    def redact(self, value: str) -> str:
        for secret in (
            self.settings.api_auth_token_value,
            self.settings.app_password_value,
            self.settings.api_bearer_token.get_secret_value(),
            self.settings.openai_api_key_value,
            self.settings.copilot_github_token,
        ):
            if secret:
                value = value.replace(secret, "[redacted]")
        for key, secret in os.environ.items():
            if re.search(r"(TOKEN|PASSWORD|SECRET|API_KEY)", key, re.I) and len(secret) >= 6:
                value = value.replace(secret, "[redacted]")
        return value[-12000:]

    async def command(
        self,
        args: list[str],
        cwd: Path,
        *,
        deployment: bool = False,
        extra_env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not args:
            raise SDLCError("Configure the server-owned command for this delivery step")
        environment = {
            key: value
            for key, value in os.environ.items()
            if key
            in {
                "PATH",
                "HOME",
                "TMPDIR",
                "DOTNET_ROOT",
                "NUGET_PACKAGES",
                "LANG",
                "SYSTEMROOT",
                "USERPROFILE",
            }
        }
        if deployment:
            environment.update(os.environ)
        environment.update(extra_env or {})
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                cwd=cwd,
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as error:
            raise SDLCError("Configured delivery command could not start: " + args[0]) from error
        output = bytearray()

        async def drain() -> None:
            assert process.stdout is not None
            while chunk := await process.stdout.read(8192):
                output.extend(chunk)
                del output[:-24000]
            await process.wait()

        try:
            await asyncio.wait_for(drain(), self.settings.sdlc_command_timeout_seconds)
        except TimeoutError as error:
            await stop_process_tree(process)
            raise SDLCError("Configured delivery command timed out") from error
        except BaseException:
            await stop_process_tree(process)
            raise
        return dict(
            exit_code=process.returncode, output=self.redact(output.decode(errors="replace"))
        )

    async def prepare(self) -> dict[str, str]:
        repository = self.settings.sdlc_repository_path
        if repository is None and not self.settings.sdlc_greenfield_enabled:
            raise SDLCError(
                "Configure SDLC_REPOSITORY_PATH before the Development Agent can write code"
            )
        self.root.mkdir(parents=True, exist_ok=True)
        if self.checkout.exists():
            self.checkout.rename(self.root / ("source-previous-" + uuid4().hex[:8]))
        if repository is None:
            self.checkout.mkdir()
            await self.command(["git", "init", "-q"], self.checkout)
            return dict(base_commit="greenfield", repository="new project scaffold")
        repository = repository.resolve()
        revision = await self.command(["git", "rev-parse", "HEAD"], repository)
        if revision["exit_code"]:
            raise SDLCError("Configured repository has no readable HEAD commit")
        archive = self.root / "baseline.tar"
        result = await self.command(
            ["git", "archive", "--format=tar", "-o", str(archive), "HEAD"], repository
        )
        if result["exit_code"] or archive.stat().st_size > 100_000_000:
            raise SDLCError("Repository export failed or exceeded 100 MB")
        self.checkout.mkdir()
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                if not member.isfile():
                    continue
                if any(
                    part.casefold() in FORBIDDEN or part.casefold().startswith(".env.")
                    for part in PurePosixPath(member.name).parts
                ):
                    continue
                path = safe_path(self.checkout, member.name)
                stream = source.extractfile(member)
                if stream:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(stream.read())
                    path.chmod(member.mode & 0o755)
        archive.unlink()
        await self.command(["git", "init", "-q"], self.checkout)
        await self.command(["git", "add", "--all"], self.checkout)
        return dict(base_commit=revision["output"].strip(), repository=str(repository))

    async def context(self) -> dict[str, str]:
        files: dict[str, str] = {}
        used = 0
        for path in sorted(self.checkout.rglob("*")):
            name = path.relative_to(self.checkout).as_posix()
            if not path.is_file() or any(part.casefold() in FORBIDDEN for part in Path(name).parts):
                continue
            path = safe_path(self.checkout, name)
            if path.suffix.lower() not in {
                ".py",
                ".cs",
                ".js",
                ".ts",
                ".tsx",
                ".json",
                ".toml",
                ".md",
                ".html",
                ".css",
                ".yml",
                ".yaml",
                ".csproj",
            }:
                continue
            if path.stat().st_size > 25000:
                continue
            try:
                content = path.read_text()
            except (UnicodeError, OSError):
                continue
            if used + len(content) > 180000:
                break
            files[name] = content
            used += len(content)
        return files

    def write_files(
        self, files: list[SourceFile], root: Path | None = None
    ) -> list[dict[str, str]]:
        destination = root or self.checkout
        names = [file.path for file in files]
        if len(names) != len(set(names)):
            raise SDLCError("Generated file paths must be unique")
        if sum(len(file.content.encode()) for file in files) > 5_000_000:
            raise SDLCError("Generated files exceed the 5 MB stage limit")
        paths = [safe_path(destination, name) for name in names]
        manifest = []
        for file, path in zip(files, paths, strict=True):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(file.content)
            manifest.append(
                dict(path=file.path, sha256=hashlib.sha256(file.content.encode()).hexdigest())
            )
        return manifest

    async def reset_files(self, names: list[str]) -> None:
        # Only files written by this worker are removed; the trusted baseline index restores them.
        for name in names:
            path = safe_path(self.checkout, name)
            if path.is_file():
                path.unlink()
        result = await self.command(["git", "checkout-index", "--all", "--force"], self.checkout)
        if result["exit_code"]:
            raise SDLCError("Could not restore the isolated baseline before repair")

    async def revision(self) -> str:
        await self.command(["git", "add", "--all"], self.checkout)
        result = await self.command(["git", "write-tree"], self.checkout)
        if result["exit_code"]:
            raise SDLCError("Candidate source revision could not be recorded")
        return str(result["output"]).strip()

    async def deploy(self, environment: str, revision: str) -> dict[str, Any]:
        if environment != "rollback" and self.cancel_requested():
            raise asyncio.CancelledError()
        commands = {
            "preview": self.settings.sdlc_preview_command,
            "staging": self.settings.sdlc_staging_command,
            "production": self.settings.sdlc_production_command,
            "rollback": self.settings.sdlc_rollback_command,
        }
        if environment == "production" and not self.settings.sdlc_production_enabled:
            raise SDLCError("Production deployment is disabled by the server delivery policy")
        receipt_path = self.root / "receipts" / f"{environment}.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        if receipt_path.exists():
            if receipt_path.is_symlink():
                raise SDLCError("Deployment receipts cannot follow symbolic links")
            receipt = json.loads(receipt_path.read_text())
            if (
                receipt.get("revision") != revision
                or receipt.get("environment") != environment
                or not receipt.get("deployment_id")
            ):
                raise SDLCError("Existing deployment receipt does not match this candidate")
            return dict(
                receipt=receipt,
                command={
                    "exit_code": 0,
                    "output": "Recorded receipt reused; deployment was not replayed",
                },
            )
        if environment in {"staging", "production"}:
            from app.services.project_lifecycle import ProjectLifecycle
            from app.services.sdlc import SDLCStore

            store = SDLCStore(self.settings.organizational_memory_path)
            with store.connect() as db:
                row = db.execute(
                    "SELECT owner FROM runs WHERE id=? AND project=?",
                    (self.run_id, self.project_id),
                ).fetchone()
            if row is None:
                raise SDLCError("A governed delivery run is required for deployment")
            ProjectLifecycle(store).require_deployment(
                self.project_id, row[0], environment, revision
            )
        self.on_action("deploy:" + environment)
        result = await self.command(
            commands[environment],
            self.checkout,
            deployment=True,
            extra_env={
                "SDLC_WORKSPACE": str(self.checkout),
                "SDLC_DEPLOYMENT_KEY": self.root.name + ":" + environment,
                "SDLC_REVISION": revision,
                "SDLC_ENVIRONMENT": environment,
                "SDLC_RECEIPT_PATH": str(receipt_path),
            },
        )
        self.on_action("idle")
        if result["exit_code"]:
            raise SDLCError(
                f"{environment.capitalize()} deployment command failed: " + result["output"]
            )
        if not receipt_path.is_file() or receipt_path.is_symlink():
            raise SDLCError("Deployment command did not produce its required receipt")
        receipt = json.loads(receipt_path.read_text())
        if (
            receipt.get("revision") != revision
            or receipt.get("environment") != environment
            or not receipt.get("deployment_id")
        ):
            raise SDLCError(
                "Deployment receipt does not identify the requested environment and revision"
            )
        receipt = {
            key: self.redact(str(receipt[key]))[:200]
            for key in ("revision", "environment", "deployment_id", "previous_revision")
            if key in receipt
        }
        return dict(receipt=receipt, command=result)

    async def health(self, url: str, revision: str) -> dict[str, Any]:
        if not url.startswith(("https://", "http://")):
            raise SDLCError("Configure a health URL for the deployed environment")
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            for attempt in range(5):
                try:
                    response = await client.get(url)
                    deployed = response.headers.get("x-sdlc-revision")
                    if not deployed:
                        try:
                            deployed = response.json().get("revision")
                        except (ValueError, AttributeError):
                            deployed = None
                    if response.is_success and deployed == revision:
                        return dict(
                            status="healthy", revision=revision, status_code=response.status_code
                        )
                except httpx.HTTPError:
                    pass
                if attempt < 4:
                    await asyncio.sleep(2)
        raise SDLCError("Health verification did not confirm the deployed candidate revision")

    def bundle(self) -> bytes:
        paths: list[Path] = []
        total = 0
        excluded = FORBIDDEN | {"bin", "obj", ".venv", ".pytest_cache", "testresults"}
        for directory in (self.checkout, self.pack):
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*")):
                relative = path.relative_to(self.root)
                if (
                    not path.is_file()
                    or path.is_symlink()
                    or any(
                        part.casefold() in excluded or part.casefold().startswith(".env.")
                        for part in relative.parts
                    )
                ):
                    continue
                total += path.stat().st_size
                if total > 100_000_000:
                    raise SDLCError("Delivery source bundle exceeds the 100 MB export limit")
                paths.append(path)
        with io.BytesIO() as buffer:
            with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
                for path in paths:
                    archive.add(path, arcname=str(path.relative_to(self.root)), recursive=False)
            return buffer.getvalue()


def bdd_coverage(feature: str, executed_names: list[str]) -> list[str]:
    """Verify every feature scenario and outline row appears in actual runner discovery."""
    expected: dict[str, int] = {}
    current = ""
    examples = False
    header = False
    for raw in feature.splitlines():
        line = raw.strip()
        if line.startswith(("Scenario:", "Scenario Outline:")):
            outline = line.startswith("Scenario Outline:")
            current = line.split(":", 1)[1].strip()
            expected[current] = 0 if outline else 1
            examples = False
        elif line.startswith("Examples:"):
            examples, header = True, True
        elif examples and line.startswith("|"):
            if header:
                header = False
            else:
                expected[current] += 1

    def normalize(value: str) -> str:
        return "".join(character.casefold() for character in value if character.isalnum())

    names = [normalize(name.split("(", 1)[0]) for name in executed_names]
    return [
        f"{scenario}: expected {count} examples, found {names.count(normalize(scenario))}"
        for scenario, count in expected.items()
        if count < 1 or names.count(normalize(scenario)) < count
    ]
