import asyncio
import json
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import ValidationError

from app.agents.contracts import AgentCapability, AgentDescriptor
from app.config import Settings
from app.models import GenerateRequest, GenerationTarget, TestCase, TestFormat, TestSuite

SYSTEM_PROMPT = """You are a senior QA engineer. Turn product requirements into a concise,
executable test suite. Classify every case as exactly one of critical, smoke, sanity, or
regression. Include positive, negative, boundary, authorization, accessibility, and failure
cases where relevant. Every step needs an observable expected result. Generate synthetic data
only. List uncertainty as assumptions. Never contradict an explicit requirement. Do not repeat
scenarios. Map each acceptance criterion to test cases. Treat explicitly labelled business rules
(for example BR-1) like acceptance criteria: preserve their meaning and include each covered rule
in acceptance_criteria_covered. Test steps must demonstrate the stated rule and must not invent
conflicting behavior.

Classify every case as `automation` or `manual`. Choose automation when execution is repeatable,
deterministic, observable through stable UI/API/system interfaces, and valuable to rerun. Choose
manual for exploratory testing, subjective usability or visual judgment, one-off investigation,
physical/hardware interaction, CAPTCHA/biometric challenges, or cases whose reliable automation
cost clearly exceeds their repeat value. Do not mark a case manual merely because it is complex.
Provide a concise, case-specific feasibility_reason for every decision.

For BDD output, write executable Gherkin compatible with SpecFlow. Use `Scenario:` for a single
flow. Use `Scenario Outline:` with `<parameter>` placeholders and a complete `Examples:` table
when the same flow should run against multiple inputs, roles, outcomes, or boundaries. Use only
Given/When/Then/And/But steps, keep steps reusable and implementation-neutral, and never put a
`Feature:` line inside an individual test case.

This is a data-generation session. Do not use tools, inspect files, or run commands. Return only
one JSON object matching the schema supplied in the user message. Do not use Markdown fences or
add commentary."""


class CopilotGenerationError(RuntimeError):
    """A safe, user-facing failure produced by the generation adapter."""


def _gherkin_from_case(case: TestCase) -> str:
    lines = [f"Scenario: {case.title}"]
    if case.preconditions:
        lines.extend(
            f"  {'Given' if index == 0 else 'And'} {condition}"
            for index, condition in enumerate(case.preconditions)
        )
    else:
        lines.append("  Given the feature preconditions are satisfied")
    for index, step in enumerate(case.steps):
        lines.append(f"  {'When' if index == 0 else 'And'} {step.action}")
        lines.append(f"  {'Then' if index == 0 else 'And'} {step.expected_result}")
    return "\n".join(lines)


def finalize_suite(suite: TestSuite, request: GenerateRequest) -> TestSuite:
    """Enforce quality guarantees on untrusted Copilot output."""
    unique_cases: list[TestCase] = []
    seen: set[tuple[str, str]] = set()
    for case in suite.test_cases:
        fingerprint = (case.title.casefold().strip(), case.objective.casefold().strip())
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        gherkin_text = case.gherkin.strip() if case.gherkin else ""
        if request.output_format == TestFormat.BDD:
            if not gherkin_text.startswith(("Scenario:", "Scenario Outline:")):
                gherkin_text = _gherkin_from_case(case)
            gherkin: str | None = gherkin_text
        else:
            gherkin = None
        unique_cases.append(case.model_copy(update={"gherkin": gherkin}))
    return suite.model_copy(
        update={
            "output_format": request.output_format,
            "test_cases": unique_cases[:5],
        }
    )


def user_prompt(
    request: GenerateRequest,
    phase: str = "initial",
    existing_titles: list[str] | None = None,
) -> str:
    target_instructions = {
        GenerationTarget.MANUAL: (
            "Generate only manual cases. Every execution_mode must be manual. Focus on genuinely "
            "human-dependent exploratory, usability, visual, accessibility-experience, subjective "
            "quality, physical, CAPTCHA, or biometric risks."
        ),
        GenerationTarget.AUTOMATION: (
            "Generate only automation cases. Every execution_mode must be automation. Focus on "
            "repeatable, deterministic scenarios observable through stable UI, API, or system "
            "interfaces and suitable for continuous execution."
        ),
        GenerationTarget.BOTH: (
            "Generate a balanced suite with at least 2 automation and 2 genuinely manual cases."
        ),
        GenerationTarget.AUTO: (
            "Generate a balanced suite with at least 2 automation and 2 genuinely manual cases."
        ),
    }
    format_instruction = (
        "Populate gherkin for every case with copy-ready SpecFlow syntax. Use Scenario for a "
        "single flow. Use Scenario Outline with <parameter> placeholders and an Examples table "
        "where multiple data rows, roles, boundary values, or outcomes should execute the same "
        "steps. Include concrete Given, When, Then, and optional And/But statements. Do not add "
        "Markdown fences or a Feature line. Keep structured steps for export compatibility."
        if request.output_format == TestFormat.BDD
        else "Use structured manual-test steps and set gherkin to null."
    )
    coverage_instruction = (
        "Generate 2 to 3 concise, high-level scenarios in one response. Prioritize the critical "
        "business path, one important negative case, and the highest risks. Use one or two short "
        "steps per scenario and keep every field brief. This is a proof of concept, so keep "
        "coverage selective rather than exhaustive."
        if phase == "initial"
        else "Generate the remaining distinct regression, boundary, permissions, state, recovery, "
        "accessibility, integration-failure, and risk-based pairwise coverage."
    )
    exclusions = "\n".join(f"- {title}" for title in (existing_titles or [])) or "None"
    schema = json.dumps(TestSuite.model_json_schema(), separators=(",", ":"))
    return f"""{coverage_instruction}

SPECIALIST ACTION
{target_instructions[request.generation_target]}

OUTPUT FORMAT
{format_instruction}

EXISTING SCENARIOS TO EXCLUDE
{exclusions}

SOURCE MATERIAL
{request.description}

ADDITIONAL CONTEXT
{request.additional_context or "None provided"}

REQUIRED JSON SCHEMA
{schema}"""


class GeneratorProvider(Protocol):
    async def generate(
        self,
        request: GenerateRequest,
        phase: str = "initial",
        existing_titles: list[str] | None = None,
    ) -> TestSuite: ...


class CopilotGenerator:
    """Generate test suites exclusively through the official GitHub Copilot SDK."""

    descriptor = AgentDescriptor(
        runtime_id="github-copilot",
        display_name="GitHub Copilot Test Designer",
        capabilities=frozenset(
            {
                AgentCapability.REQUIREMENT_TO_TEST_CASE,
                AgentCapability.TEST_DESIGN,
                AgentCapability.NORMAL_STEPS,
                AgentCapability.SPECFLOW_BDD,
                AgentCapability.STRUCTURED_OUTPUT,
            }
        ),
    )

    def __init__(
        self,
        settings: Settings,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory

    async def generate(
        self,
        request: GenerateRequest,
        phase: str = "initial",
        existing_titles: list[str] | None = None,
    ) -> TestSuite:
        try:
            from copilot import CopilotClient
            from copilot.session_events import AssistantMessageData, SessionIdleData
        except ImportError as error:
            raise CopilotGenerationError(
                "GitHub Copilot SDK is not installed. Run 'pip install -e .' and restart."
            ) from error

        factory = self.client_factory or CopilotClient
        client_options: dict[str, Any] = {
            "working_directory": str(self.settings.copilot_working_directory),
            "use_logged_in_user": not bool(self.settings.copilot_github_token),
            "mode": "copilot-cli",
        }
        if self.settings.copilot_github_token:
            client_options["github_token"] = self.settings.copilot_github_token

        content: str | None = None
        done = asyncio.Event()

        async with factory(**client_options) as client:
            session_options: dict[str, Any] = {
                "system_message": {"mode": "append", "content": SYSTEM_PROMPT},
                "streaming": False,
                "infinite_sessions": {"enabled": False},
                "available_tools": [],
                "skip_custom_instructions": True,
                "enable_config_discovery": False,
                "enable_skills": False,
                "enable_session_store": False,
                "memory": {"enabled": False},
                "enable_file_hooks": False,
                "enable_host_git_operations": False,
                "mcp_servers": {},
            }
            if self.settings.copilot_model:
                session_options["model"] = self.settings.copilot_model

            async with await client.create_session(**session_options) as session:

                def on_event(event: Any) -> None:
                    nonlocal content
                    if isinstance(event.data, AssistantMessageData):
                        content = event.data.content
                    elif isinstance(event.data, SessionIdleData):
                        done.set()

                session.on(on_event)
                await session.send(user_prompt(request, phase, existing_titles))
                try:
                    await asyncio.wait_for(done.wait(), self.settings.copilot_timeout_seconds)
                except TimeoutError as error:
                    raise CopilotGenerationError(
                        "GitHub Copilot generation timed out. Try again."
                    ) from error

        if not content:
            raise CopilotGenerationError("GitHub Copilot did not return a test suite.")
        try:
            return finalize_suite(TestSuite.model_validate_json(_json_object(content)), request)
        except (ValidationError, ValueError) as error:
            raise CopilotGenerationError(
                "GitHub Copilot returned output that did not match the test-suite schema."
            ) from error


def _json_object(content: str) -> str:
    """Accept a bare JSON object while tolerating an accidental Markdown fence."""
    value = content.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            value = "\n".join(lines[1:-1]).strip()
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end < start:
        raise ValueError("No JSON object found")
    return value[start : end + 1]


def create_generator(settings: Settings) -> GeneratorProvider:
    return CopilotGenerator(settings)


TestCaseGenerator = CopilotGenerator
