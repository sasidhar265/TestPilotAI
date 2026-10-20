"""C# compiler parsing alongside Tree-sitter, without executing generated source."""

import json
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from threading import Lock

_TOOL = Path(__file__).resolve().parent / "tools" / "roslyn"
_DLL = _TOOL / "bin" / "Release" / "net8.0" / "RoslynSyntax.dll"
_BUILD_LOCK = Lock()


def _tool() -> tuple[str, str]:
    dotnet = shutil.which("dotnet")
    if not dotnet:
        raise RuntimeError("install the .NET 8 SDK to validate generated C#")
    with _BUILD_LOCK:
        sources = [_TOOL / name for name in ("Program.cs", "RoslynSyntax.csproj", "global.json")]
        if not _DLL.exists() or _DLL.stat().st_mtime < max(p.stat().st_mtime for p in sources):
            result = subprocess.run(
                [
                    dotnet,
                    "build",
                    "RoslynSyntax.csproj",
                    "-c",
                    "Release",
                    "--nologo",
                    "-v",
                    "quiet",
                ],
                cwd=_TOOL,
                capture_output=True,
                text=True,
                timeout=60,
                env=os.environ | {"DOTNET_CLI_TELEMETRY_OPTOUT": "1"},
                check=False,
            )
            if result.returncode:
                raise RuntimeError("build app/tools/roslyn/RoslynSyntax.csproj with the .NET 8 SDK")
    return dotnet, str(_DLL)


@lru_cache(maxsize=16)
def _diagnostics(sources: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    result = subprocess.run(
        list(_tool()),
        input=json.dumps([{"path": path, "content": content} for path, content in sources]),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("the Roslyn parser failed; check the local .NET runtime")
    diagnostics = json.loads(result.stdout)
    if not isinstance(diagnostics, list):
        raise ValueError("invalid Roslyn diagnostics response")
    findings = []
    for item in diagnostics:
        if not isinstance(item, dict) or not all(
            key in item for key in ("Path", "Line", "Column", "Code", "Message")
        ):
            raise ValueError("invalid Roslyn diagnostic")
        findings.append(
            f"{item['Path']}:{item['Line']}:{item['Column']}: Roslyn {item['Code']}: "
            f"{item['Message']}"
        )
    return tuple(findings)


def csharp_syntax_findings(files) -> list[str]:
    """Check every C# file, including helpers; unavailable tooling cannot imply a pass."""
    sources = tuple((file.path, file.content) for file in files if file.path.endswith(".cs"))
    if not sources:
        return []
    try:
        return list(_diagnostics(sources))
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
        return [
            "Roslyn C# validation unavailable. Install the .NET 8 SDK and build "
            "app/tools/roslyn/RoslynSyntax.csproj before accepting generated C#; "
            "Tree-sitter checks alone do not satisfy this validation."
        ]
