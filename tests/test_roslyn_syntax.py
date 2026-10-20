"""Real compiler-parser checks, independent of generated-code execution."""

import subprocess
from types import SimpleNamespace

import pytest

from app import roslyn_syntax
from app.agents.multilanguage_agent import ArtifactFile, LanguageArtifact, safe_files


def source(path, content):
    return SimpleNamespace(path=path, content=content)


def test_roslyn_checks_syntax_in_services_not_just_bindings():
    findings = roslyn_syntax.csharp_syntax_findings(
        [source("Services/InvalidService.cs", "class Service { public void Send( { }")]
    )
    assert any("Services/InvalidService.cs:1:" in item and "Roslyn CS" in item for item in findings)
    assert not any("unavailable" in item for item in findings)


def test_roslyn_accepts_csharp12_and_does_not_claim_dependency_resolution():
    files = [
        source(
            "Services/Valid.cs",
            '''
namespace Generated;
public class Valid(ExternalDependency dependency)
{
    public string Text() => """literal if switch ? :""";
}
''',
        )
    ]
    assert roslyn_syntax.csharp_syntax_findings(files) == []


def test_multilanguage_download_rejects_invalid_csharp_helpers():
    artifact = LanguageArtifact(
        language="csharp",
        framework="ReqnRoll",
        files=[ArtifactFile(path="Services/Broken.cs", content="class Broken { void Send( { }")],
    )
    with pytest.raises(ValueError, match="Roslyn CS"):
        safe_files(artifact)


@pytest.mark.parametrize(
    "failure", [RuntimeError("missing SDK"), subprocess.TimeoutExpired("dotnet", 1)]
)
def test_unavailable_compiler_cannot_silently_pass(monkeypatch, failure):
    def unavailable():
        raise failure

    roslyn_syntax._diagnostics.cache_clear()
    monkeypatch.setattr(roslyn_syntax, "_tool", unavailable)
    findings = roslyn_syntax.csharp_syntax_findings([source("Services/A.cs", "class A {}")])
    assert "Roslyn C# validation unavailable" in findings[0]
    roslyn_syntax._diagnostics.cache_clear()


def test_non_csharp_never_invokes_roslyn(monkeypatch):
    def forbidden(*args):
        raise AssertionError("Roslyn is only for C#")

    monkeypatch.setattr(roslyn_syntax, "_diagnostics", forbidden)
    assert roslyn_syntax.csharp_syntax_findings([source("Services/A.java", "class A {}")]) == []


def test_pack_implementation_validation_includes_roslyn_supporting_file_diagnostics():
    from app.agents.reqnroll_step_definition_agent import StepDefinitionArtifact, StepDefinitionFile
    from app.agents.reqnroll_validation import implementation_findings

    artifact = StepDefinitionArtifact(
        files=[
            StepDefinitionFile(path="Builders/Broken.cs", content="class Broken { int Value => ; }")
        ],
        coverage=[],
    )
    assert any(
        "Builders/Broken.cs:" in item and "Roslyn CS" in item
        for item in implementation_findings(artifact)
    )


def test_changed_source_at_same_path_is_rechecked():
    assert roslyn_syntax.csharp_syntax_findings([source("Models/Cache.cs", "class Cache {}")]) == []
    assert roslyn_syntax.csharp_syntax_findings([source("Models/Cache.cs", "class Cache { ")])
