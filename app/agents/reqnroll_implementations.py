"""Conservative implementations for an explicit vocabulary of common API steps."""

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

_STRING = r'"(?:[^"<>]*|<[A-Za-z_][A-Za-z0-9_]*>)"'
_INT = r"(?:\d+|<[A-Za-z_][A-Za-z0-9_]*>)"
_DECIMAL = r"(?:-?\d+(?:\.\d+)?|<[A-Za-z_][A-Za-z0-9_]*>)"
_LABEL = r'(?:"[^"\r\n]+"|[^"\r\n]+?)'
_LABEL_CAPTURE = r'("[^"\r\n]+"|[^"\r\n]+?)'

# kind, source text matcher, runtime binding regex, typed arguments, body, async
COMMON_STEPS = [
    (
        "Given",
        rf"fixture {_LABEL} sets {_LABEL} and {_LABEL} as {_LABEL}",
        rf"fixture {_LABEL_CAPTURE} sets {_LABEL_CAPTURE} "
        rf"and {_LABEL_CAPTURE} as {_LABEL_CAPTURE}",
        [
            ("string", "fixture"),
            ("string", "customerType"),
            ("string", "productType"),
            ("string", "eligibility"),
        ],
        "api.LoadEligibilityFixture(fixture.Trim('\"'), customerType.Trim('\"'), "
        "productType.Trim('\"'), eligibility.Trim('\"'));",
        False,
    ),
    (
        "Given",
        rf"a request built from {_STRING}",
        r'a request built from "([^"]*)"',
        [("string", "fixture")],
        "api.LoadFixture(fixture);",
        False,
    ),
    (
        "When",
        r"the request is submitted",
        r"the request is submitted",
        [],
        "await api.SubmitConfiguredAsync();",
        True,
    ),
    (
        "When",
        rf"I send a {_STRING} request to {_STRING}",
        r'I send a "([^"]*)" request to "([^"]*)"',
        [("string", "method"), ("string", "path")],
        "await api.SendAsync(method, path);",
        True,
    ),
    (
        "Then",
        rf"the response status is {_INT}",
        r"the response status is (\d+)",
        [("int", "expectedStatus")],
        "api.AssertStatus(expectedStatus);",
        False,
    ),
    (
        "Then",
        rf"the response JSON field {_STRING} equals {_STRING}",
        r'the response JSON field "([^"]*)" equals "([^"]*)"',
        [("string", "field"), ("string", "expected")],
        "api.AssertField(field, expected);",
        False,
    ),
    (
        "Then",
        rf"the response JSON field {_STRING} is present",
        r'the response JSON field "([^"]*)" is present',
        [("string", "field")],
        "api.AssertFieldPresent(field);",
        False,
    ),
    (
        "Then",
        rf"the response decimal field {_STRING} equals {_DECIMAL}",
        r'the response decimal field "([^"]*)" equals (-?\d+(?:\.\d+)?)',
        [("string", "field"), ("string", "expected")],
        "api.AssertDecimal(field, decimal.Parse(expected, "
        "System.Globalization.NumberStyles.AllowLeadingSign | "
        "System.Globalization.NumberStyles.AllowDecimalPoint, "
        "System.Globalization.CultureInfo.InvariantCulture));",
        False,
    ),
]


def common_step(keyword: str, text: str) -> tuple[str, list[tuple[str, str]], str, bool] | None:
    for kind, matcher, pattern, parameters, body, asynchronous in COMMON_STEPS:
        if kind == keyword and re.fullmatch(matcher, text):
            return f"^{pattern}$", parameters, body, asynchronous
    return None


def support_files(cases: list[Any]) -> list[tuple[str, str]]:
    """Embed only supplied JSON fixtures; conflicting names require external configuration."""
    fixtures: dict[str, Any] = {}
    raw_fixtures: dict[str, str] = {}
    conflicts: set[str] = set()
    for case in cases:
        for datum in case.test_data:
            try:
                payload = json.loads(
                    datum.value, parse_float=Decimal, parse_constant=_reject_constant
                )
            except (ValueError, TypeError):
                continue
            if not isinstance(payload, (dict, list)):
                continue
            if datum.name in fixtures and fixtures[datum.name] != payload:
                conflicts.add(datum.name)
            fixtures[datum.name] = payload
            raw_fixtures[datum.name] = datum.value
    for name in conflicts:
        raw_fixtures.pop(name, None)
    # Retain original JSON numeric tokens; a Python float round trip loses decimal precision.
    literal = (
        "{" + ",".join(json.dumps(name) + ":" + raw for name, raw in raw_fixtures.items()) + "}"
    ).replace('"', '""')
    source = (
        "namespace Generated.StepDefinitions\n{\n"
        "    internal static class ApprovedFixtures\n    {\n"
        f'        internal const string Json = @"{literal}";\n'
        "    }\n}\n"
    )
    template = Path(__file__).parent.parent / "templates" / "reqnroll" / "ApiScenario.cs"
    return [
        ("Support/ApiScenario.cs", template.read_text(encoding="utf-8")),
        ("Support/ApprovedFixtures.cs", source),
    ]


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-JSON numeric constant: {value}")
