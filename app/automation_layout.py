"""Canonical, language-independent automation framework layout."""

import re
from collections.abc import Iterable, Sequence
from pathlib import PurePosixPath
from typing import Protocol

from app.agent_instructions import load_agent_section

FOLDERS = (
    "Reqnroll",
    "Features",
    "StepDefinitions",
    "Hooks",
    "TestContext",
    "Services",
    "Builders",
    "Models",
    "Utilities",
    "TestResults/Reports",
    "Input",
)


def layout_instructions() -> str:
    return load_agent_section("automation-test-generator", "Framework layout")


class SourceFile(Protocol):
    @property
    def path(self) -> str: ...


def validate_layout(files: Sequence[SourceFile]) -> None:
    validate_layout_paths(file.path for file in files)


def validate_layout_paths(paths: Iterable[str]) -> None:
    roots = {folder.split("/")[0] for folder in FOLDERS}
    root_files = {
        "README.md",
        "requirements.txt",
        "pyproject.toml",
        "pom.xml",
        "package.json",
        "package-lock.json",
        "tsconfig.json",
        "Gemfile",
    }
    suffixes = {
        "StepDefinitions": "stepdefinition",
        "Services": "service",
        "Builders": "builder",
        "Models": "model",
        "Utilities": "utility",
    }
    seen: set[str] = set()
    for name in paths:
        path = PurePosixPath(name)
        if (
            not re.fullmatch(r"[A-Za-z0-9_./-]+", name)
            or any(part in {"", ".", ".."} for part in name.split("/"))
            or name.casefold() in seen
        ):
            raise ValueError("Unsafe or duplicate automation framework path")
        seen.add(name.casefold())
        if len(path.parts) == 1:
            if path.name in root_files or path.suffix == ".csproj":
                continue
            raise ValueError(f"Place {name} in its automation framework folder")
        folder = path.parts[0]
        if folder not in roots:
            raise ValueError(f"Unsupported automation framework folder: {folder}")
        if folder == "TestResults" and (len(path.parts) < 3 or path.parts[1] != "Reports"):
            raise ValueError("Execution output belongs in TestResults/Reports/")
        if path.suffix.lower() == ".feature" and folder != "Features":
            raise ValueError("Feature files belong in Features/")
        if path.suffix.lower() in {".cs", ".java", ".py", ".js", ".ts", ".rb"}:
            stem = path.stem.casefold().replace("_", "")
            if path.name == "__init__.py":
                continue
            expected = suffixes.get(folder)
            if expected and not stem.endswith(expected):
                raise ValueError(f"{name} must use the {folder} filename convention")
            if folder == "Hooks" and stem != "hooks":
                raise ValueError("Lifecycle hooks must be named Hooks")
            if folder == "TestContext" and stem != "testcontext":
                raise ValueError("Shared context must be named testcontext")
            if folder not in {*suffixes, "Hooks", "TestContext", "Reqnroll"}:
                raise ValueError(f"Source code does not belong in {folder}")


def folder_notes() -> dict[str, str]:
    return {
        f"{folder}/README.md": (
            f"# {folder}\n\n"
            + (
                "Execution output is created here when tests run.\n"
                if folder == "TestResults/Reports"
                else "Store the framework's " + folder + " artifacts here as they are created.\n"
            )
        )
        for folder in FOLDERS
    }
