"""Canonical, language-independent automation framework layout."""

import re
from collections.abc import Iterable, Sequence
from pathlib import PurePosixPath
from typing import Protocol

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
LAYOUT_INSTRUCTIONS = """
MANDATORY AUTOMATION FRAMEWORK LAYOUT (all languages):
Use sibling folders Reqnroll/, Features/, StepDefinitions/, Hooks/, TestContext/,
Services/, Builders/, Models/, Utilities/, TestResults/Reports/, Input/.
Keep dependency manifests and README.md at the framework root. Reqnroll is the
runner/configuration folder name for EVERY language; retain the selected BDD runtime.
Use Features/*.feature, StepDefinitions/*StepDefinition.<ext>, Hooks/Hooks.<ext>,
TestContext/testcontext.<ext>, Services/*Service.<ext>, Builders/*builder.<ext>,
Models/*Model.<ext>, Utilities/*Utility.<ext>, and Input/TestData.Json.
Use the selected language's extension and valid class/module identifiers.
Put real created artifacts into their role's folder, never Support/, src/, or features/.
Do not invent unnecessary business models or fixture values to fill unused folders.
Wire imports, feature discovery, hook registration and test-data loading to these paths.
Runner configuration belongs in Reqnroll; output belongs in TestResults/Reports.
Python uses the supplied Reqnroll/run.py adapter to stage Behave's conventional runtime
tree temporarily: author hooks in Hooks/Hooks.py and bindings in StepDefinitions/.
Java must configure Maven testSourceDirectory to the framework root with explicit
includes for the source folders, resources from Features and Input, and a runner
under Reqnroll. Cucumber-JS/TS and Ruby must explicitly load Hooks and StepDefinitions.
Root build/dependency manifests are allowed, but no source code at the root.
"""


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
