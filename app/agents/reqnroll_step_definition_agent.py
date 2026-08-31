"""Generate ReqnRoll C# bindings from approved automation scenarios."""

import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from app.agent_instructions import step_definition_agent_instructions
from app.agents.runner import CopilotAgentRunner, StructuredAgentDefinition
from app.agents.test_case_validator import ValidationReport
from app.config import Settings
from app.models import ExecutionMode, TestSuite


class StepCoverage(BaseModel):
    gherkin_step: str
    status: str = Field(pattern=r"^(reused|generated|blocked)$")
    binding: str


class StepDefinitionFile(BaseModel):
    path: str = Field(pattern=r"^[A-Za-z0-9_./-]+\.cs$")
    content: str = Field(min_length=1)


class StepDefinitionArtifact(BaseModel):
    framework: str = "ReqnRoll"
    language: str = "C#"
    files: list[StepDefinitionFile] = Field(min_length=1)
    coverage: list[StepCoverage] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class StepDefinitionRequest(BaseModel):
    suite: TestSuite
    validation: ValidationReport


STEP_DEFINITION_AGENT = StructuredAgentDefinition(
    output_model=StepDefinitionArtifact,
    timeout_error="ReqnRoll step-definition generation timed out. Try again.",
    empty_error="GitHub Copilot did not return step definitions.",
    invalid_error="GitHub Copilot returned invalid ReqnRoll step-definition output.",
)


class ReqnRollStepDefinitionAgent:
    """Use the approved Copilot runtime to create reviewable C# implementation artifacts."""

    def __init__(
        self, settings: Settings, client_factory: Callable[..., Any] | None = None
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory

    async def generate(self, request: StepDefinitionRequest) -> StepDefinitionArtifact:
        if not request.validation.passed:
            raise ValueError("Step definitions require a Quality Gate-approved suite.")
        automation_cases = [
            case
            for case in request.suite.test_cases
            if case.execution_mode == ExecutionMode.AUTOMATION and case.gherkin
        ]
        if not automation_cases:
            raise ValueError(
                "The suite has no automation Gherkin to convert into step definitions."
            )

        schema = json.dumps(StepDefinitionArtifact.model_json_schema(), separators=(",", ":"))
        source = request.suite.model_copy(update={"test_cases": automation_cases}).model_dump_json()
        prompt = f"APPROVED AUTOMATION SUITE\n{source}\n\nARTIFACT SCHEMA\n{schema}"
        runner = CopilotAgentRunner(self.settings, self.client_factory)
        return await runner.generate_structured(
            STEP_DEFINITION_AGENT,
            instructions=step_definition_agent_instructions(self.settings.agent_profile),
            prompt=prompt,
        )
