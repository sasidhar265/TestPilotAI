"""Markdown-directed story and scenario agents with validated stage handoffs."""

from app.agent_instructions import load_agent_instructions
from app.agents import AgentKind, FunctionalAgentDescriptor
from app.agents.artifact_runner import ArtifactGenerationRunner
from app.agents.runner import StructuredAgentDefinition
from app.config import Settings
from app.models import GenerateRequest
from app.workflow_models import ScenarioHandoff, Scenarios, Stories, StoryHandoff


class WorkflowAgent:
    def __init__(self, settings: Settings):
        self.runner = ArtifactGenerationRunner(settings)

    async def stories(self, request: GenerateRequest) -> Stories:
        def validate(result: Stories) -> Stories:
            StoryHandoff(request=request, stories=result)
            return result

        return await self.runner.generate_structured(
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

    async def scenarios(self, handoff: StoryHandoff) -> Scenarios:
        def validate(result: Scenarios) -> Scenarios:
            ScenarioHandoff(**handoff.model_dump(), scenarios=result)
            return result

        return await self.runner.generate_structured(
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


def test_case_request(handoff: ScenarioHandoff) -> GenerateRequest:
    context = "\n\n".join(
        [
            handoff.request.additional_context,
            load_agent_instructions("workflow-test-cases"),
            handoff.stories.model_dump_json(),
            handoff.scenarios.model_dump_json(),
        ]
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
