"""Stage handoff integrity and provider composition, without live model dependencies."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.agents.workflow_agent import WorkflowAgent
from app.agents.workflow_agent import test_case_request as build_request
from app.config import Settings
from app.models import GenerateRequest, GenerationTarget
from app.workflow_models import ScenarioHandoff, Scenarios, Stories, StoryHandoff
from app.workflow_routes import ExecutionPlanRequest, create_cases, execution_plan

FIXTURES = json.loads(Path("automation/Input/Workflow.Json").read_text())


def handoff():
    return ScenarioHandoff.model_validate(FIXTURES["approved-scenarios"]["body"])


def test_story_evidence_must_be_in_original_source():
    with pytest.raises(ValidationError, match="exact, contiguous quote") as error:
        StoryHandoff.model_validate(FIXTURES["ungrounded-stories"]["body"])
    assert "source_excerpt" in str(error.value)
    assert "request.description" in str(error.value)


def test_scenario_rejects_unknown_story_and_duplicate_ids():
    with pytest.raises(ValidationError, match="unknown story"):
        ScenarioHandoff.model_validate(FIXTURES["orphan-scenarios"]["body"])
    data = copy.deepcopy(FIXTURES["approved-scenarios"]["body"])
    data["scenarios"]["scenarios"] *= 2
    with pytest.raises(ValidationError, match="unique"):
        ScenarioHandoff.model_validate(data)


def test_scenario_cannot_invent_acceptance_criteria():
    data = copy.deepcopy(FIXTURES["approved-scenarios"]["body"])
    data["scenarios"]["scenarios"][0]["acceptance_criteria"] = ["An invented business rule"]
    with pytest.raises(ValidationError, match="acceptance criteria"):
        ScenarioHandoff.model_validate(data)


def test_conversion_preserves_source_target_and_traceability_instructions():
    source = handoff()
    source.request.generation_target = GenerationTarget.MANUAL
    result = build_request(source)
    assert result.description == source.request.description
    assert result.generation_target == "manual"
    assert '"ST-001"' in result.additional_context
    assert '"SC-001"' in result.additional_context
    assert "acceptance_criteria_covered" in result.additional_context


@pytest.mark.asyncio
async def test_agents_load_markdown_and_validate_provider_output(tmp_path):
    source = handoff()
    agent = WorkflowAgent(
        Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    )
    agent.runner.generate_structured = AsyncMock(return_value=source.stories)
    assert await agent.stories(source.request) == source.stories
    call = agent.runner.generate_structured.call_args
    assert "stage 2" in call.kwargs["instructions"]
    assert "exact, contiguous quote" in call.kwargs["instructions"]
    assert call.kwargs["validate"](source.stories) == source.stories
    assert call.args[0].output_model is Stories
    agent.runner.generate_structured = AsyncMock(return_value=source.scenarios)
    assert await agent.scenarios(source) == source.scenarios
    call = agent.runner.generate_structured.call_args
    assert "stage 3" in call.kwargs["instructions"]
    assert call.args[0].output_model is Scenarios


@pytest.mark.asyncio
async def test_test_case_stage_rejects_missing_handoff_coverage():
    from fastapi import HTTPException
    from test_automation_execution_agent import automation_suite

    pipeline = SimpleNamespace(
        run=AsyncMock(return_value=SimpleNamespace(suite=automation_suite()))
    )
    with pytest.raises(HTTPException, match="story/scenario"):
        await create_cases(handoff(), pipeline)


def test_execution_plan_does_not_confuse_repository_checks_with_generated_suite():
    from test_automation_execution_agent import automation_suite

    suite = automation_suite()
    plan = execution_plan(
        ExecutionPlanRequest(
            suite=suite, request=GenerateRequest(description="Check service health")
        ),
        Settings(_env_file=None),
    )
    assert not plan["ready"]
    assert "match this suite exactly" in plan["reason"]
    assert all(case["feature_file"] == "Features/generated.feature" for case in plan["cases"])


def test_scenarios_cannot_drop_a_story_acceptance_criterion():
    data = copy.deepcopy(FIXTURES["approved-scenarios"]["body"])
    data["stories"]["stories"][0]["acceptance_criteria"].append(
        "Preserve the complete source text."
    )
    with pytest.raises(ValidationError, match="every acceptance criterion"):
        ScenarioHandoff.model_validate(data)


def test_actual_runner_case_names_redact_target_credentials(tmp_path):
    from app.agents.automation_execution_agent import _test_results

    path = tmp_path / "results.trx"
    path.write_text(
        '<TestRun><Results><UnitTestResult testName="case(secret-token)" '
        'outcome="Failed" duration="00:00:01"><Output><ErrorInfo>'
        '<Message>secret-token failed the assertion</Message></ErrorInfo></Output>'
        '</UnitTestResult></Results></TestRun>'
    )
    result = _test_results(path, ["secret-token"])
    assert result == [{"name": "case([redacted])", "status": "Failed", "duration": "00:00:01", "error": "[redacted] failed the assertion"}]
