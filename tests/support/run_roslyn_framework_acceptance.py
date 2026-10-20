"""Generate and execute a complete ReqnRoll pack against an isolated quotation echo fixture.

This verifies generated framework wiring and the approved payload, not business behavior of
an external quotation service. The generated pack and its actual TRX remain in the temp folder.
"""

import asyncio
import json
import os
import subprocess
import tempfile
import threading
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app.agents.reqnroll_step_definition_agent import (
    ReqnRollStepDefinitionAgent,
    StepDefinitionRequest,
)
from app.agents.test_case_validator import ValidationReport
from app.config import Settings
from app.models import TestCase, TestStep, TestSuite
from app.quotation_contract import PAYLOAD_PATH


def main():
    payload = json.loads(PAYLOAD_PATH.read_text())
    requests = []

    class Echo(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            valid = self.path == "/quotes" and body == payload
            requests.append(valid)
            encoded = json.dumps(payload).encode()
            self.send_response(201 if valid else 400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    cases = []
    for index, assertion in enumerate(
        [
            'And the response JSON field "Outlet.code" equals "OUTLET001"',
            'And the response decimal field "Parameters.Term" equals 36',
        ],
        1,
    ):
        cases.append(
            TestCase(
                id=f"TC-ROSLYN-{index:03}",
                title=f"Approved quotation transport {index}",
                objective="Verify generated framework wiring with the approved quotation payload",
                category="smoke",
                priority="P1",
                execution_mode="automation",
                feasibility_reason="Isolated local HTTP fixture with explicit expected values",
                steps=[
                    TestStep(
                        action="Send approved quotation", expected_result="Approved values returned"
                    )
                ],
                gherkin=f"""Scenario: Approved quotation transport {index}
 Given the approved quotation request
 When I send a "POST" request to "/quotes"
 Then the response status is 201
 {assertion}""",
            )
        )
    suite = TestSuite(
        feature_name="Roslyn generated quotation framework", output_format="bdd", test_cases=cases
    )
    settings = Settings(
        _env_file=None, runtime_config_path=None, organizational_memory_enabled=False
    )
    artifact = asyncio.run(
        ReqnRollStepDefinitionAgent(settings).generate(
            StepDefinitionRequest(
                suite=suite,
                validation=ValidationReport(
                    passed=True,
                    score=100,
                    acceptance_criteria_total=0,
                    acceptance_criteria_covered=0,
                ),
            )
        )
    )
    root = Path(tempfile.mkdtemp(prefix="roslyn-generated-framework-"))
    for file in artifact.files:
        target = root / file.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file.content)
    (root / "global.json").write_text('{"sdk":{"version":"8.0.100","rollForward":"latestFeature"}}')
    server = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = os.environ | {
            "API_BASE_URL": f"http://127.0.0.1:{server.server_port}",
            "API_BEARER_TOKEN": "",
            "API_FIXTURE_FILE": "",
        }
        result = subprocess.run(
            [
                "dotnet",
                "test",
                "Automation.csproj",
                "-p:NuGetAudit=false",
                "--logger",
                "trx;LogFileName=generated-framework.trx",
                "--results-directory",
                "TestResults/Reports",
            ],
            cwd=root,
            env=env,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"Generated BDD run failed; inspect {root}")
        trx = ET.parse(root / "TestResults/Reports/generated-framework.trx")
        counters = next(item.attrib for item in trx.iter() if item.tag.endswith("Counters"))
        assert int(counters["executed"]) == 2 and int(counters["passed"]) == 2, counters
        assert int(counters["failed"]) == 0, counters
        assert requests == [True, True], requests
        print(f"GENERATED_REQNROLL_PASSED: 2 executed, 2 passed; pack and TRX: {root}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
