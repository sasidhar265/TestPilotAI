"""Route explicit website framework requests to evidence-derived Selenium packs."""

import base64
import io
import json
import re
from pathlib import Path
from typing import Literal
from zipfile import ZIP_DEFLATED, ZipFile

from pydantic import BaseModel, Field

from app.automation_layout import folder_notes, validate_layout_paths
from app.config import Settings
from app.models import GenerateRequest
from app.observability import publish_lifecycle_event
from app.services.website_framework_assets import SUITES, page_assets
from app.services.website_inspection import (
    WebsiteInspectionError,
    WebsiteInspectionService,
    WebsiteRequest,
    normalize_url,
)

TEMPLATES = Path(__file__).parents[1] / "templates" / "website_framework"


def framework_target(request: GenerateRequest) -> str | None:
    """Do not route ordinary requirements, uploaded BRDs or incidental links."""
    text = request.description
    if request.uploaded_brd_text or request.uploaded_brd_receipt:
        return None
    if not re.search(r"\b(build|create|generate|set\s+up|scaffold)\b", text, re.I):
        return None
    if not re.search(r"\b(automation|framework|selenium|playwright)\b", text, re.I):
        return None
    return website_target(text)


def website_target(text: str) -> str:
    """Validate a semantically selected target without requiring imperative keywords."""
    urls = list(
        dict.fromkeys(
            url.rstrip("),.;!?") for url in re.findall(r"""https?://[^\s<>"']+""", text, re.I)
        )
    )
    if not urls:
        raise WebsiteInspectionError("Supply a public website URL for the framework.")
    if len(urls) != 1:
        raise WebsiteInspectionError("Use one target website per framework request.")
    if re.search(r"\b(playwright|java|python|typescript|javascript|cypress)\b", text, re.I):
        raise WebsiteInspectionError(
            "Direct website frameworks currently support Selenium, C# and ReqnRoll BDD. "
            "Specify that stack, or use the existing reviewed test-design workflow."
        )
    return normalize_url(urls[0])


class FrameworkFile(BaseModel):
    path: str
    content: str


class FrameworkSuite(BaseModel):
    name: str
    feature_file: str
    scenario_count: int
    scenarios: list[str]
    command: str


class WebsiteFrameworkResult(BaseModel):
    workflow: Literal["website-framework"] = "website-framework"
    target_url: str
    stack: str = "Selenium / C# / ReqnRoll BDD / POM + PageFactory"
    original_prompt: str
    scenario_counts: dict[str, int]
    observations: str
    limitations: list[str]
    execution_status: Literal["not_run"] = "not_run"
    language: Literal["csharp"] = "csharp"
    framework: Literal["ReqnRoll"] = "ReqnRoll"
    automation_tool: Literal["Selenium"] = "Selenium"
    design_pattern: str = "Page Object Model + PageFactory"
    target_framework: str = "net10.0"
    files: list[FrameworkFile] = Field(default_factory=list)
    page_objects: list[str] = Field(default_factory=list)
    test_suites: list[FrameworkSuite] = Field(default_factory=list)
    file_names: list[str]
    archive_base64: str
    filename: str = "website-automation.zip"


async def build_website_framework(
    request: GenerateRequest, target: str, settings: Settings
) -> WebsiteFrameworkResult:
    publish_lifecycle_event(
        "Website Framework Agent",
        "discovery",
        "running",
        "Inspecting public website evidence for a Selenium/C#/BDD page object pack.",
    )
    inspection = await WebsiteInspectionService().inspect(
        WebsiteRequest(url=target, max_pages=5), settings
    )
    if not inspection.pages:
        raise WebsiteInspectionError(
            "No public HTML pages were available for framework generation."
        )
    generated_files, cases = page_assets(inspection)
    limitations = [
        *inspection.warnings,
        "Checks cover observed public page contracts and published navigation; "
        "business-rule approval and full functional coverage are not established.",
        "Login, form submission and JavaScript-only journeys need credentials "
        "and expected behavior.",
        "Generated checks have not been executed. Review the evidence and code before running.",
        "Selectors and titles are snapshots and may change. "
        "No external AI calls were needed for this pack.",
    ]
    counts = {
        category: sum(c["category"] == category for c in cases)
        for category in ("smoke", "sanity", "regression")
    }
    files = folder_notes()
    for path in TEMPLATES.rglob("*"):
        if path.is_file():
            files[path.relative_to(TEMPLATES).as_posix()] = path.read_text()
    files.update(generated_files)
    files[".gitignore"] = "bin/\nobj/\nTestResults/Reports/*\n!TestResults/Reports/README.md\n"
    files["Input/CaseData.Json"] = json.dumps(cases, ensure_ascii=False, indent=2)
    from urllib.parse import urlsplit

    origin = urlsplit(inspection.pages[0].url)
    files["Input/TestData.Json"] = json.dumps(
        {
            "baseUrl": f"{origin.scheme}://{origin.netloc}/",
            "browser": "chrome",
            "headless": True,
            "waitTimeoutSeconds": 15,
            "pageLoadTimeoutSeconds": 45,
            "commandTimeoutSeconds": 60,
            "windowWidth": 1440,
            "windowHeight": 1000,
        },
        indent=2,
    )
    files["Input/Discovery.Json"] = inspection.model_dump_json(indent=2)
    files["Input/Request.Json"] = json.dumps(
        {"prompt": request.description, "limitations": limitations}, indent=2
    )
    files["README.md"] += "\n\n## Discovery limitations\n\n" + "\n".join(
        f"- {x}" for x in limitations
    )
    files["README.md"] += "\n\nScenario counts: " + json.dumps(counts) + ".\n"
    validate_layout_paths(files)
    archive = io.BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        for name, content in files.items():
            output.writestr(name, content)
    publish_lifecycle_event(
        "Website Framework Agent",
        "framework_assembly",
        "success",
        f"Prepared {len(cases)} observed-page scenarios. Execution not performed.",
    )
    suites = [
        FrameworkSuite(
            name=directory,
            feature_file=f"Features/{directory}/{directory}.feature",
            scenario_count=counts[category],
            scenarios=[
                f"{case['id']} - {case['title']}" for case in cases if case["category"] == category
            ],
            command=f"dotnet test Automation.csproj --filter TestCategory={directory}",
        )
        for category, (_, directory) in SUITES.items()
    ]
    return WebsiteFrameworkResult(
        target_url=target,
        original_prompt=request.description,
        scenario_counts=counts,
        observations=inspection.description,
        limitations=limitations,
        files=[
            FrameworkFile(path=path, content=content) for path, content in sorted(files.items())
        ],
        page_objects=sorted(
            path for path in generated_files if path.startswith("Pages/") and path.endswith(".cs")
        ),
        test_suites=suites,
        file_names=sorted(files),
        archive_base64=base64.b64encode(archive.getvalue()).decode(),
    )
