"""Markdown-directed story and scenario agents with validated stage handoffs."""

import json

from app.agent_instructions import load_agent_instructions
from app.agents import AgentKind, FunctionalAgentDescriptor
from app.agents.artifact_runner import ArtifactGenerationRunner
from app.agents.requirements_validation import RequirementsValidationAgent
from app.agents.runner import StructuredAgentDefinition
from app.agents.workflow_knowledge_agent import WorkflowKnowledgeAgent
from app.config import Settings
from app.models import GenerateRequest
from app.workflow_models import ScenarioHandoff, Scenarios, Stories, StoryHandoff


class WorkflowAgent:
    def __init__(self, settings: Settings):
        self.runner = ArtifactGenerationRunner(settings)
        self.knowledge = WorkflowKnowledgeAgent(settings)
        self.requirements_validator = RequirementsValidationAgent(settings)

    async def stories(self, request: GenerateRequest) -> Stories:
        await self.requirements_validator.require(request)

        def validate(result: Stories) -> Stories:
            StoryHandoff(request=request, stories=result)
            return result

        key = self.knowledge.key("stories", request)
        known = self.knowledge.recall(key, Stories, validate)
        if known is not None:
            return known
        result = await self.runner.generate_structured(
            StructuredAgentDefinition(
                Stories,
                "Story generation timed out.",
                "No stories returned.",
                "Story generation returned invalid output.",
            ),
            instructions=load_agent_instructions("story-generator"),
            prompt=request.model_dump_json()
            + "\nOUTPUT SCHEMA\n"
            + str(Stories.model_json_schema()),
            validate=validate,
        )
        self.knowledge.remember(key, validate(result))
        return result

    async def scenarios(self, handoff: StoryHandoff) -> Scenarios:
        await self.requirements_validator.require(
            handoff.request.model_copy(
                update={
                    "additional_context": handoff.request.additional_context
                    + "\n"
                    + handoff.stories.model_dump_json()
                }
            )
        )

        def validate(result: Scenarios) -> Scenarios:
            ScenarioHandoff(request=handoff.request, stories=handoff.stories, scenarios=result)
            return result

        source = StoryHandoff(request=handoff.request, stories=handoff.stories)
        key = self.knowledge.key("scenarios", source)
        known = self.knowledge.recall(key, Scenarios, validate)
        if known is not None:
            return known
        result = await self.runner.generate_structured(
            StructuredAgentDefinition(
                Scenarios,
                "Scenario generation timed out.",
                "No scenarios returned.",
                "Scenario generation returned invalid output.",
            ),
            instructions=load_agent_instructions("scenario-generator"),
            prompt=handoff.model_dump_json()
            + "\nOUTPUT SCHEMA\n"
            + str(Scenarios.model_json_schema()),
            validate=validate,
        )
        self.knowledge.remember(key, validate(result))
        return result


def test_case_request(handoff: ScenarioHandoff) -> GenerateRequest:
    stories = handoff.stories.model_dump(mode="json")
    scenarios = handoff.scenarios.model_dump(mode="json")
    for payload in (stories, scenarios):
        payload.pop("generation_source", None)
        payload.pop("memory_key", None)
    context = "\n\n".join(
        [
            handoff.request.additional_context,
            load_agent_instructions("workflow-test-cases"),
            json.dumps(stories),
            json.dumps(scenarios),
        ]
    )
    if len(context) > 100_000:
        raise ValueError(
            "Reviewed stories and scenarios exceed the 100,000-character generation context "
            "limit. Reduce the handoff size or split the requirements into smaller batches."
        )
    return GenerateRequest(**{**handoff.request.model_dump(), "additional_context": context})


STORY_AGENT = FunctionalAgentDescriptor(
    id="story-generator-agent",
    name="Story Agent",
    kind=AgentKind.STORY_GENERATOR,
    purpose="Convert BRD, prompt and Jira requirements into source-grounded user stories.",
    runtime="configured-ai-providers",
    capabilities=("requirements-to-stories", "source-traceability"),
    instruction_file=".github/agents/story-generator.agent.md",
)
SCENARIO_AGENT = FunctionalAgentDescriptor(
    id="scenario-generator-agent",
    name="Scenario Agent",
    kind=AgentKind.SCENARIO_GENERATOR,
    purpose="Design format-neutral scenario coverage for reviewed story acceptance criteria.",
    runtime="configured-ai-providers",
    capabilities=("stories-to-scenarios", "story-traceability"),
    instruction_file=".github/agents/scenario-generator.agent.md",
)
