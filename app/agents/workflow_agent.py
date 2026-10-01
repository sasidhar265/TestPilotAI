"""Markdown-directed story and scenario agents with validated stage handoffs."""

import json

from app.agent_instructions import load_agent_instructions
from app.agents import AgentKind, FunctionalAgentDescriptor
from app.agents.artifact_runner import ArtifactGenerationRunner
from app.agents.requirements_validation import RequirementsValidationAgent
from app.agents.runner import StructuredAgentDefinition
from app.agents.validation_evidence import fingerprint, functionality, labels
from app.agents.workflow_knowledge_agent import WorkflowKnowledgeAgent
from app.config import Settings
from app.models import GenerateRequest
from app.observability import publish_lifecycle_event
from app.workflow_models import ScenarioHandoff, Scenarios, Stories, StoryHandoff


class WorkflowAgent:
    def __init__(self, settings: Settings):
        self.runner = ArtifactGenerationRunner(settings)
        self.knowledge = WorkflowKnowledgeAgent(settings)
        self.requirements_validator = RequirementsValidationAgent(settings)

    async def stories(self, request: GenerateRequest) -> Stories:
        await self.requirements_validator.require(request)

        def validate(result: Stories) -> Stories:
            try:
                StoryHandoff(request=request, stories=result)
            except ValueError:
                self._story_evidence(request, result, passed=False)
                raise
            self._story_evidence(request, result, passed=True)
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
            try:
                ScenarioHandoff(request=handoff.request, stories=handoff.stories, scenarios=result)
            except ValueError:
                self._scenario_evidence(handoff, result, passed=False)
                raise
            self._scenario_evidence(handoff, result, passed=True)
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

    @staticmethod
    def _story_evidence(request: GenerateRequest, stories: Stories, *, passed: bool) -> None:
        outcome = "passed" if passed else "failed"
        publish_lifecycle_event(
            "Story Agent",
            "validation_basis",
            outcome,
            functionality(request) + f" Story grounding {outcome} for {len(stories.stories)} "
            f"stories and {sum(len(s.acceptance_criteria) for s in stories.stories)} criteria. "
            "Checked unique story IDs and exact source excerpts against this requirement text. "
            f"Open questions: {len(stories.open_questions)}. "
            "This check does not establish complete requirements coverage or business approval.",
        )
        publish_lifecycle_event(
            "Story Agent",
            "validation_source",
            "info",
            f"Requirement text in request {fingerprint(request)}; stories {fingerprint(stories)}. "
            "Artifacts: " + labels([f"{s.id}: {s.title}" for s in stories.stories]) + ". "
            "Validation rules: StoryHandoff source grounding and unique IDs.",
        )

    @staticmethod
    def _scenario_evidence(handoff: StoryHandoff, scenarios: Scenarios, *, passed: bool) -> None:
        outcome = "passed" if passed else "failed"
        publish_lifecycle_event(
            "Scenario Agent",
            "validation_basis",
            outcome,
            functionality(handoff.request) + f" Scenario traceability {outcome} for "
            f"{len(scenarios.scenarios)} scenarios across {len(handoff.stories.stories)} stories. "
            "Checked unique scenario IDs, known story ownership, criteria drawn from the owning "
            "story, and coverage of every story and its acceptance criteria. "
            f"Open questions: {len(scenarios.open_questions)}. This is a design check.",
        )
        publish_lifecycle_event(
            "Scenario Agent",
            "validation_source",
            "info",
            f"Reviewed stories {fingerprint(handoff.stories)} from request "
            f"{fingerprint(handoff.request)}. "
            "Stories: " + labels([f"{s.id}: {s.title}" for s in handoff.stories.stories]) + ". "
            "Scenario ownership: "
            + labels([f"{s.id} → {s.story_id}: {s.title}" for s in scenarios.scenarios])
            + ". "
            "Validation rules: StoryHandoff and ScenarioHandoff traceability.",
        )


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
