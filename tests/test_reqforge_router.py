import pytest

from app.agents import AgentCapability, AgentDescriptor, AgentRegistry
from app.agents.test_case_generator_agent import TestCaseGeneratorAgent as ReqForgeRouter
from app.models import ExecutionMode, GenerateRequest, GenerationTarget
from app.models import TestCase as Case
from app.models import TestCategory as Category
from app.models import TestStep as Step
from app.models import TestSuite as Suite


class RouteAwareProvider:
    descriptor = AgentDescriptor(
        runtime_id="github-copilot",
        display_name="Route-aware provider",
        capabilities=frozenset({AgentCapability.TEST_DESIGN}),
    )

    def __init__(self) -> None:
        self.targets: list[GenerationTarget] = []

    async def generate(self, request, phase="initial", existing_titles=None):
        self.targets.append(request.generation_target)
        mode = ExecutionMode(request.generation_target.value)
        return Suite(
            feature_name="Sign in",
            test_cases=[
                Case(
                    id="TC-001",
                    title=f"{mode.value.title()} sign in",
                    objective=f"Cover the {mode.value} path",
                    category=Category.CRITICAL,
                    priority="P0",
                    execution_mode=mode,
                    feasibility_reason=f"Suitable for {mode.value} execution",
                    steps=[Step(action="Sign in", expected_result="Dashboard is displayed")],
                )
            ],
        )


@pytest.mark.asyncio
async def test_explicit_automation_action_calls_only_automation_specialist() -> None:
    provider = RouteAwareProvider()
    router = ReqForgeRouter(AgentRegistry(provider))

    result = await router.generate(
        GenerateRequest(
            description="Create tests for secure customer sign in.",
            generation_target="automation",
        )
    )

    assert provider.targets == [GenerationTarget.AUTOMATION]
    assert {case.execution_mode for case in result.test_cases} == {ExecutionMode.AUTOMATION}


@pytest.mark.asyncio
async def test_orchestrator_routes_neutral_manual_output_to_manual_specialist() -> None:
    provider = RouteAwareProvider()
    router = ReqForgeRouter(AgentRegistry(provider))

    result = await router.generate(
        GenerateRequest(description="Create tests for secure customer sign in.")
    )

    assert provider.targets == [GenerationTarget.MANUAL]
    assert {case.execution_mode for case in result.test_cases} == {ExecutionMode.MANUAL}


def test_orchestrator_routes_neutral_bdd_output_to_automation_specialist() -> None:
    router = ReqForgeRouter(AgentRegistry(RouteAwareProvider()))

    route = router.route(
        GenerateRequest(
            description="Create tests for secure customer sign in.", output_format="bdd"
        )
    )

    assert route == GenerationTarget.AUTOMATION


def test_auto_route_uses_selected_bdd_output_format() -> None:
    router = ReqForgeRouter(AgentRegistry(RouteAwareProvider()))

    route = router.route(
        GenerateRequest(
            description="Generate coverage for customer sign in.", output_format="bdd"
        )
    )

    assert route == GenerationTarget.AUTOMATION


@pytest.mark.asyncio
async def test_manual_output_is_revised_from_quality_gate_findings() -> None:
    class RevisingProvider(RouteAwareProvider):
        async def generate(self, request, phase="initial", existing_titles=None):
            result = await super().generate(request, phase, existing_titles)
            manual = result.test_cases[0]
            if request.generation_target == GenerationTarget.MANUAL:
                covered = bool(request.additional_context)
                manual = manual.model_copy(
                    update={
                        "execution_mode": ExecutionMode.MANUAL,
                        "acceptance_criteria_covered": ["BR-1"] if covered else [],
                    }
                )
                return result.model_copy(update={"test_cases": [manual]})
            return result

    provider = RevisingProvider()
    router = ReqForgeRouter(AgentRegistry(provider))
    request = GenerateRequest(
        description="""Review account lockout manually.
BR-1: Lock the account after five failed sign-in attempts""",
        generation_target="manual",
    )

    result = await router.generate(request)

    assert provider.targets == [GenerationTarget.MANUAL, GenerationTarget.MANUAL]
    assert result.test_cases[0].acceptance_criteria_covered == ["BR-1"]


@pytest.mark.asyncio
async def test_segregated_automation_output_is_generated_and_quality_gated() -> None:
    class RevisingAutomationProvider(RouteAwareProvider):
        async def generate(self, request, phase="initial", existing_titles=None):
            result = await super().generate(request, phase, existing_titles)
            automated = result.test_cases[0]
            if request.generation_target == GenerationTarget.AUTOMATION:
                covered = "AUTOMATION QUALITY GATE" in request.additional_context
                automated = automated.model_copy(
                    update={"acceptance_criteria_covered": ["AC-1"] if covered else []}
                )
                return result.model_copy(update={"test_cases": [automated]})
            return result

    provider = RevisingAutomationProvider()
    router = ReqForgeRouter(AgentRegistry(provider))
    request = GenerateRequest(
        description="""Automate secure customer sign in with Playwright.
AC-1: Valid credentials open the dashboard""",
        generation_target="automation",
        output_format="bdd",
    )

    result = await router.generate(request)

    assert provider.targets == [GenerationTarget.AUTOMATION, GenerationTarget.AUTOMATION]
    assert result.test_cases[0].execution_mode == ExecutionMode.AUTOMATION
    assert result.test_cases[0].acceptance_criteria_covered == ["AC-1"]


@pytest.mark.asyncio
async def test_mixed_route_keeps_valid_automation_when_manual_gate_fails() -> None:
    class InvalidManualProvider(RouteAwareProvider):
        async def generate(self, request, phase="initial", existing_titles=None):
            result = await super().generate(request, phase, existing_titles)
            if request.generation_target == GenerationTarget.MANUAL:
                invalid = result.test_cases[0].model_copy(
                    update={
                        "steps": [
                            Step(action="Review the option", expected_result="It works correctly")
                        ]
                    }
                )
                return result.model_copy(update={"test_cases": [invalid]})
            return result

    provider = InvalidManualProvider()
    router = ReqForgeRouter(AgentRegistry(provider))

    result = await router.generate(
        GenerateRequest(
            description="Keep the user signed in between browser sessions.",
            generation_target="both",
        )
    )

    assert {case.execution_mode for case in result.test_cases} == {ExecutionMode.AUTOMATION}
    assert any("Manual scenarios were excluded" in note for note in result.coverage_notes)
