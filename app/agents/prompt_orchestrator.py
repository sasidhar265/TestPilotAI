"""Understand a user's requested artifact before choosing a governed workflow."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent_instructions import load_agent_instructions
from app.agents.artifact_runner import ArtifactGenerationRunner
from app.agents.business_analyst import BusinessAnalystAgent
from app.agents.runner import StructuredAgentDefinition
from app.agents.workflow_agent import WorkflowAgent
from app.config import Settings
from app.models import GenerateRequest, GenerationTarget, ManualTestingType
from app.observability import publish_lifecycle_event
from app.services.website_framework import build_website_framework, website_target


class PromptIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow: Literal["website-framework", "test-cases", "stories", "business-analysis", "clarify"]
    summary: str = Field(min_length=10, max_length=1500)
    questions: list[str] = Field(default_factory=list, max_length=10)
    generation_target: GenerationTarget = GenerationTarget.AUTO
    testing_type: ManualTestingType = ManualTestingType.API


class PromptResult(BaseModel):
    workflow: Literal["prompt-result"] = "prompt-result"
    intent: PromptIntent
    source_request: GenerateRequest
    result: dict[str, Any] = Field(default_factory=dict)


class PromptOrchestrator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.runner = ArtifactGenerationRunner(settings)

    async def interpret(self, request: GenerateRequest) -> PromptIntent:
        publish_lifecycle_event(
            "OrchestratorAgent",
            "understand_request",
            "running",
            "Understanding the requested outcome before selecting a workflow.",
        )
        intent = await self.runner.generate_structured(
            StructuredAgentDefinition(
                PromptIntent,
                "Understanding the request timed out.",
                "No request interpretation returned.",
                "Invalid request interpretation.",
            ),
            instructions=load_agent_instructions("prompt-orchestrator"),
            prompt=request.model_dump_json(),
            llm_model=request.llm_model,
        )
        if intent.questions:
            intent.workflow = "clarify"
        if intent.workflow == "clarify" and not intent.questions:
            intent.questions = [
                "What should I produce: a framework, test cases, stories or a requirements review?"
            ]
        return intent

    async def run(self, request: GenerateRequest, pipeline: Any) -> PromptResult:
        intent = (
            PromptIntent(
                workflow=request.requested_workflow,
                summary=f"Preparing the requested {request.requested_workflow} output.",
                generation_target=request.generation_target,
                testing_type=request.manual_testing_type,
            )
            if request.requested_workflow
            else await self.interpret(request)
        )
        if intent.questions or intent.workflow == "clarify":
            return PromptResult(intent=intent, source_request=request)
        publish_lifecycle_event(
            "OrchestratorAgent",
            "select_workflow",
            "success",
            intent.summary,
        )
        source = request.model_copy(
            update={
                "generation_target": intent.generation_target,
                "manual_testing_type": intent.testing_type,
            }
        )
        if intent.workflow == "website-framework":
            artifact = await build_website_framework(
                source, website_target(source.description), self.settings
            )
            result = artifact.model_dump(mode="json")
        elif intent.workflow == "stories":
            result = (await WorkflowAgent(self.settings).stories(source)).model_dump(mode="json")
        elif intent.workflow == "business-analysis":
            result = (await BusinessAnalystAgent(self.settings).review(source)).model_dump(
                mode="json"
            )
        else:
            generated = await pipeline.run(source)
            result = {
                "suite": generated.suite.model_dump(mode="json"),
                "validation": generated.validation.model_dump(mode="json"),
            }
        return PromptResult(intent=intent, source_request=source, result=result)
