from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents import TestStorageAgent as StorageAgent
from app.agents.lifecycle_agents import BusinessRulesAgent
from app.agents.test_case_validator import ValidationReport
from app.config import Settings, get_settings
from app.dependencies import get_multi_agent_pipeline
from app.main import app
from app.memory import OrganizationalMemory
from app.models import (
    GenerateRequest,
    GenerationTarget,
    LlmModel,
    ManualTestingType,
    ReviewFeedbackRequest,
)
from app.models import TestSuite as Suite
from app.services import MultiAgentTestPipeline
from app.services.document_ingestion import InputAgent


def example_suite(mode="manual", title="Valid login"):
    return Suite.model_validate(
        {
            "feature_name": "Account access",
            "test_cases": [
                {
                    "id": "TC-001",
                    "title": title,
                    "objective": "Verify account access",
                    "category": "smoke",
                    "priority": "P1",
                    "execution_mode": mode,
                    "feasibility_reason": "Observable account response",
                    "steps": [{"action": "Sign in", "expected_result": "Account opens"}],
                    "gherkin": (
                        "Scenario: Login\n Given an account\n"
                        " When signing in\n Then access is granted"
                    )
                    if mode == "automation"
                    else None,
                }
            ],
        }
    )


def report(passed=True):
    return ValidationReport(
        passed=passed,
        score=100 if passed else 30,
        acceptance_criteria_total=0,
        acceptance_criteria_covered=0,
    )


def pipeline_for(memory, candidate, passed=True):
    generate = AsyncMock(return_value=candidate)
    generator = SimpleNamespace(generate=generate, generate_revision=generate)
    validator = SimpleNamespace(validate=lambda request, suite: report(passed))
    return MultiAgentTestPipeline(InputAgent(), generator, validator, StorageAgent(memory))


@pytest.mark.parametrize("mode", ["manual", "automation", "both"])
def test_review_saved_then_regenerated_and_reused_for_original_request(tmp_path, mode):
    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "knowledge.db")
    memory = OrganizationalMemory(settings.organizational_memory_path)
    request = GenerateRequest(
        description="Users must sign in to access their account",
        generation_target=mode,
        business_rules=[{"id": "BR-1", "description": "Reject invalid credentials"}],
    )
    source = example_suite("automation" if mode == "automation" else "manual")
    revised = example_suite(
        "automation" if mode == "automation" else "manual", "Invalid password is rejected"
    )
    if mode == "both":
        source.test_cases.append(
            example_suite("automation").test_cases[0].model_copy(update={"id": "TC-002"})
        )
        revised.test_cases.append(
            example_suite("automation", "Invalid password is rejected")
            .test_cases[0]
            .model_copy(update={"id": "TC-002"})
        )
    enriched = BusinessRulesAgent().enrich(request)
    memory.put(enriched, source)
    pipeline = pipeline_for(memory, revised)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_multi_agent_pipeline] = lambda: pipeline
    try:
        client = TestClient(app)
        payload = {
            "request": request.model_dump(mode="json"),
            "suite": source.model_dump(mode="json"),
            "comments": "TC-001: cover invalid passwords with an explicit rejection result",
        }
        first = client.post("/api/reviews", json=payload)
        assert first.status_code == 200
        assert client.post("/api/reviews", json=payload).json() == first.json()
        # Feedback is durable before generation is attempted.
        reopened = OrganizationalMemory(settings.organizational_memory_path)
        assert payload["comments"] in reopened.with_reviews(enriched).additional_context
        response = client.post("/api/agent/run", json=request.model_dump(mode="json"))
        assert response.status_code == 200
        assert response.json()["source_request"] == request.model_dump(mode="json")
        assert response.json()["suite"]["test_cases"][0]["title"] == "Invalid password is rejected"
        seen = pipeline.generator.generate.call_args.args[0]
        assert payload["comments"] in seen.additional_context
        assert "BR-1" in seen.additional_context
        assert "TC-001" in seen.additional_context
        assert seen.generation_target == request.generation_target
        assert (
            client.post("/api/agent/run", json=request.model_dump(mode="json")).status_code == 200
        )
        assert pipeline.generator.generate.await_count == 1
    finally:
        app.dependency_overrides.clear()


def test_feedback_is_scoped_but_follows_provider_changes(tmp_path):
    memory = OrganizationalMemory(tmp_path / "memory.db")
    source = GenerateRequest(
        description="Users sign in to their account", generation_target="manual"
    )
    memory.save_review(source, example_suite(), "Expect the status ABC")
    reviewed = memory.with_reviews(source)
    assert "Expect the status ABC" in reviewed.additional_context
    assert (
        memory.with_reviews(
            source.model_copy(update={"description": "Users create a new quotation"})
        ).additional_context
        == ""
    )
    assert (
        memory.with_reviews(
            source.model_copy(update={"generation_target": GenerationTarget.AUTOMATION})
        ).additional_context
        == ""
    )

    assert (
        "Expect the status ABC"
        in memory.with_reviews(
            source.model_copy(update={"llm_model": LlmModel.OPENAI})
        ).additional_context
    )
    memory.save_review(source, example_suite(), "Expect the status abc")
    assert memory.key_for(memory.with_reviews(source)) != memory.key_for(reviewed)


@pytest.mark.asyncio
async def test_failed_regeneration_keeps_feedback_without_approving_output(tmp_path):
    memory = OrganizationalMemory(tmp_path / "memory.db")
    source = GenerateRequest(description="Users sign in to their account")
    memory.save_review(source, example_suite(), "Include an invalid password case")
    pipeline = pipeline_for(memory, example_suite(), passed=False)
    result = await pipeline.run(source)
    assert not result.validation.passed
    assert memory.get(memory.with_reviews(source)) is None
    pipeline.generator.generate.side_effect = RuntimeError("provider offline")
    with pytest.raises(RuntimeError, match="provider offline"):
        await pipeline.run(source)
    assert (
        "invalid password"
        in OrganizationalMemory(memory.path).with_reviews(source).additional_context
    )


def test_rejects_blank_reviews_and_disabled_knowledge(tmp_path):
    source = GenerateRequest(description="Users sign in to their account")
    with pytest.raises(ValidationError):
        ReviewFeedbackRequest(request=source, suite=example_suite(), comments="   ")
    with pytest.raises(ValueError, match="disabled"):
        OrganizationalMemory(tmp_path / "disabled.db", enabled=False).save_review(
            source, example_suite(), "Add negative tests"
        )
    assert not (tmp_path / "disabled.db").exists()


@pytest.mark.asyncio
async def test_document_regeneration_keeps_extracted_requirements_and_settings(tmp_path):
    from app.services.document_ingestion import ExtractedDocument

    source = GenerateRequest(description="Extracted document requires secure account access")
    memory = OrganizationalMemory(tmp_path / "memory.db")
    pipeline = pipeline_for(memory, example_suite())
    pipeline.input_agent = SimpleNamespace(
        from_document=lambda *args: (
            ExtractedDocument("requirements.pdf", "application/pdf", source.description),
            source,
        )
    )
    result = await pipeline.run_document(
        "requirements.pdf",
        b"document",
        generation_target=GenerationTarget.MANUAL,
        manual_testing_type=ManualTestingType.DATABASE,
        llm_model=LlmModel.OPENAI,
    )
    assert result.source_request.description == source.description
    assert result.source_request.generation_target == "manual"
    assert result.source_request.manual_testing_type == "database"
    assert result.source_request.llm_model == "openai"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["manual", "automation"])
async def test_targeted_review_preserves_unrelated_tests_even_if_model_changes_them(tmp_path, mode):
    memory = OrganizationalMemory(tmp_path / "memory.db")
    request = GenerateRequest(description="Users sign in to their account", generation_target=mode)
    original = example_suite(mode)
    original.test_cases.append(
        example_suite(mode, "Unrelated case").test_cases[0].model_copy(update={"id": "TC-002"})
    )
    memory.save_review(request, original, "TC-001: require an explicit rejection result")
    candidate = example_suite(mode, "Revised login")
    candidate.test_cases.append(
        example_suite(mode, "Unwanted edit").test_cases[0].model_copy(update={"id": "TC-002"})
    )
    pipeline = pipeline_for(memory, candidate)
    pipeline.runtime = SimpleNamespace(run=AsyncMock())
    result = await pipeline.run(request)
    assert result.suite.test_cases[0].title == "Revised login"
    assert result.suite.test_cases[1].model_dump() == original.test_cases[1].model_dump()
    assert [case.id for case in result.suite.test_cases] == ["TC-001", "TC-002"]
    pipeline.runtime.run.assert_not_awaited()
    assert "TARGETED REVIEW" in pipeline.generator.generate.call_args.args[0].additional_context


@pytest.mark.asyncio
async def test_missing_target_does_not_store_revision(tmp_path):
    memory = OrganizationalMemory(tmp_path / "memory.db")
    request = GenerateRequest(description="Users sign in to their account")
    original = example_suite()
    memory.save_review(request, original, "TC-001: revise expected result")
    candidate = example_suite()
    candidate.test_cases[0].id = "TC-002"
    with pytest.raises(ValueError, match="each requested test ID"):
        await pipeline_for(memory, candidate).run(request)
    assert memory.get(memory.with_reviews(request)) is None


def test_review_target_matching_rejects_unknown_and_supports_exact_titles(tmp_path):
    memory = OrganizationalMemory(tmp_path / "memory.db")
    request = GenerateRequest(description="Users sign in to their account")
    with pytest.raises(ValueError, match="unknown test ID"):
        memory.save_review(request, example_suite(), "TC-0010: update result")
    assert memory.review_targets(example_suite(), "Valid login: update result") == {"TC-001"}
    assert memory.review_targets(example_suite(), "tc-001: update result") == {"TC-001"}


@pytest.mark.asyncio
async def test_explicit_case_review_does_not_expand_scope_from_comments(tmp_path):
    memory = OrganizationalMemory(tmp_path / "memory.db")
    request = GenerateRequest(description="Users sign in to their account")
    original = example_suite()
    original.test_cases.append(
        original.test_cases[0].model_copy(update={"id": "TC-002", "title": "Other login"})
    )
    memory.save_review(request, original, "Match the wording used in TC-002", "TC-001")
    reopened = OrganizationalMemory(memory.path)
    assert reopened.latest_targeted_review(request)[1] == {"TC-001"}
    assert '"test_case_id": "TC-001"' in reopened.with_reviews(request).additional_context
    candidate = example_suite(title="Revised login")
    result = await pipeline_for(reopened, candidate).run(request)
    assert result.suite.test_cases[0].title == "Revised login"
    assert result.suite.test_cases[1] == original.test_cases[1]
    with pytest.raises(ValueError, match="unknown test ID"):
        memory.save_review(request, original, "Revise expected result", "TC-999")
