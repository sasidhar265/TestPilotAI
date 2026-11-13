"""Direct framework routing is separate from the business requirement approval gate."""

import base64
import io
import json
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import GenerateRequest
from app.services.website_framework import framework_target
from app.services.website_inspection import WebsiteInspection, WebsiteInspectionService, WebsitePage

PROMPT = (
    "Consider you're a senior C# automation tester and build a C# automation framework "
    "for this 'https://careerpilot-nrn7.onrender.com' to evaluate its functionalities, "
    "and segregate the regression, sanity & smoke tests as well. "
    "Build the framework using Selenium, C#, and BDD in a page object model."
)


def test_agent_route_builds_framework_without_business_gate(monkeypatch):
    async def inspect(self, request, settings):
        return WebsiteInspection(
            pages=[
                WebsitePage(
                    url=request.url,
                    title="Careers",
                    headings=["Find work"],
                    controls=[{"selector": 'input[id="search"]'}],
                    links=[],
                )
            ],
            warnings=["HTML inspection only."],
            description="Observed public Careers page.",
        )

    monkeypatch.setattr(WebsiteInspectionService, "inspect", inspect)
    with TestClient(app) as client:
        response = client.post("/api/agent/run", json={"description": PROMPT})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["workflow"] == "website-framework"
    assert result["execution_status"] == "not_run"
    assert result["language"] == "csharp"
    assert result["framework"] == "ReqnRoll"
    assert result["design_pattern"] == "Page Object Model + PageFactory"
    assert result["automation_tool"] == "Selenium"
    assert result["target_framework"] == "net10.0"
    assert any(
        file["path"] == "Pages/HomePage.cs" and "class HomePage" in file["content"]
        for file in result["files"]
    )
    assert result["original_prompt"] == PROMPT
    assert result["scenario_counts"] == {"smoke": 1, "sanity": 1, "regression": 2}
    with ZipFile(io.BytesIO(base64.b64decode(result["archive_base64"]))) as archive:
        names = archive.namelist()
        assert "Pages/HomePage.cs" in names
        assert "StepDefinitions/WebsiteStepDefinition.cs" in names
        assert "Features/Smoke/Smoke.feature" in names
        assert "Features/Sanity/Sanity.feature" in names
        assert "Features/Regression/Regression.feature" in names
        assert "Selenium.WebDriver" in archive.read("Automation.csproj").decode()
        assert "DotNetSeleniumExtras.PageObjects.Core" in archive.read("Automation.csproj").decode()
        assert "[FindsBy" in archive.read("Pages/HomePage.cs").decode()
        assert (
            "PageFactory.InitElements(driver, page)"
            in archive.read("Services/PageCatalogService.cs").decode()
        )
        assert "CacheLookup" not in archive.read("Pages/HomePage.cs").decode()
        cases = json.loads(archive.read("Input/CaseData.Json"))
        assert any(case["kind"] == "control" for case in cases)
        assert json.dumps('input[id="search"]') in archive.read("Pages/HomePage.cs").decode()
        assert 'Category("Smoke")' in archive.read("Reqnroll/TestCategories.cs").decode()
        assert len(result["test_suites"]) == 3
        assert result["page_objects"] == ["Pages/HomePage.cs"]
        assert "Selenium" in archive.read("Input/Request.Json").decode()


@pytest.mark.parametrize(
    "description",
    [
        "Verify help opens https://example.com in a new tab.",
        "Generate test cases for the approved interest rate requirement.",
    ],
)
def test_ordinary_requirements_keep_business_workflow(description):
    assert framework_target(GenerateRequest(description=description)) is None


def test_uploaded_document_keeps_business_workflow():
    assert (
        framework_target(GenerateRequest(description=PROMPT, uploaded_brd_text="Readable document"))
        is None
    )


@pytest.mark.parametrize(
    "description,reason",
    [
        ("Build a framework for https://example.com and https://example.org", "one target"),
        ("Build a Playwright framework for https://example.com", "currently support Selenium"),
        ("Build a framework for https://user:secret@example.com", "without credentials"),
        ("Build a framework for http://127.0.0.1", "public internet"),
    ],
)
def test_agent_framework_rejects_invalid_targets(description, reason):
    with TestClient(app) as client:
        response = client.post("/api/agent/run", json={"description": description})
    assert response.status_code == 422, response.text
    assert reason in response.text


def test_named_page_actions_and_read_only_suites_come_from_published_evidence():
    from app.services.website_framework_assets import page_assets

    inspection = WebsiteInspection(
        pages=[
            WebsitePage(
                url="https://example.com/",
                title="Careers",
                headings=["Find work"],
                controls=[
                    {
                        "tag": "select",
                        "aria-label": "Appearance",
                        "selector": 'select[aria-label="Appearance"]',
                        "options_json": json.dumps(
                            [
                                {"text": "Light mode", "value": "light", "disabled": False},
                                {"text": "Dark mode", "value": "dark", "disabled": True},
                            ]
                        ),
                    }
                ],
                links=[{"url": "https://example.com/guide", "text": "User guide"}],
            ),
            WebsitePage(
                url="https://example.com/guide",
                title="User guide",
                headings=[],
                controls=[],
                links=[],
            ),
        ],
        warnings=[],
        description="Observed Careers and guide pages.",
    )
    files, cases = page_assets(inspection)
    assert "class HomePage" in files["Pages/HomePage.cs"]
    assert "[FindsBy" in files["Pages/HomePage.cs"]
    assert "IWebElement" in files["Pages/HomePage.cs"]
    assert "Func<IWebElement>" in files["Pages/HomePage.cs"]
    assert "class GuidePage" in files["Pages/GuidePage.cs"]
    assert "OpenUserGuide1" in files["Pages/HomePage.cs"]
    assert "NavigationActions" in files["Pages/HomePage.cs"]
    assert sum(case["kind"] == "navigation" for case in cases) == 1
    assert [case["expected"] for case in cases if case["kind"] == "selection"] == ["Light mode"]
    assert any(case["kind"] == "options" for case in cases)
    assert all(
        not line.startswith("@")
        for path, text in files.items()
        if path.endswith(".feature")
        for line in text.splitlines()
    )
