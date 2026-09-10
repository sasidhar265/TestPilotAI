"""Language routing and BDD artifact generation through the configured provider runtime."""

import ast
import json
import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field

from app.agents import AgentKind, FunctionalAgentDescriptor
from app.agents.artifact_runner import ArtifactGenerationRunner
from app.agents.context_converter_agent import ContextConverterAgent
from app.agents.reqnroll_step_definition_agent import (
    ReqnRollStepDefinitionAgent,
    StepCoverage,
    StepDefinitionRequest,
    _binding_pattern,
)
from app.agents.runner import StructuredAgentDefinition
from app.config import Settings
from app.models import ExecutionMode
from app.workspace_policy import standards

Language = Literal["csharp", "java", "python", "javascript", "typescript", "ruby"]
LANGUAGES = {
    "csharp": ("C#", "ReqnRoll", "cs"),
    "java": ("Java", "Cucumber-JVM", "java"),
    "python": ("Python", "Behave", "py"),
    "javascript": ("JavaScript", "Cucumber-JS", "js"),
    "typescript": ("TypeScript", "Cucumber-JS", "ts"),
    "ruby": ("Ruby", "Cucumber-Ruby", "rb"),
}


class LanguageRequest(StepDefinitionRequest):
    language: Language = "csharp"


class ArtifactFile(BaseModel):
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=500_000)


class LanguageArtifact(BaseModel):
    language: Language
    framework: str
    files: list[ArtifactFile] = Field(min_length=1, max_length=100)
    coverage: list[StepCoverage] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def safe_files(artifact: LanguageArtifact) -> None:
    seen = set()
    allowed = {"cs", "java", "py", "js", "ts", "rb", "json", "xml", "md", "txt", "feature", "toml"}
    for file in artifact.files:
        path = PurePosixPath(file.path)
        if (
            not re.fullmatch(r"[A-Za-z0-9_./-]+", file.path)
            or any(p in {"", ".", ".."} for p in file.path.split("/"))
            or path.is_absolute()
            or file.path.casefold() in seen
            or (path.suffix.lstrip(".") not in allowed and path.name != "Gemfile")
        ):
            raise ValueError("Unsafe, duplicate or unsupported artifact file path")
        seen.add(file.path.casefold())


class MultiLanguageAgent:
    descriptor = FunctionalAgentDescriptor(
        id="multi-language-agent",
        name="Multi Language Support Agent",
        kind=AgentKind.AUTOMATION_GENERATOR,
        runtime="language-adapters-and-configured-providers",
        purpose="Generate BDD bindings and implementation packs in the selected language.",
        capabilities=("csharp", "java", "python", "javascript", "typescript", "ruby"),
        instruction_file=".github/agents/multi-language.agent.md",
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def bindings(self, request: LanguageRequest) -> LanguageArtifact:
        if not request.validation.passed:
            raise ValueError("Step definitions require a Quality Gate-approved suite.")
        standards("automation")  # Read shared policy for each generation; no stale cached policy.
        if request.language == "csharp":
            artifact = ReqnRollStepDefinitionAgent(self.settings).generate_bindings(request)
            return LanguageArtifact(**(artifact.model_dump() | {"language": "csharp"}))
        bodies: list[str] = []
        coverage: list[StepCoverage] = []
        seen: dict[str, str] = {}
        for case in request.suite.test_cases:
            if case.execution_mode != ExecutionMode.AUTOMATION:
                continue
            keyword = "Given"
            for line in (case.gherkin or "").splitlines():
                match = re.match(r"^\s*(Given|When|Then|And|But)\s+(.+)$", line)
                if not match:
                    continue
                current, text = match.groups()
                keyword = current if current not in {"And", "But"} else keyword
                pattern, parameters = _binding_pattern(text)
                # Cucumber matches step text independent of Given/When/Then; deduplicate globally.
                if pattern not in seen:
                    name = f"step_{len(seen) + 1}"
                    seen[pattern] = name
                    args = [f"arg{i}" for i in range(1, len(parameters) + 1)]
                    bodies.append(_declaration(request.language, keyword, pattern, name, args))
                coverage.append(
                    StepCoverage(
                        gherkin_step=f"{keyword} {text}", status="blocked", binding=seen[pattern]
                    )
                )
        if not bodies:
            raise ValueError("The suite contains no automation Gherkin steps")
        headers = {
            "python": (
                "from behave import given, when, then, use_step_matcher\n\n"
                'use_step_matcher("re")\n\n'
            ),
            "java": "package generated;\n\nimport io.cucumber.java.en.*;\n\npublic class Steps {\n",
            "javascript": "const { Given, When, Then } = require('@cucumber/cucumber');\n\n",
            "typescript": "import { Given, When, Then } from '@cucumber/cucumber';\n\n",
            "ruby": "# Cucumber step definitions\n\n",
        }
        suffix = LANGUAGES[request.language][2]
        paths = {"java": "src/test/java/generated/Steps.java"}
        content = headers[request.language] + "\n\n".join(bodies) + "\n"
        if request.language == "java":
            content += "}\n"
        return LanguageArtifact(
            language=request.language,
            framework=LANGUAGES[request.language][1],
            files=[
                ArtifactFile(
                    path=paths.get(request.language, f"features/steps/steps.{suffix}"),
                    content=content,
                )
            ],
            coverage=coverage,
            notes=[
                "Bindings only: implement the pending steps before execution.",
                "Shared conventions: workspace/automation-standards.md. "
                "Language adapters provide standard declarations; custom implementation "
                "conventions are supplied to full-pack generation.",
            ],
        )

    async def generate(self, request: LanguageRequest) -> LanguageArtifact:
        baseline = self.bindings(request)
        if request.language == "csharp":
            result = await ReqnRollStepDefinitionAgent(self.settings).generate(request)
            artifact = LanguageArtifact(**(result.model_dump() | {"language": "csharp"}))
            artifact.files.append(
                ArtifactFile(
                    path="features/generated.feature",
                    content=ContextConverterAgent()._feature(request.suite).decode(),
                )
            )
            return artifact
        instructions = (
            "Generate a complete BDD automation implementation pack as JSON. "
            "Implement every baseline binding, preserving its method name and regex. "
            "Do not invent API contracts, selectors or business behavior; report missing contracts "
            "instead of inventing implementations. Include dependency manifest, "
            "runner configuration "
            "and README.md with setup and execution commands. Never execute generated code.\n"
            + standards("automation")
            + "\n"
            + standards("feature")
        )
        definition = StructuredAgentDefinition(
            output_model=LanguageArtifact,
            timeout_error="Automation pack generation timed out.",
            empty_error="No automation files returned.",
            invalid_error="Invalid automation pack.",
        )
        return await ArtifactGenerationRunner(self.settings).generate_structured(
            definition,
            instructions=instructions,
            prompt=json.dumps(
                {
                    "language": request.language,
                    "framework": baseline.framework,
                    "suite": request.suite.model_dump(mode="json"),
                    "bindings": baseline.model_dump(mode="json"),
                }
            ),
            validate=lambda artifact: validate_pack(artifact, request, baseline),
        )


def _declaration(language: str, keyword: str, pattern: str, name: str, args: list[str]) -> str:
    if language == "python":
        # Behave's regex matcher passes named groups as keyword arguments.
        # Rebuild positional capture groups without changing escaped literal parentheses.
        index = iter(args)
        pattern = re.sub(r"(?<!\\)\((?!\?)", lambda _: f"(?P<{next(index)}>", pattern)
        return (
            f"@{keyword.lower()}({pattern[1:-1]!r})\n"
            f"def {name}({', '.join(['context', *args])}):\n"
            '    raise NotImplementedError("Implement this step")'
        )
    if language == "java":
        return (
            f"    @{keyword}({json.dumps(pattern)})\n"
            f"    public void {name}({', '.join('String ' + a for a in args)}) {{\n"
            "        throw new io.cucumber.java.PendingException();\n    }"
        )
    if language in {"javascript", "typescript"}:
        arguments = ", ".join(a + (": string" if language == "typescript" else "") for a in args)
        return (
            f"{keyword}(new RegExp({json.dumps(pattern)}), async function {name}({arguments}) {{\n"
            "    return 'pending';\n});"
        )
    ruby_pattern = json.dumps(pattern).replace("#{", r"\#{")
    return (
        f"{keyword}(Regexp.new({ruby_pattern})) do |{', '.join(args)}|\n"
        f"  # {name}\n  pending 'Implement this step'\nend"
    )


def validate_pack(
    artifact: LanguageArtifact, request: LanguageRequest, baseline: LanguageArtifact
) -> LanguageArtifact:
    safe_files(artifact)
    if artifact.language != request.language or artifact.framework != baseline.framework:
        raise ValueError("Pack language/framework does not match the selected language")
    extension = "." + LANGUAGES[request.language][2]
    code = "\n".join(f.content for f in artifact.files if f.path.endswith(extension))
    if not code or re.search(
        r"NotImplementedError|PendingException|\bpending\b|\bTODO\b|\bFIXME\b|"
        r"throw new Error\([\"']Implement|raise NotImplemented|\bpass\s*$",
        code,
        re.M | re.I,
    ):
        raise ValueError("Full packs require concrete code without pending/placeholder steps")
    expected = {c.gherkin_step for c in baseline.coverage}
    if {c.gherkin_step for c in artifact.coverage} != expected or any(
        c.status == "blocked" for c in artifact.coverage
    ):
        raise ValueError("Pack must map every approved Gherkin step to an implementation")
    for mapping in baseline.coverage:
        if mapping.binding not in code:
            raise ValueError("Pack must preserve every baseline binding")
    registrations = [
        line.strip()
        for file in baseline.files
        for line in file.content.splitlines()
        if re.match(
            r"^\s*(?:@(?:given|when|then|Given|When|Then)\(|"
            r"(?:Given|When|Then)\()",
            line,
        )
    ]
    if any(line not in code for line in registrations):
        raise ValueError("Pack must preserve the baseline step registrations and patterns")
    required = {
        "java": "pom.xml",
        "python": "requirements.txt",
        "javascript": "package.json",
        "typescript": "package.json",
        "ruby": "Gemfile",
    }
    if not any(f.path == required[request.language] for f in artifact.files):
        raise ValueError("Pack must include its dependency manifest: " + required[request.language])
    for file in artifact.files:
        if file.path.endswith(".json"):
            try:
                json.loads(file.content)
            except ValueError as error:
                raise ValueError("Pack contains invalid JSON configuration") from error
    if request.language == "typescript" and not any(
        f.path == "tsconfig.json" for f in artifact.files
    ):
        raise ValueError("TypeScript pack must include tsconfig.json")
    if request.language == "python":
        for file in artifact.files:
            if file.path.endswith(".py"):
                try:
                    tree = ast.parse(file.content)
                    for node in ast.walk(tree):
                        if isinstance(
                            node, (ast.FunctionDef, ast.AsyncFunctionDef)
                        ) and node.name in {item.binding for item in baseline.coverage}:
                            body = [
                                n
                                for n in node.body
                                if not isinstance(n, ast.Expr)
                                or not isinstance(n.value, ast.Constant)
                            ]
                            if not body or all(isinstance(n, (ast.Raise, ast.Pass)) for n in body):
                                raise ValueError(
                                    "Step implementations cannot be empty or throw-only"
                                )
                except SyntaxError as error:
                    raise ValueError("Generated Python has invalid syntax") from error
    if not any(f.path == "README.md" for f in artifact.files):
        raise ValueError("Pack must include README.md with setup and execution instructions")
    # Always supply the feature from the deterministic converter, never AI-authored tags/content.
    feature = ContextConverterAgent()._feature(request.suite).decode()
    artifact.files = [f for f in artifact.files if not f.path.endswith(".feature")]
    artifact.files.append(ArtifactFile(path="features/generated.feature", content=feature))
    artifact.notes.append("Static checks passed; compilation and live execution have not been run.")
    return artifact
