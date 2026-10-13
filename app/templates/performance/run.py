"""Run an API workload without accepting JMeter process success as test success."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Utilities"))
from PerformanceReportUtility import jtl_samples, report

root = Path(__file__).resolve().parents[1]
os.chdir(root)
config = json.loads((root / "Input/PerformanceConfig.Json").read_text())
target = urlparse(os.environ.get("TARGET_BASE_URL", ""))
if (
    target.scheme not in ("http", "https")
    or not target.hostname
    or target.path not in ("", "/")
    or target.username
    or target.query
):
    sys.exit("Set TARGET_BASE_URL to a real HTTP(S) origin without credentials or a path.")
run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
output = root / "TestResults/Reports" / run_id
output.mkdir(parents=True)
command = [
    os.environ.get("JMETER_BIN", "jmeter"),
    "-n",
    "-t",
    "Features/performance.jmx",
    "-q",
    "Reqnroll/jmeter.properties",
    "-Jhost=" + target.hostname,
    "-Jprotocol=" + target.scheme,
    "-Jport=" + str(target.port or (443 if target.scheme == "https" else 80)),
    "-l",
    str(output / "results.jtl"),
    "-j",
    str(output / "jmeter.log"),
    "-e",
    "-o",
    str(output / "dashboard"),
]
# Private properties supply authentication and correlation values; never export credentials.
if os.environ.get("JMETER_PRIVATE_PROPERTIES"):
    command.extend(["-q", os.environ["JMETER_PRIVATE_PROPERTIES"]])
result = subprocess.run(command, check=False)
samples = (
    jtl_samples(output / "results.jtl", config["warmup_seconds"])
    if (output / "results.jtl").exists()
    else []
)
passed = report(
    samples,
    config,
    output,
    {
        "run_id": run_id,
        "tool": "Apache JMeter",
        "target": target.geturl(),
        "tool_exit_code": result.returncode,
    },
)
print("Results:", output / "report.html")
sys.exit(0 if passed and result.returncode == 0 else 1)
