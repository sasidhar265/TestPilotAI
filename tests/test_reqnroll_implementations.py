import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.agents.reqnroll_implementations import common_step, support_files
from app.agents.reqnroll_step_definition_agent import ReqnRollStepDefinitionAgent
from app.models import TestCase as Case
from app.models import TestDatum as Datum
from app.models import TestStep as Step


def api_case(gherkin: str, data: list[Datum] | None = None) -> Case:
    return Case(
        id="TC-001",
        title="API request",
        objective="Validate API response",
        category="smoke",
        priority="P1",
        execution_mode="automation",
        feasibility_reason="Known API contract",
        gherkin=gherkin,
        steps=[Step(action="Send request", expected_result="Expected status and fields")],
        test_data=data or [],
    )


ELIGIBILITY_STEP = "fixture <fixture> sets <customerType> and <productType> as <eligibility>"


@pytest.mark.parametrize(
    "text,values",
    [
        (ELIGIBILITY_STEP, ("<fixture>", "<customerType>", "<productType>", "<eligibility>")),
        (
            "fixture catalogue sets limited company and HP as eligible",
            ("catalogue", "limited company", "HP", "eligible"),
        ),
        (
            'fixture "catalogue" sets "limited company" and "HP" as "ineligible"',
            ('"catalogue"', '"limited company"', '"HP"', '"ineligible"'),
        ),
    ],
)
def test_eligibility_step_has_four_reusable_parameters(text, values) -> None:
    pattern, parameters, body, asynchronous = common_step("Given", text)
    assert re.fullmatch(pattern, text).groups() == values
    assert [name for _, name in parameters] == [
        "fixture",
        "customerType",
        "productType",
        "eligibility",
    ]
    assert "LoadEligibilityFixture" in body
    assert not asynchronous
    assert re.fullmatch(pattern, "unrelated " + text) is None


def test_reported_eligibility_step_generates_code_instead_of_blocked_stub() -> None:
    cases = [
        api_case("Scenario: Eligibility\n Given " + step)
        for step in [
            ELIGIBILITY_STEP,
            "fixture catalogue sets private individual and PCP as eligible",
            'fixture "catalogue" sets "private individual" and "PCP" as "eligible"',
        ]
    ]
    artifact = ReqnRollStepDefinitionAgent._fallback_artifact("API", cases)
    assert "NotImplementedException" not in artifact.files[0].content
    assert artifact.files[0].content.count("[Given(") == 1
    assert "api.LoadEligibilityFixture(" in artifact.files[0].content
    assert [item.status for item in artifact.coverage] == ["generated", "reused", "reused"]
    assert len({item.binding for item in artifact.coverage}) == 1


def test_outline_and_literal_steps_share_implemented_bindings() -> None:
    cases = [
        api_case(
            'Scenario Outline: Request\n  Given a request built from "<fixture>"\n'
            '  When I send a "POST" request to "/quotes"\n'
            "  Then the response status is <status>\n\n"
            "Examples:\n  | fixture | status |\n  | valid | 201 |\n  | invalid | 400 |"
        ),
        api_case(
            'Scenario: Request\n  Given a request built from "valid"\n'
            '  When I send a "POST" request to "/quotes"\n'
            "  Then the response status is 201"
        ),
    ]
    artifact = ReqnRollStepDefinitionAgent._fallback_artifact("API", cases)
    content = artifact.files[0].content
    assert "NotImplementedException" not in content
    assert content.count("[Given(") == 1
    assert content.count("[Then(") == 1
    assert "int expectedStatus" in content
    assert "await api.SendAsync(method, path)" in content
    assert {entry.status for entry in artifact.coverage} == {"generated", "reused"}
    assert len(artifact.files) == 9


@pytest.mark.parametrize(
    "kind,source,expanded",
    [
        ("Given", 'a request built from "<fixture>"', 'a request built from ""'),
        ("Then", "the response status is <status>", "the response status is 400"),
        (
            "Then",
            'the response decimal field "<field>" equals <amount>',
            'the response decimal field "total" equals -12.34',
        ),
        (
            "Then",
            'the response JSON field "<field>" equals "<value>"',
            'the response JSON field "code" equals "INVALID"',
        ),
    ],
)
def test_common_patterns_match_expanded_values(kind, source, expanded) -> None:
    pattern, parameters, _, _ = common_step(kind, source)
    match = re.fullmatch(pattern, expanded)
    assert match is not None
    assert len(match.groups()) == len(parameters)
    assert re.fullmatch(pattern, expanded + " extra") is None


def test_unknown_domain_behavior_remains_blocked() -> None:
    artifact = ReqnRollStepDefinitionAgent._fallback_artifact(
        "API",
        [
            api_case(
                'Scenario: Calculation\n  Given a request built from "valid"\n'
                "  When the request is submitted\n  Then the APR is correct"
            )
        ],
    )
    assert [entry.status for entry in artifact.coverage] == ["generated", "generated", "blocked"]


def test_only_unambiguous_supplied_json_is_embedded() -> None:
    files = support_files(
        [
            api_case(
                "",
                [
                    Datum(name="valid", value='{"amount":"12.30"}', purpose="request"),
                    Datum(name="conflict", value='{"a":1}', purpose="request"),
                    Datum(name="conflict", value='{"a":2}', purpose="request"),
                    Datum(name="description", value="not JSON", purpose="context"),
                ],
            )
        ]
    )
    fixture_source = files[1][1]
    assert '""amount"":""12.30""' in fixture_source
    assert "conflict" not in fixture_source
    assert "description" not in fixture_source


def test_fixture_numbers_keep_exact_decimal_precision() -> None:
    files = support_files(
        [
            api_case(
                "",
                [
                    Datum(
                        name="precise",
                        value='{"amount":123456789.123456789123456789}',
                        purpose="request",
                    ),
                    Datum(name="invalid", value='{"amount":NaN}', purpose="request"),
                ],
            )
        ]
    )
    assert "123456789.123456789123456789" in files[1][1]
    assert "NaN" not in files[1][1]


@pytest.mark.skipif(
    os.environ.get("RUN_CSHARP_TESTS") != "1" or shutil.which("dotnet") is None,
    reason="Set RUN_CSHARP_TESTS=1 with .NET 8+ installed to compile and execute generated C#.",
)
def test_generated_csharp_compiles_and_executes(tmp_path) -> None:
    case = api_case(
        'Scenario Outline: API\n Given a request built from "<fixture>"\n'
        ' When I send a "POST" request to "/quotes"\n'
        " Then the response status is <status>\n"
        ' And the response JSON field "quote.id" equals "q-1"\n'
        ' And the response JSON field "quote.id" is present\n'
        ' And the response decimal field "quote.total" equals 12.30\n',
        [Datum(name="valid", value='{"amount":"12.30"}', purpose="request")],
    )
    for source in (Path(__file__).parent / "csharp").iterdir():
        if source.is_file():
            shutil.copy(source, tmp_path / source.name)
    row = {
        "customerType": "private individual",
        "productType": "PCP",
        "eligibility": "eligible",
        "request": {"customerType": "private individual", "productType": "PCP", "amount": "12.30"},
    }
    negative = {
        "customerType": "limited company",
        "productType": "HP",
        "eligibility": "ineligible",
        "request": {"customerType": "limited company", "productType": "HP", "amount": "15.60"},
    }
    inconsistent = {**row, "request": {**row["request"], "productType": "HP"}}
    eligibility = api_case(
        "Scenario: Eligibility\n Given " + ELIGIBILITY_STEP,
        [
            Datum(
                name="catalogue",
                value=json.dumps({"eligibilityCases": [row, negative]}),
                purpose="approved eligibility requests",
            ),
            Datum(
                name="duplicate",
                value=json.dumps({"eligibilityCases": [row, row]}),
                purpose="duplicate fixture regression",
            ),
            Datum(
                name="inconsistent",
                value=json.dumps({"eligibilityCases": [inconsistent]}),
                purpose="inconsistent fixture regression",
            ),
        ],
    )
    artifact = ReqnRollStepDefinitionAgent._fallback_artifact("API", [case, eligibility])
    input_directory = tmp_path / "Input"
    input_directory.mkdir()
    shutil.copy(
        Path(__file__).parents[1] / "app/templates/framework/QuotationRequest.Json",
        input_directory / "QuotationRequest.Json",
    )
    for file in artifact.files:
        target = tmp_path / file.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file.content, encoding="utf-8")
    result = subprocess.run(
        [
            "dotnet",
            "run",
            "--project",
            str(tmp_path / "GeneratedBindings.csproj"),
            "-p:NuGetAudit=false",
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Generated C# runtime checks passed." in result.stdout
