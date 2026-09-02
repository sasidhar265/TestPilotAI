"""Model-directed Copilot agent runtime for test-design goals."""

import asyncio
import json
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from pydantic import BaseModel, Field

from app.agent_instructions import load_agent_instructions
from app.agents import TestStorageAgent
from app.agents.runner import CopilotAgentRunner, CopilotGenerationError, CopilotTimeoutError
from app.agents.test_case_generator_agent import TestCaseGeneratorAgent
from app.agents.test_case_validator import TestCaseValidatorAgent, ValidationReport
from app.config import Settings
from app.models import GenerateRequest, TestSuite
from app.observability import lifecycle_events, publish_lifecycle_event, request_id_context


class AgentEvent(BaseModel):
    sequence: int = Field(ge=1)
    tool: str
    status: str
    summary: str


class AgentOutcome(BaseModel):
    suite: TestSuite
    validation: ValidationReport
    trace: list[AgentEvent]


class DesignParams(BaseModel):
    revision_instructions: str = Field(
        default="", description="Specific validation findings to correct, empty for a first draft"
    )


class AgentRuntime:
    """Give Copilot safe application tools and let it direct their execution."""

    def __init__(
        self,
        settings: Settings,
        generator: TestCaseGeneratorAgent,
        validator: TestCaseValidatorAgent,
        storage: TestStorageAgent,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self.generator = generator
        self.validator = validator
        self.storage = storage
        self.client_factory = client_factory

    async def run(self, request: GenerateRequest) -> AgentOutcome:
        try:
            from copilot.tools import ToolResult, define_tool
        except ImportError as error:
            raise CopilotGenerationError(
                "GitHub Copilot SDK is not installed. Run 'pip install -e .' and restart."
            ) from error

        trace: list[AgentEvent] = []
        run_request_id = request_id_context.get()
        suite: TestSuite | None = None
        validation: ValidationReport | None = None
        finished = False
        active_specialist_task: asyncio.Task[TestSuite] | None = None

        def record(tool: str, status: str, summary: str) -> None:
            event = AgentEvent(sequence=len(trace) + 1, tool=tool, status=status, summary=summary)
            trace.append(event)
            agent = {
                "lookup_memory": "Knowledge Agent",
                "design_test_suite": "QA Master → ReqForge",
                "validate_test_suite": "Quality Gate",
                "store_validated_suite": "Test Storage Agent",
                "finish_run": "QA Master Agent",
            }.get(tool, "QA Master Agent")
            if run_request_id != "-":
                lifecycle_events.publish(run_request_id, agent, tool, status, summary)

        @define_tool(
            description="Look for an already validated exact-match suite in memory.",
            skip_permission=True,
            defer="never",
        )
        def lookup_memory() -> str:
            nonlocal suite, validation
            suite = self.storage.find(request)
            if suite is None:
                record("lookup_memory", "miss", "No reusable suite matched the goal.")
                return json.dumps({"found": False})
            validation = self.validator.validate(request, suite)
            record("lookup_memory", "success", f"Found {len(suite.test_cases)} reusable cases.")
            return json.dumps({"found": True, "validation": validation.model_dump(mode="json")})

        @define_tool(
            description=(
                "Ask QA Master to design scenarios from ingested UI input and have ReqForge "
                "transform them into the requested test-case format."
            ),
            skip_permission=True,
            defer="never",
        )
        async def design_test_suite(params: DesignParams) -> str:
            nonlocal active_specialist_task, suite, validation
            design_request = request
            if params.revision_instructions:
                design_request = request.model_copy(
                    update={
                        "additional_context": (
                            request.additional_context
                            + "\n\nVALIDATION CORRECTIONS REQUIRED\n"
                            + params.revision_instructions
                        ).strip()
                    }
                )
            correlation_token = request_id_context.set(run_request_id)
            try:
                active_specialist_task = asyncio.create_task(
                    self.generator.generate(design_request),
                    name=f"specialist-generation-{run_request_id}",
                )
                suite = await active_specialist_task
            finally:
                if active_specialist_task is not None and active_specialist_task.done():
                    active_specialist_task = None
                request_id_context.reset(correlation_token)
            validation = None
            action = "Revised" if params.revision_instructions else "Transformed"
            record(
                "design_test_suite",
                "success",
                f"QA Master and ReqForge {action.lower()} {len(suite.test_cases)} cases.",
            )
            return json.dumps(suite.model_dump(mode="json"))

        @define_tool(
            description="Run the independent deterministic quality gate on the current suite.",
            skip_permission=True,
            defer="never",
        )
        def validate_test_suite() -> Any:
            nonlocal validation
            if suite is None:
                return ToolResult(
                    text_result_for_llm="No suite exists. Design one first.", result_type="failure"
                )
            validation = self.validator.validate(request, suite)
            status = "passed" if validation.passed else "failed"
            record("validate_test_suite", status, f"Quality score: {validation.score}/100.")
            return ToolResult(text_result_for_llm=validation.model_dump_json())

        @define_tool(
            description="Store the current suite, but only after independent validation passes.",
            skip_permission=True,
            defer="never",
        )
        def store_validated_suite() -> Any:
            nonlocal suite
            if suite is None or validation is None or not validation.passed:
                return ToolResult(
                    text_result_for_llm="Validation must pass before storage.",
                    result_type="failure",
                )
            suite = self.storage.store(request, suite)
            record("store_validated_suite", "success", "Saved the approved suite for reuse.")
            return ToolResult(text_result_for_llm=json.dumps({"stored": True}))

        @define_tool(
            description="Complete the run after the current suite has passed validation.",
            skip_permission=True,
            defer="never",
            is_terminal=True,
        )
        def finish_run() -> Any:
            nonlocal finished
            if suite is None or validation is None or not validation.passed:
                return ToolResult(
                    text_result_for_llm="Cannot finish until validation passes.",
                    result_type="failure",
                )
            finished = True
            record("finish_run", "success", "Goal completed with a validated test suite.")
            return ToolResult(text_result_for_llm=json.dumps({"completed": True}))

        tools = [
            lookup_memory,
            design_test_suite,
            validate_test_suite,
            store_validated_suite,
            finish_run,
        ]
        runner = CopilotAgentRunner(self.settings, self.client_factory)
        publish_lifecycle_event(
            "QA Master Agent",
            "coordinate",
            "running",
            "Coordinator is selecting governed lifecycle tools from the normalized request.",
        )
        try:
            await runner.invoke(
                instructions=load_agent_instructions("testpilot-coordinator"),
                prompt="REQUEST ENVELOPE\n" + request.model_dump_json(),
                timeout_error=(
                    "The coordinator agent timed out while waiting for its governed tools."
                ),
                tools=tools,
                capture_response=False,
                timeout_seconds=self.settings.copilot_coordinator_timeout_seconds,
            )
        except CopilotTimeoutError:
            task = active_specialist_task
            if task is not None and not task.done():
                task.cancel("Coordinator stopped before specialist completion")
                with suppress(asyncio.CancelledError):
                    await task
            return await self._recover_incomplete_run(request, suite, validation, trace)
        except (CopilotGenerationError, asyncio.CancelledError):
            task = active_specialist_task
            if task is not None and not task.done():
                task.cancel("Coordinator stopped before specialist completion")
                with suppress(asyncio.CancelledError):
                    await task
            raise

        if not finished or suite is None or validation is None:
            return await self._recover_incomplete_run(request, suite, validation, trace)
        return AgentOutcome(suite=suite, validation=validation, trace=trace)

    async def _recover_incomplete_run(
        self,
        request: GenerateRequest,
        suite: TestSuite | None,
        validation: ValidationReport | None,
        trace: list[AgentEvent],
    ) -> AgentOutcome:
        """Complete safely when the model-directed coordinator idles prematurely."""

        def record(tool: str, status: str, summary: str) -> None:
            event = AgentEvent(sequence=len(trace) + 1, tool=tool, status=status, summary=summary)
            trace.append(event)
            publish_lifecycle_event("Governed Recovery", tool, status, summary)

        record(
            "coordinator_recovery",
            "started",
            "Coordinator became idle before completion; using the governed fallback workflow.",
        )
        if suite is None:
            suite = await self.generator.generate(request)
            record(
                "design_test_suite",
                "success",
                (
                    f"Fallback transformed {len(suite.test_cases)} QA Master scenarios "
                    "through ReqForge."
                ),
            )
        if validation is None:
            validation = self.validator.validate(request, suite)
            status = "passed" if validation.passed else "failed"
            record("validate_test_suite", status, f"Quality score: {validation.score}/100.")
        if not validation.passed:
            raise CopilotGenerationError(
                "The recovered test suite did not pass the quality gate. Try adding explicit "
                "acceptance criteria to the requirement."
            )
        suite = self.storage.store(request, suite)
        record("store_validated_suite", "success", "Saved the recovered approved suite.")
        record("finish_run", "success", "Recovered coordinator run completed successfully.")
        return AgentOutcome(suite=suite, validation=validation, trace=trace)
