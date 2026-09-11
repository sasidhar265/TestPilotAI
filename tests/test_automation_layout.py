"""Framework migration, language routing and generated artifact regressions."""

import json
import os
import subprocess
import threading
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.agents.multilanguage_agent import (
    LANGUAGES,
    ArtifactFile,
    LanguageRequest,
    MultiLanguageAgent,
    validate_pack,
)
from app.agents.test_case_validator import ValidationReport
from app.automation_layout import FOLDERS, validate_layout_paths
from app.automation_pack import TEMPLATES, shared_assets
from app.config import Settings
from app.models import TestSuite as Suite


@pytest.mark.skipif(os.getenv("RUN_CSHARP_TESTS") != "1", reason="Requires .NET 8 SDK")
@pytest.mark.asyncio
async def test_new_api_case_is_included_and_executed_with_existing_bdd_cases(tmp_path):
    agent = MultiLanguageAgent(
        Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    )
    item = request()
    await agent.generate(item)  # Populate the same cache used by subsequent generation.
    added = item.suite.test_cases[0].model_copy(deep=True)
    added.id = "TC-2"
    added.title = "New API response"
    added.gherkin = added.gherkin.replace("Known response", "New API response").replace(
        '"/test"', '"/new-test"'
    )
    item.suite.test_cases.append(added)
    pack = await agent.generate(item)
    for file in pack.files:
        destination = tmp_path / file.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(file.content)
    inputs = json.loads((tmp_path / "Input/CaseData.Json").read_text())
    assert set(inputs) == {"TC-1", "TC-2"}
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.path, json.loads(body)))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [
                "dotnet",
                "test",
                str(tmp_path / "Automation.csproj"),
                "-p:NuGetAudit=false",
                "--logger",
                "trx;LogFileName=results.trx",
                "--results-directory",
                str(tmp_path / "TestResults/Reports"),
            ],
            cwd=tmp_path,
            env={
                **os.environ,
                "API_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                "API_FIXTURE_FILE": str(tmp_path / "Input/TestData.Json"),
                "API_BEARER_TOKEN": "",
            },
            capture_output=True,
            text=True,
            timeout=180,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert result.returncode == 0, result.stdout + result.stderr
    results = ET.parse(tmp_path / "TestResults/Reports/results.trx")
    outcomes = results.findall(".//{*}UnitTestResult")
    assert len(outcomes) == 2
    assert all(row.attrib["outcome"] == "Passed" for row in outcomes)
    assert sorted(received) == [("/new-test", {"amount": 12.3}), ("/test", {"amount": 12.3})]


def request(language="csharp"):
    return LanguageRequest(
        language=language,
        suite=Suite.model_validate(
            {
                "feature_name": "Approved API",
                "test_cases": [
                    {
                        "id": "TC-1",
                        "title": "Known response",
                        "objective": "Check status",
                        "category": "smoke",
                        "priority": "P1",
                        "execution_mode": "automation",
                        "feasibility_reason": "Known contract",
                        "steps": [{"action": "Call API", "expected_result": "Status 200"}],
                        "gherkin": (
                            'Scenario: Known response\n Given a request built from "approved"\n'
                            ' When I send a "POST" request to "/test"\n'
                            " Then the response status is 200"
                        ),
                        "test_data": [
                            {"name": "approved", "value": '{"amount":12.30}', "purpose": "request"},
                            {"name": "label", "value": "supplied text", "purpose": "description"},
                        ],
                    }
                ],
            }
        ),
        validation=ValidationReport(
            passed=True, score=100, acceptance_criteria_total=0, acceptance_criteria_covered=0
        ),
    )


@pytest.mark.asyncio
async def test_csharp_full_pack_contains_current_features_data_and_separated_helpers(tmp_path):
    agent = MultiLanguageAgent(
        Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    )
    item = request()
    pack = await agent.generate(item)
    files = {file.path: file.content for file in pack.files}
    assert all(any(path.startswith(folder + "/") for path in files) for folder in FOLDERS)
    assert "class ApiScenario" in files["TestContext/testcontext.cs"]
    assert "class ApiClient :" in files["Services/ApiService.cs"]
    assert "class ApiResponse" in files["Models/ApiResponseModel.cs"]
    assert "class ApiClientFactory" in files["Builders/ApiClientbuilder.cs"]
    assert json.loads(files["Input/TestData.Json"]) == {"approved": {"amount": 12.3}}
    assert "supplied text" in files["Input/CaseData.Json"]
    assert "Input/*.Json" in files["Automation.csproj"]
    assert "Then the response status is 200" in files["Features/generated.feature"]
    item.suite.test_cases[0].test_data[0].value = '{"amount":99}'
    updated = await agent.generate(item)
    assert json.loads(
        next(f.content for f in updated.files if f.path == "Input/TestData.Json")
    ) == {"approved": {"amount": 99}}


@pytest.mark.parametrize("language", LANGUAGES)
def test_all_binding_languages_use_canonical_paths(language):
    pack = MultiLanguageAgent(Settings(_env_file=None)).bindings(request(language))
    assert pack.files[0].path.startswith("StepDefinitions/")
    assert pack.files[0].path.endswith("StepDefinition." + LANGUAGES[language][2])
    validate_layout_paths(file.path for file in pack.files)


@pytest.mark.parametrize(
    "path",
    [
        "Support/Client.cs",
        "features/example.feature",
        "src/test/Steps.java",
        "Steps.py",
        "Services/Client.cs",
        "Features/Steps.cs",
        "Hooks/environment.py",
        "TestResults/old-report.json",
        "../Hooks/Hooks.cs",
    ],
)
def test_pack_layout_rejects_old_locations_and_misplaced_sources(path):
    with pytest.raises(ValueError):
        validate_layout_paths([path])


def test_regenerated_input_retains_all_supplied_data_without_inventing_fixtures():
    item = request()
    assets = shared_assets(item.suite)
    assert "label" not in json.loads(assets["Input/TestData.Json"])
    assert json.loads(assets["Input/CaseData.Json"])["TC-1"][1]["value"] == "supplied text"


def test_old_layout_cannot_be_returned_as_a_complete_python_pack():
    item = request("python")
    baseline = MultiLanguageAgent(Settings(_env_file=None)).bindings(item)
    pack = baseline.model_copy(deep=True)
    pack.files[0].path = "features/steps/steps.py"
    pack.files[0].content = pack.files[0].content.replace(
        'raise NotImplementedError("Implement this step")', "assert context.response is not None"
    )
    pack.files.extend(
        [
            ArtifactFile(path="requirements.txt", content="behave"),
            ArtifactFile(path="README.md", content="Run the suite."),
        ]
    )
    for mapping in pack.coverage:
        mapping.status = "generated"
    with pytest.raises(ValueError, match="framework folder"):
        validate_pack(pack, item, baseline)


@pytest.mark.skipif(not os.getenv("FRAMEWORK_PYTHON"), reason="Requires a Behave environment")
def test_python_adapter_loads_hooks_steps_context_and_input(tmp_path):
    files = {
        "Reqnroll/run.py": (TEMPLATES / "run.py").read_text(),
        "Input/TestData.Json": '{"expected": 7}',
        "Features/example.feature": (
            "Feature: Folder wiring\n Scenario: Read supplied data\n"
            "  Given the supplied input\n  Then it matches the context\n"
        ),
        "TestContext/testcontext.py": "class State:\n    expected = 7\n",
        "Hooks/Hooks.py": (
            "from TestContext.testcontext import State\n"
            "def before_scenario(context, scenario):\n    context.state = State()\n"
        ),
        "Utilities/InputUtility.py": (
            "import json\nfrom pathlib import Path\n"
            "def read_input():\n"
            "    return json.loads(Path('Input/TestData.Json').read_text())['expected']\n"
        ),
        "StepDefinitions/ExampleStepDefinition.py": (
            "from behave import given, then\nfrom Utilities.InputUtility import read_input\n"
            "@given('the supplied input')\n"
            "def supplied(context):\n    context.actual = read_input()\n"
            "@then('it matches the context')\n"
            "def matches(context):\n    assert context.actual == context.state.expected\n"
        ),
    }
    for path, content in files.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    result = subprocess.run(
        [os.environ["FRAMEWORK_PYTHON"], str(tmp_path / "Reqnroll/run.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "TestResults/Reports/results.json").read_text())
    assert report[0]["status"] == "passed"
    assert not (tmp_path / "Features/steps").exists()
