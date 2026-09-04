import asyncio

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.dependencies import get_multi_agent_pipeline, get_test_generation_service
from app.main import app, business_rules_from_document_text, log_operation_failure
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


def test_login_page_presents_ai_test_generation_workspace() -> None:
    response = client.get("/login")

    assert response.status_code == 200
    assert 'id="login-form"' in response.text
    assert "AI-assisted quality engineering" in response.text
    assert "manual and automated tests" in response.text
    assert 'src="/static/scripts/login.js?v=20260902-login-feedback"' in response.text
    assert 'id="auth-overlay"' in response.text
    assert 'id="dismiss-auth-error"' in response.text
    assert 'id="password-toggle"' in response.text
    assert 'id="forgot-password"' in response.text
    assert 'aria-label="Show password"' in response.text
    assert 'id="theme-gear"' in response.text
    assert 'id="theme-menu"' in response.text
    assert 'data-theme-option="light"' in response.text
    assert 'data-theme-option="dark"' in response.text
    assert 'data-theme-option="system"' in response.text
    assert 'src="/static/scripts/theme.js?v=20260901-shared-theme"' in response.text
    assert "styles/login-feedback.css?v=20260902" in response.text


def test_home_has_format_radios_and_generation_timer() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert "Risk categories" not in response.text
    assert "Automation / manual" not in response.text
    assert "Sole AI runtime" not in response.text
    assert "Execution topology" not in response.text
    assert 'id="output-target"' in response.text
    assert '<option value="manual">Manual</option>' in response.text
    assert "Normal steps" not in response.text
    automation_option = (
        '<option value="automation" selected>Automation (BDD / Gherkin)</option>'
    )
    assert automation_option in response.text
    assert '<option value="both">Both manual and automation</option>' in response.text
    assert 'id="timer" role="timer"' in response.text
    assert 'id="download-feature"' in response.text
    assert 'id="generate-step-definitions"' in response.text
    assert 'id="step-definition-files"' in response.text
    assert 'id="download-step-definitions"' in response.text
    assert "↓ .feature" in response.text
    assert 'id="stop-generation"' in response.text
    assert 'id="publish-panel"' not in response.text
    assert 'id="business-rules"' in response.text
    assert 'id="business-rules-file"' in response.text
    assert 'id="source-state"' in response.text
    assert 'id="jira-source-key"' in response.text
    assert 'id="add-requirement-source"' in response.text
    assert 'id="requirement-source-menu"' in response.text
    assert 'id="show-jira-link"' in response.text
    assert 'id="jira-link-panel"' in response.text
    assert 'id="generation-overlay"' in response.text
    assert 'id="cancel-generation-overlay"' in response.text
    assert 'id="generation-llm-provider"' in response.text
    assert 'id="generation-llm-model"' in response.text
    assert 'id="generation-llm-auth"' in response.text
    assert 'id="generation-background-state"' in response.text
    assert 'id="generation-background-events"' in response.text
    assert 'id="generation-agent"' not in response.text
    assert 'id="llm-model"' in response.text
    assert 'value="auto-fallback" selected' in response.text
    assert 'value="openai"' in response.text
    assert 'value="codex"' in response.text
    assert 'value="gpt-5.3-codex"' in response.text
    assert 'id="model-access-overlay"' in response.text
    assert 'id="close-model-access"' in response.text
    assert 'aria-label="Close model access details"' in response.text
    assert 'id="save-business-rules"' in response.text
    assert "The repository BRD baseline and Quality Gate remain protected" in response.text
    assert 'id="agent-workspace"' in response.text
    assert 'href="#agent-workspace"' in response.text
    assert 'class="panel agent-workspace"' in response.text
    assert 'class="panel agent-workspace hidden"' not in response.text
    assert 'class="secondary lifecycle-action" id="generate-data" disabled' in response.text
    assert 'id="execution-dashboard"' not in response.text
    assert 'id="defects-dashboard"' not in response.text
    assert 'id="summarize-execution"' not in response.text
    assert 'id="draft-defects"' not in response.text
    assert 'id="metrics-dashboard"' in response.text
    assert "Business Rules Agent" in response.text
    assert "Bug Reporter Agent" not in response.text
    assert "Metrics Agent" in response.text
    assert 'class="suite-approval"' in response.text
    assert 'id="context"' not in response.text
    assert 'src="/static/scripts/theme.js?v=20260901-shared-theme"' in response.text
    assert 'src="/static/scripts/index.js?v=20260904-profile-menu"' in response.text
    assert 'id="generate" type="submit" disabled' in response.text
    assert 'href="/static/styles/index.css?v=20260904-profile-menu"' in response.text
    assert 'id="theme-gear"' in response.text
    assert 'id="theme-menu"' in response.text
    assert 'data-theme-option="light"' in response.text
    assert 'data-theme-option="dark"' in response.text
    assert 'data-theme-option="system"' in response.text
    assert 'id="accept-selected"' in response.text
    assert 'id="accepted-by"' in response.text
    assert 'id="reviewer-error" role="alert"' in response.text
    assert 'id="notification-bell"' in response.text
    assert 'id="notification-panel"' in response.text
    assert 'id="notification-list"' in response.text
    assert 'id="knowledge-notice-overlay"' in response.text
    assert 'id="close-knowledge-notice"' in response.text
    assert 'id="profile-toggle"' in response.text
    assert 'id="profile-panel"' in response.text
    assert 'class="profile-signout" id="logout"' in response.text
    assert 'id="accepted-manual-format"' not in response.text
    assert 'id="acceptance-receipt"' in response.text
    assert 'class="suite-jira"' in response.text
    assert "↗ Jira" in response.text
    assert 'id="jira-key-error" role="alert"' in response.text
    assert 'href="/documentation#integrations"' not in response.text
    assert 'id="runtime-health"' in response.text
    assert 'id="server-location"' in response.text
    assert 'id="active-agent"' in response.text
    assert 'id="model-name"' in response.text
    assert 'id="llm-details"' in response.text
    assert 'id="agent-details"' in response.text
    assert 'id="orchestration-details"' in response.text
    assert 'id="live-agent-events"' in response.text
    assert 'id="live-agent-feed-state"' in response.text
    assert "Model-directed coordinator" in response.text
    assert "AgentRuntime" in response.text
    assert "Copilot SDK + CLI" in response.text
    assert 'href="/logs"' in response.text


def test_business_rule_document_text_replaces_overlay_with_stable_ids() -> None:
    rules = business_rules_from_document_text(
        "Business rules\nBR-SEC-01: Require a signed token\nReject expired sessions"
    )

    assert [(rule.id, rule.description) for rule in rules] == [
        ("BR-UPLOAD-001", "Business rules"),
        ("BR-SEC-01", "Require a signed token"),
        ("BR-UPLOAD-003", "Reject expired sessions"),
    ]


def test_logs_page_has_search_and_navigation() -> None:
    response = client.get("/logs")
    assert response.status_code == 200
    assert 'id="log-reference"' in response.text
    assert 'id="search-logs"' in response.text
    assert 'href="/documentation"' in response.text
    assert 'id="theme-gear"' in response.text
    assert 'src="/static/scripts/theme.js?v=20260901-shared-theme"' in response.text


def test_documentation_page_is_not_cached() -> None:
    response = client.get("/documentation")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert "Markdown-directed, Python-governed" in response.text
    assert "/api/step-definitions/reqnroll" in response.text
    assert 'id="theme-gear"' in response.text
    assert 'id="profile-toggle"' in response.text
    assert 'class="profile-signout" id="logout"' in response.text
    assert 'href="/static/styles/documentation.css?v=20260904-current-ui"' in response.text
    assert 'src="/static/scripts/documentation.js?v=20260904-current-ui"' in response.text
    assert 'src="/static/scripts/theme.js?v=20260901-shared-theme"' in response.text


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
    assert response.json()["active_agent"] == "Resilient AI Test Designer"
    assert response.json()["agent_runtime_id"] == "automatic-fallback"
    assert response.json()["copilot_model"] == "organization-default"
    assert response.json()["openai_model"] == "gpt-5.4"
    assert response.json()["codex_model"] == "account-default"
    assert response.json()["agent_profile"] == "auto-finance-quotation"
    assert response.json()["organizational_memory"] == "enabled"
    assert isinstance(response.json()["organizational_memory_entries"], int)


def test_model_access_endpoint_returns_permission_and_quota(monkeypatch) -> None:
    async def inspect(settings, model):
        assert model == "gpt-5.3-codex"
        return {
            "model": model,
            "display_name": "GPT-5.3-Codex",
            "available": True,
            "policy": "enabled",
            "billing_multiplier": 1,
            "quota": {"remaining_percentage": 75},
            "can_use": True,
            "reason": "Available",
        }

    monkeypatch.setattr("app.main.inspect_model_access", inspect)
    response = client.get("/api/llm/models/gpt-5.3-codex/access")

    assert response.status_code == 200
    assert response.json()["can_use"] is True
    assert response.json()["quota"]["remaining_percentage"] == 75


def test_model_access_endpoint_rejects_unlisted_model() -> None:
    response = client.get("/api/llm/models/not-approved/access")

    assert response.status_code == 422


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


def test_generation_lifecycle_events_are_incremental_and_payload_free() -> None:
    from app.observability import lifecycle_events

    request_id = "lifecycle-test-request"
    lifecycle_events.start(request_id)
    lifecycle_events.publish(
        request_id,
        "Quality Gate",
        "validate_suite",
        "passed",
        "Validated 4 cases with score 100/100.",
    )
    lifecycle_events.complete(request_id)

    response = client.get(f"/api/generation/{request_id}/events", params={"after": 0})
    incremental = client.get(f"/api/generation/{request_id}/events", params={"after": 1})

    assert response.status_code == 200
    assert response.json()["complete"] is True
    assert response.json()["events"][0]["agent"] == "Quality Gate"
    assert response.json()["events"][0]["summary"] == "Validated 4 cases with score 100/100."
    assert incremental.json()["events"] == []


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
        "orchestrator",
        "decision",
        "manual-test-generator",
        "manual-testing-specialist",
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
    assert agents[3]["runtime"] == "local-orchestrator"
    assert agents[4]["runtime"] == "local-router"
    assert agents[3]["instruction_file"] == ".github/agents/testpilot-coordinator.agent.md"
    assert agents[4]["instruction_file"] == ".github/agents/reqforge.agent.md"
    assert agents[9]["instruction_file"] == ".github/agents/context-converter.agent.md"
    assert agents[10]["runtime"] == "local-sqlite"


def test_documentation_page_describes_agents_and_use_cases() -> None:
    home = client.get("/")
    assert 'href="/documentation"' in home.text

    response = client.get("/documentation")
    assert response.status_code == 200
    assert "Agents and responsibilities" in response.text
    assert "Application use cases" in response.text
    assert "GET /api/agents" in response.text
    assert "Document-to-tests" in response.text
    assert "Generated Suite actions" in response.text
    assert "Activity and reuse notices" in response.text
    assert 'href="/#agent-workspace"' not in response.text
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

    captured_rules = []
    captured_manual_types = []

    class StubPipeline:
        async def run_document(
            self,
            filename,
            content,
            additional_context,
            output_format,
            business_rules=None,
            manual_testing_type="api",
            generation_target="auto",
            llm_model="organization-default",
        ):
            captured_rules.extend(business_rules or [])
            captured_manual_types.append(manual_testing_type)
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
            data={
                "output_format": "normal",
                "generation_target": "manual",
                "manual_testing_type": "database",
                "business_rules": (
                    "BR-CUSTOM-001: Reject expired campaigns\n"
                    "BR-CUSTOM-002: Preserve the correlation ID"
                ),
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    result = response.json()
    assert result["filename"] == "requirements.xlsx"
    assert result["extracted_characters"] > 0
    assert result["suite"]["test_cases"][0]["id"] == "TC-001"
    assert result["validation"]["score"] <= 100
    assert [rule.id for rule in captured_rules] == ["BR-CUSTOM-001", "BR-CUSTOM-002"]
    assert captured_manual_types[0] == "database"


def test_document_generation_rejects_duplicate_business_rule_ids() -> None:
    response = client.post(
        "/api/generate/document",
        files={"file": ("requirements.pdf", b"document bytes", "application/pdf")},
        data={
            "business_rules": (
                "BR-CUSTOM-001: Reject expired campaigns\n"
                "BR-CUSTOM-001: Preserve the correlation ID"
            )
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Business rule BR-CUSTOM-001 is duplicated."


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
