"""Build from clean Docker inputs so local egg-info cannot hide discovery errors."""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def test_clean_docker_context_builds_only_application_package(tmp_path):
    root = Path(__file__).resolve().parents[1]
    context = tmp_path / "context"
    context.mkdir()
    for name in ("pyproject.toml", "README.md"):
        shutil.copyfile(root / name, context / name)
    for name in ("app", "workspace"):
        shutil.copytree(root / name, context / name, ignore=shutil.ignore_patterns("__pycache__"))
    wheels = tmp_path / "wheels"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheels),
            ".",
        ],
        cwd=context,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with zipfile.ZipFile(next(wheels.glob("*.whl"))) as wheel:
        files = set(wheel.namelist())
    assert {
        "app/main.py",
        "app/agents/automation_execution_agent.py",
        "app/services/automation_reports.py",
        "app/templates/reqnroll/testcontext.cs",
        "app/templates/reqnroll/ApiService.cs",
        "app/templates/framework/Automation.csproj",
        "app/templates/framework/run.py",
        "app/static/index.html",
        "app/static/scripts/dashboard.js",
        "app/static/styles/index.css",
    } <= files
    assert not any(path.startswith(("workspace/", "automation/", "tests/")) for path in files)
