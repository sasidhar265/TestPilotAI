import asyncio

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.dependencies import get_multi_agent_pipeline, get_test_generation_service
from app.main import app, log_operation_failure
from app.models import ExecutionMode
from app.models import TestCase as Case
from app.models import TestCategory as Category
from app.models import TestStep as Step
from app.models import TestSuite as Suite
from app.observability import request_id_context, ui_log_handler

client = TestClient(app)


def test_frontend_assets_are_served() -> None:
    stylesheet = client.get("/static/styles/index.css")
    script = client.get("/static/scripts/index.js")

    assert stylesheet.status_code == 200
    assert "text/css" in stylesheet.headers["content-type"]
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]


def test_home_has_format_radios_and_generation_timer() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert "Risk categories" not in response.text
    assert "Automation / manual" not in response.text
    assert "Sole AI runtime" not in response.text
    assert "Execution topology" not in response.text
    assert 'type="radio" name="format" value="normal"' in response.text
    assert "Manual test" in response.text
    assert "Normal steps" not in response.text
    assert 'type="radio" name="format" value="bdd"' in response.text
    assert 'id="timer" role="timer"' in response.text
    assert 'id="download-feature"' in response.text
    assert 'id="generate-step-definitions"' in response.text
    assert 'id="step-definition-files"' in response.text
    assert 'id="download-step-definitions"' in response.text
    assert "↓ .feature" in response.text
    assert 'id="stop-generation"' in response.text
    assert 'id="publish-panel"' in response.text
    assert 'id="business-rules"' not in response.text
    assert 'id="agent-workspace"' in response.text
    assert 'href="#agent-workspace"' in response.text
    assert 'class="panel agent-workspace"' in response.text
    assert 'class="panel agent-workspace hidden"' not in response.text
    assert 'class="secondary lifecycle-action" id="generate-data" disabled' in response.text
    assert 'id="execution-dashboard"' in response.text
    assert 'id="defects-dashboard"' in response.text
    assert 'id="metrics-dashboard"' in response.text
    assert "Business Rules Agent" in response.text
    assert "Bug Reporter Agent" in response.text
    assert "Metrics Agent" in response.text
    assert 'aria-labelledby="publish-title"' in response.text
    assert 'id="context"' not in response.text
    assert 'src="/static/scripts/index.js?v=20260831-input-state"' in response.text
    assert 'id="generate" type="submit" disabled' in response.text
    assert 'href="/static/styles/index.css?v=20260831-fluid-type"' in response.text
    assert 'id="runtime-health"' in response.text
    assert 'id="server-location"' in response.text
    assert 'id="active-agent"' in response.text
    assert 'id="model-name"' in response.text
    assert 'id="llm-details"' in response.text
    assert 'id="agent-details"' in response.text
    assert 'id="orchestration-details"' in response.text
    assert "TestGenerationService" in response.text
    assert "Copilot SDK + CLI" in response.text
    assert 'href="/logs"' in response.text


def test_logs_page_has_search_and_navigation() -> None:
    response = client.get("/logs")
    assert response.status_code == 200
    assert 'id="log-reference"' in response.text
    assert 'id="search-logs"' in response.text
    assert 'href="/documentation"' in response.text


def test_documentation_page_is_not_cached() -> None:
    response = client.get("/documentation")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert "Markdown-directed, Python-governed" in response.text
    assert "/api/step-definitions/reqnroll" in response.text


def test_logs_can_be_searched_by_failure_reference_id() -> None:
    reference_id = "test-failure-reference-guid"
    failed = client.get("/api/not-found", headers={"X-Request-ID": reference_id})

    assert failed.status_code == 404
    assert failed.headers["x-request-id"] == reference_id

    response = client.get("/api/logs", params={"request_id": reference_id})
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["request_id"] == reference_id
    assert entries[0]["level"] == "WARNING"
    assert "status=404" in entries[0]["message"]


def test_failure_logs_include_payload_free_technical_details() -> None:
    reference_id = "detailed-failure-guid"
    token = request_id_context.set(reference_id)
    try:
        try:
            raise ValueError("private submitted requirement")
        except ValueError as error:
            log_operation_failure("test_operation", 502, error)
    finally:
        request_id_context.reset(token)

    entry = ui_log_handler.search(request_id=reference_id)[0]
    assert "operation=test_operation" in entry["message"]
    assert "status=502" in entry["message"]
    assert "error_type=ValueError" in entry["message"]
    assert "ValueError" in entry["exception"]
    assert "test_failure_logs_include_payload_free_technical_details" in entry["exception"]
    assert "private submitted requirement" not in entry["exception"]


def test_health_reports_configuration() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["execution_host"] == "local-fastapi-uvicorn"
    assert response.json()["active_agent"] == "GitHub Copilot Test Designer"
    assert response.json()["agent_runtime_id"] == "github-copilot"
    assert response.json()["copilot_model"] == "organization-default"
    assert response.json()["agent_profile"] == "auto-finance-quotation"
    assert response.json()["organizational_memory"] == "enabled"
    assert isinstance(response.json()["organizational_memory_entries"], int)


def test_health_reports_disabled_memory_and_configured_jira() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        organizational_memory_enabled=False,
        jira_base_url="https://example.atlassian.net",
        jira_email="tester@example.com",
        jira_api_token="test-token",
    )
    try:
        response = client.get("/api/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["organizational_memory"] == "disabled"
    assert response.json()["organizational_memory_entries"] == 0
    assert response.json()["jira_configured"] is True


def test_cancel_endpoint_reports_unknown_generation() -> None:
    response = client.post("/api/generation/not-active/cancel")

    assert response.status_code == 200
    assert response.json() == {"request_id": "not-active", "cancelled": False}


def test_http_baseline_security_and_correlation_headers() -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "qe-check-123"})

    assert response.headers["x-request-id"] == "qe-check-123"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_agents_endpoint_lists_functional_pipeline_in_order() -> None:
    response = client.get("/api/agents")
    assert response.status_code == 200
    agents = response.json()
    assert [agent["kind"] for agent in agents] == [
        "input",
        "business-rules",
        "knowledge",
        "specforge-router",
        "manual-test-generator",
        "automation-test-generator",
        "validator",
        "context-converter",
        "output",
        "test-storage",
        "test-data",
        "execution",
        "bug-reporter",
        "metrics",
    ]
    assert agents[3]["runtime"] == "local-router"
    assert agents[4]["runtime"] == "github-copilot"
    assert agents[3]["instruction_file"] == ".github/agents/specforge.agent.md"
    assert agents[7]["instruction_file"] == ".github/agents/context-converter.agent.md"
    assert agents[9]["runtime"] == "local-sqlite"


def test_documentation_page_describes_agents_and_use_cases() -> None:
    home = client.get("/")
    assert 'href="/documentation"' in home.text

    response = client.get("/documentation")
    assert response.status_code == 200
    assert "Agents and responsibilities" in response.text
    assert "Application use cases" in response.text
    assert "GET /api/agents" in response.text
    assert "Document-to-tests" in response.text
    assert 'id="company-documents"' in response.text
    assert 'data-document="requirements"' in response.text


def test_company_documents_are_available_through_allowlisted_api() -> None:
    response = client.get("/api/documentation/company/requirements")
    assert response.status_code == 200
    document = response.json()
    assert document["id"] == "requirements"
    assert document["title"] == "Company solution requirements"
    assert "## 3. Functional requirements" in document["content"]

    missing = client.get("/api/documentation/company/not-allowed")
    assert missing.status_code == 404


def test_generate_validates_short_input() -> None:
    response = client.post("/api/generate", json={"description": "short"})
    assert response.status_code == 422


class StubGenerationService:
    async def generate(self, request) -> Suite:
        return Suite(
            feature_name="Basket",
            output_format=request.output_format,
            test_cases=[
                Case(
                    id="TC-001",
                    title="Add item",
                    objective="Add an available item",
                    category=Category.CRITICAL,
                    priority="P0",
                    execution_mode=ExecutionMode.AUTOMATION,
                    feasibility_reason="Repeatable flow with observable application state",
                    steps=[Step(action="Add an item", expected_result="Item is in basket")],
                )
            ],
        )

    async def expand(self, expansion) -> Suite:
        return await self.generate(expansion.request)

    async def convert(self, request) -> Suite:
        return await self.generate(request)


def test_bdd_format_returns_gherkin_scenarios(monkeypatch) -> None:
    app.dependency_overrides[get_test_generation_service] = lambda: StubGenerationService()
    app.dependency_overrides[get_settings] = lambda: Settings()
    try:
        response = client.post(
            "/api/generate",
            json={
                "description": "As a customer, I want to add an item to my basket.",
                "output_format": "bdd",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    suite = response.json()
    assert suite["output_format"] == "bdd"


def test_copilot_provider_supports_background_expansion_contract(monkeypatch) -> None:
    app.dependency_overrides[get_test_generation_service] = lambda: StubGenerationService()
    app.dependency_overrides[get_settings] = lambda: Settings()
    try:
        response = client.post(
            "/api/generate/expand",
            json={
                "request": {"description": "As a customer, I want to update my delivery address."},
                "existing_titles": ["Update a valid delivery address"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["test_cases"]


def test_document_pipeline_extracts_generates_and_validates(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.agents.test_case_validator import ValidationReport
    from app.services.document_ingestion import ExtractedDocument

    class StubPipeline:
        async def run_document(
            self, filename, content, additional_context, output_format, business_rules=None
        ):
            request = type("Request", (), {"output_format": output_format})()
            return SimpleNamespace(
                document=ExtractedDocument(
                    filename,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "AC-1: Customer can add an available item to the basket",
                ),
                suite=await StubGenerationService().generate(request),
                validation=ValidationReport(
                    passed=True,
                    score=100,
                    acceptance_criteria_total=1,
                    acceptance_criteria_covered=1,
                ),
            )

    app.dependency_overrides[get_multi_agent_pipeline] = lambda: StubPipeline()
    try:
        response = client.post(
            "/api/generate/document",
            files={
                "file": (
                    "requirements.xlsx",
                    b"representative workbook bytes",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            data={"output_format": "normal"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    result = response.json()
    assert result["filename"] == "requirements.xlsx"
    assert result["extracted_characters"] > 0
    assert result["suite"]["test_cases"][0]["id"] == "TC-001"
    assert result["validation"]["score"] <= 100


def test_jira_rejects_unknown_selected_case_id_before_publish(monkeypatch) -> None:
    app.dependency_overrides[get_test_generation_service] = lambda: StubGenerationService()
    app.dependency_overrides[get_settings] = lambda: Settings()
    try:
        generated = client.post(
            "/api/generate",
            json={"description": "As a user, I want to update my profile."},
        ).json()
        response = client.post(
            "/api/jira/publish",
            json={
                "issue_key": "QA-123",
                "suite": generated,
                "selected_case_ids": ["TC-NOT-PRESENT"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "Unknown selected test case IDs" in response.json()["detail"]


def test_context_converter_endpoint_requires_passing_validation() -> None:
    suite = StubGenerationService()
    generated = asyncio.run(suite.generate(type("Request", (), {"output_format": "normal"})()))
    payload = {
        "suite": generated.model_dump(mode="json"),
        "validation": {
            "passed": False,
            "score": 70,
            "acceptance_criteria_total": 1,
            "acceptance_criteria_covered": 0,
            "findings": [],
        },
    }

    response = client.post("/api/context-converter/xlsx", json=payload)

    assert response.status_code == 422
    assert "quality-gate-approved" in response.json()["detail"]
