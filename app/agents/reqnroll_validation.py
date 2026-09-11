"""Reject incomplete C# artifacts before they reach previews or downloads.

This is a static completeness check, not a substitute for compiling the target project.
"""

import re
from typing import TYPE_CHECKING

from app.automation_style import step_style_findings

if TYPE_CHECKING:
    from app.agents.reqnroll_step_definition_agent import StepDefinitionArtifact

_PLACEHOLDER = re.compile(
    r"\b(?:NotImplementedException|PendingStepException|TODO|TBD)\b"
    r"|\b(?:ScenarioContext|Assert)\s*\.\s*(?:Pending|Ignore|Inconclusive)\s*\("
    r"|\.\s*Pending\s*\(",
    re.IGNORECASE,
)
# Preserve positions while hiding comments and literals from the brace/method scanner.
_NON_CODE = re.compile(
    r'@"(?:""|[^"])*"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    r"|//[^\n]*|/\*[\s\S]*?\*/"
)
_METHOD = re.compile(
    r"(?P<attributes>(?:\[[^\]]*\]\s*)*)"
    r"(?:public|internal|private|protected)\s+"
    r"(?:(?:static|async|virtual|override|sealed|new)\s+)*"
    r"[\w?.<>\[\],]+\s+(?P<name>@?\w+)\s*\([^)]*\)\s*(?P<start>\{|=>)"
)


def implementation_findings(
    artifact: "StepDefinitionArtifact", expected_steps: set[str] | None = None
) -> list[str]:
    findings: list[str] = []
    methods: dict[str, set[str]] = {}
    paths: set[str] = set()
    for file in artifact.files:
        if file.path in paths or any(part in {"", ".", ".."} for part in file.path.split("/")):
            findings.append(f"Unsafe or duplicate file path: {file.path}")
        paths.add(file.path)
        if not file.path.endswith(".cs"):
            continue
        findings.extend(step_style_findings(file.path, file.content))
        if _PLACEHOLDER.search(file.content):
            findings.append(
                f"{file.path}: replace placeholder or pending implementation with real code."
            )
        code = _NON_CODE.sub(lambda match: " " * len(match.group()), file.content)
        if re.search(
            r"\b(?:RestSharp|RestClient|RestRequest|WebClient|WebRequest|HttpWebRequest|"
            r"Flurl|IFlurlClient|IFlurlRequest|IAPIRequestContext|APIRequest)\b",
            code,
        ):
            findings.append(
                f"{file.path}: C# API handling must use System.Net.Http.HttpClient "
                "through a typed service; alternative HTTP clients are not allowed."
            )
        for match in _METHOD.finditer(code):
            name = match["name"].lstrip("@")
            kinds = set(re.findall(r"\[\s*(Given|When|Then)(?:Attribute)?\b", match["attributes"]))
            if kinds:
                methods.setdefault(name, set()).update(kinds)
            start = match.end()
            if match["start"] == "=>":
                end = code.find(";", start)
            else:
                depth, end = 1, start
                while end < len(code) and depth:
                    depth += (code[end] == "{") - (code[end] == "}")
                    end += 1
                if depth:
                    findings.append(f"{file.path}: unclosed method {name}.")
                end -= 1
            body = code[start:end].strip()
            if not body or _no_implementation(body):
                findings.append(f"{file.path}: {name} needs an executable implementation.")

    all_code = "\n".join(file.content for file in artifact.files)
    for helper in (
        "ApiScenario",
        "ApiClient",
        "ApiResponse",
        "ApprovedFixtures",
        "ApiClientFactory",
    ):
        if re.search(rf"\b{helper}\b", all_code) and not re.search(
            rf"\b(?:class|record|struct)\s+{helper}\b", all_code
        ):
            findings.append(f"Include the referenced supporting implementation: {helper}")

    coverage: dict[str, list[str]] = {}
    for item in artifact.coverage:
        coverage.setdefault(item.gherkin_step, []).append(item.binding)
        if item.status == "blocked":
            findings.append(f"Implementation required: {item.gherkin_step}")
        name = item.binding.split("(", 1)[0].rsplit(".", 1)[-1]
        kind = item.gherkin_step.split(" ", 1)[0]
        if kind not in methods.get(name, set()):
            findings.append(f"No {kind} binding implementation for: {item.gherkin_step}")
    for step, bindings in coverage.items():
        if len(bindings) != 1:
            findings.append(f"Duplicate coverage mapping: {step}")
    if expected_steps is not None:
        for step in sorted(expected_steps - coverage.keys()):
            findings.append(f"Missing step coverage: {step}")
        for step in sorted(coverage.keys() - expected_steps):
            findings.append(f"Coverage references a step outside the approved suite: {step}")
        if not expected_steps:
            findings.append("The approved suite contains no executable Gherkin steps.")
    return list(dict.fromkeys(findings))


def _no_implementation(body: str) -> bool:
    """Catch empty, unconditional-throw and common fake-success method bodies."""
    compact = re.sub(r"\s+", "", body).rstrip(";")
    if compact in {
        "return",
        "returnTask.CompletedTask",
        "Task.CompletedTask",
        "awaitTask.CompletedTask",
        "returntrue",
        "true",
    }:
        return True
    if re.fullmatch(r"(?:return)?(?:System\.)?Threading\.Tasks\.Task\.CompletedTask", compact):
        return True
    if re.fullmatch(r"(?:return)?Task\.(?:FromResult\(.*\)|Delay\(.*\))", compact):
        return True
    if re.fullmatch(r"throw\s+[^;]+;?", body):
        return True
    if re.fullmatch(r"(?:Assert\.(?:Pass\([^)]*\)|True\(true\)|IsTrue\(true\)));?", compact):
        return True
    return False
