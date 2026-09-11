"""Run Behave with the shared source layout and a temporary discovery tree."""

import os
import shutil
import sys
import tempfile
from pathlib import Path


def main() -> int:
    from behave.__main__ import main as behave_main

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.chdir(root)
    reports = root / "TestResults" / "Reports"
    reports.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bdd-discovery-") as directory:
        features = Path(directory) / "Features"
        shutil.copytree(root / "Features", features)
        shutil.copytree(root / "StepDefinitions", features / "steps")
        shutil.copyfile(root / "Hooks" / "Hooks.py", features / "environment.py")
        return int(
            behave_main(
                [
                    str(features),
                    "--format",
                    "json",
                    "--outfile",
                    str(reports / "results.json"),
                    *sys.argv[1:],
                ]
            )
        )


if __name__ == "__main__":
    sys.exit(main())
