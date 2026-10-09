"""Regression checks for syntax-aware automation pack guardrails."""

import re
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.agents.multilanguage_agent import ArtifactFile, LanguageArtifact, safe_files
from app.automation_style import step_style_findings
from app.code_syntax import parse_source


@pytest.mark.parametrize(
    "suffix,source,kind",
    [
        ("cs", "public void Step() { if (ready) service.Send(); }", "if_statement"),
        ("cs", "public int Step() => ready ? 1 : 0;", "conditional_expression"),
        ("cs", 'public int Step() => kind switch { "a" => 1, _ => 0 };', "switch_expression"),
        ("java", "class Steps { void step() { if (ready) service.send(); } }", "if_statement"),
        ("java", "class Steps { int step() { return ready ? 1 : 0; } }", "ternary_expression"),
        (
            "java",
            "class Steps { int step() { return switch (kind) { default -> 0; }; } }",
            "switch_expression",
        ),
        ("js", 'Then("x", () => { switch (kind) { default: send(); } });', "switch_statement"),
        ("js", 'Then("x", () => `${ready ? pass() : fail()}`);', "ternary_expression"),
        ("ts", 'Then("x", () => { if (ready) send(); });', "if_statement"),
        ("ts", 'Then("x", () => `${ready ? pass() : fail()}`);', "ternary_expression"),
        ("cs", 'public string Step() => $"{(ready ? 1 : 0)}";', "conditional_expression"),
        ("rb", 'Then("x") do\n send_request if ready\nend', "if_modifier"),
        ("rb", 'Then("x") do\n send_request unless ready\nend', "unless_modifier"),
        ("rb", 'Then("x") do\n unless ready\n send_request\n end\nend', "unless"),
        ("rb", 'Then("x") do\n case kind\n when 1\n send_request\n end\nend', "case"),
        ("rb", 'Then("x") do\n ready ? pass : fail\nend', "conditional"),
    ],
)
def test_branch_nodes_report_locations(suffix, source, kind):
    findings = step_style_findings(f"StepDefinitions/Example.{suffix}", source)
    assert any(f"({kind})" in finding for finding in findings)
    assert all(
        re.match(rf"StepDefinitions/Example\.{suffix}:\d+:\d+: ", finding) for finding in findings
    )
    assert not any("invalid step-definition syntax" in finding for finding in findings)


@pytest.mark.parametrize(
    "suffix,source",
    [
        ("cs", 'public void Step() { service.Send("""if "switch" ? :"""); }'),
        ("cs", 'public void Step() { service.Send(@"if ""switch"" ? :"); }'),
        ("cs", "public void Step() { var @if = service; @if.Send(); }"),
        ("cs", 'public void Step() { service.Send(value?.Name ?? "default"); }'),
        ("java", 'class Steps { void step() { service.send("""\nif switch ? :\n"""); } }'),
        ("js", 'Then("x", () => service.send(/if|switch|\\?:/));'),
        ("js", 'Then("x", () => service.send(`if switch ? : ${value}`));'),
        ("ts", 'Then("x", () => service.send(value?.name ?? "if"));'),
        ("rb", 'Then("x") do\n service.send_request(:if, :case, /unless/) # if ready\nend'),
    ],
)
def test_literal_text_and_nonconditional_operators_are_allowed(suffix, source):
    assert step_style_findings(f"StepDefinitions/Example.{suffix}", source) == []


@pytest.mark.parametrize(
    "suffix,source",
    [
        ("cs", '[Reqnroll.GivenAttribute("x")] public void Step() { if (ready) Send(); }'),
        ("cs", '[Reqnroll . Given("x")] public void Step() { if (ready) Send(); }'),
        (
            "java",
            'class Steps { @io.cucumber.java.en.Given("x") void step() { if (ready) send(); } }',
        ),
        ("js", 'bdd.Given("x", () => { if (ready) send(); });'),
        ("ts", 'Given("x", () => { if (ready) send(); });'),
        ("rb", 'Given("x") do\n send_request unless ready\nend'),
    ],
)
def test_moved_bindings_cannot_bypass_validation(suffix, source):
    assert any(
        "step definitions must delegate" in finding
        for finding in step_style_findings(f"Services/Example.{suffix}", source)
    )


def test_step_registration_text_in_strings_does_not_restrict_services():
    source = '''class Service {
        public void Send() {
            var example = """[Given("example")]""";
            if (ready) SendRequest();
        }
    }'''
    assert step_style_findings("Services/Example.cs", source) == []


@pytest.mark.parametrize(
    "suffix,source",
    [
        ("cs", 'public void Step() { service.Send("x");'),
        ("java", 'class Steps { void step() { service.send("x");'),
        ("js", 'Then("x", () => { service.send('),
        ("ts", 'Then("x", () => { service.send('),
        ("rb", 'Then("x") do\n service.send_request'),
    ],
)
def test_malformed_steps_are_rejected_with_a_location(suffix, source):
    findings = step_style_findings(f"StepDefinitions/Example.{suffix}", source)
    assert any("invalid step-definition syntax" in finding for finding in findings)
    assert all(finding.startswith(f"StepDefinitions/Example.{suffix}:") for finding in findings)


def test_exact_line_and_column_for_conditional():
    source = "public void Step() {\n    if (ready) Send();\n}"
    findings = step_style_findings("StepDefinitions/Example.cs", source)
    assert findings[0].startswith("StepDefinitions/Example.cs:2:5:")


def test_multilanguage_pack_download_rejects_interpolated_conditionals():
    artifact = LanguageArtifact(
        language="javascript",
        framework="Cucumber-JS",
        files=[
            ArtifactFile(
                path="StepDefinitions/Example.js",
                content='Then("x", () => `${ready ? pass() : fail()}`);',
            )
        ],
    )
    with pytest.raises(ValueError, match="ternary_expression"):
        safe_files(artifact)


def test_parsers_can_be_used_by_concurrent_generations():
    samples = [
        (".cs", "public void Step() { service.Send(); }"),
        (".js", 'Then("x", () => send());'),
    ] * 20
    with ThreadPoolExecutor(max_workers=4) as executor:
        roots = list(executor.map(lambda sample: parse_source(*sample), samples))
    assert all(root is not None and not root.has_error for root in roots)


def test_python_retains_builtin_syntax_validation():
    assert parse_source(".py", "def step(): pass") is None
    assert step_style_findings("StepDefinitions/Example.py", "def step():\n    if ready: send()")
    assert step_style_findings("StepDefinitions/Example.py", "def step(:") == [
        "StepDefinitions/Example.py: invalid Python step definitions"
    ]


@pytest.mark.parametrize(
    "source", ["public void Step() { if (ready) Send(); }", "public void Step() {"]
)
def test_compact_diagnostics_still_reject_invalid_steps(source):
    assert step_style_findings(
        "StepDefinitions/Example.cs", source, detailed_diagnostics=False
    ) == [
        "StepDefinitions/Example.cs: step definitions must have valid syntax and delegate "
        "conditional behavior to strategies/services; if/else, switch/match and ternary "
        "expressions are not allowed"
    ]
