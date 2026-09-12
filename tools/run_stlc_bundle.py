"""Execute an explicitly reviewed C# bundle on an ephemeral CI worker."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET


def unpack(archive_path: Path, output: Path) -> dict:
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if len(infos) > 101 or sum(item.file_size for item in infos) > 6_000_000:
            raise ValueError("Bundle exceeds file or size limits")
        if len({item.filename for item in infos}) != len(infos):
            raise ValueError("Duplicate bundle paths")
        manifest = json.loads(archive.read("manifest.json"))
        if set(archive.namelist()) != set(manifest["files"]) | {"manifest.json"}:
            raise ValueError("Manifest does not match bundle contents")
        for name, digest in manifest["files"].items():
            path = PurePosixPath(name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or ":" in name
                or str(path) != name
            ):
                raise ValueError("Unsafe bundle path")
            content = archive.read(name)
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError("Bundle content differs from reviewed manifest")
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        project = manifest["project_path"]
        if project not in manifest["files"] or not project.endswith(".csproj"):
            raise ValueError("Missing C# project")
        return manifest


def convert_results(path: Path, manifest: dict, run_key: str) -> dict:
    if path.stat().st_size > 10_000_000:
        raise ValueError("TRX exceeds 10 MB")
    raw = path.read_bytes()
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise ValueError("XML entities are unsupported")
    root = ET.fromstring(raw)
    mappings = manifest["test_mappings"]
    grouped = {}
    observed_names = set()
    outcomes = {"Passed": "passed", "Failed": "failed", "NotExecuted": "not-run"}
    for result in root.findall(".//{*}UnitTestResult"):
        name, outcome = result.get("testName"), result.get("outcome")
        if name not in mappings or outcome not in outcomes:
            raise ValueError(f"Unmapped test name or unsupported outcome: {name}")
        observed_names.add(name)
        grouped.setdefault(mappings[name], []).append(outcomes[outcome])
    if observed_names != set(mappings):
        raise ValueError("Results are missing one or more mapped tests")
    results = []
    for case_id, statuses in grouped.items():
        status = (
            "failed" if "failed" in statuses else "not-run" if "not-run" in statuses else "passed"
        )
        results.append(
            {
                "case_id": case_id,
                "status": status,
                "actual": f"{len(statuses)} mapped TRX test(s): " + ", ".join(statuses),
            }
        )
    return {
        "cycle_id": manifest["cycle_id"],
        "run_key": run_key,
        "build": manifest["build"],
        "environment": manifest["environment"],
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cycle_id")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{32}", args.cycle_id):
        raise ValueError("Expected a cycle identifier")
    output = Path("stlc-run").resolve()
    output.mkdir(exist_ok=False)
    manifest = unpack(Path("automation-packs") / f"{args.cycle_id}.zip", output)
    if manifest["cycle_id"] != args.cycle_id:
        raise ValueError("Bundle belongs to a different cycle")
    results = output / "TestResults" / "Reports" / "ci-execution"
    results.mkdir(parents=True, exist_ok=False)
    project = output / manifest["project_path"]
    subprocess.run(["dotnet", "build", str(project)], cwd=output, check=True, timeout=300)
    playwright = list(output.glob("**/bin/Debug/net8.0/playwright.ps1"))
    if playwright:
        subprocess.run(
            ["pwsh", str(playwright[0]), "install", "--with-deps", "chromium"],
            check=True,
            timeout=300,
        )
    result = subprocess.run(
        [
            "dotnet",
            "test",
            str(project),
            "--no-build",
            "--no-restore",
            "--logger",
            "trx;LogFileName=results.trx",
            "--results-directory",
            str(results),
        ],
        cwd=output,
        timeout=600,
    )
    converted = convert_results(
        results / "results.trx",
        manifest,
        f"ci-{os.getenv('GITHUB_RUN_ID', 'local')}-{os.getenv('GITHUB_RUN_ATTEMPT', '1')}",
    )
    (results / "results.json").write_text(json.dumps(converted, indent=2))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
