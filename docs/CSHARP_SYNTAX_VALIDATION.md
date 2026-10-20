# C# validation with Tree-sitter and Roslyn

C# automation generation uses both tools:

- Tree-sitter detects invalid binding syntax and branching in step definitions, including
  bindings placed outside StepDefinitions. Existing language checks remain in place.
- Roslyn parses every supplied `.cs` file using C# 12, including services, builders, models,
  hooks and bindings. Compiler syntax errors include file, line, column and diagnostic code.

Roslyn runs before accepting generated or cached implementation sources and again after the
framework assets are assembled. Its findings enter the existing provider validation/repair
flow. Install and download validation also reject syntax errors in C# helpers.
The existing Tree-sitter detail setting controls its diagnostic presentation; it does not
turn off Roslyn validation. Missing, failing or timed-out Roslyn tooling blocks C# acceptance
with setup instructions. Other languages do not require Roslyn.

## Setup and deployment

Install the .NET 8 SDK. From `app/tools/roslyn`, run:

```sh
dotnet build RoslynSyntax.csproj -c Release
```

The tool's local global.json selects the latest installed .NET 8 feature band. The project
references Roslyn assemblies shipped with that SDK, with no additional NuGet packages.
The Docker image builds this helper during deployment. Python installations include its
source/project files and lazily build it if necessary; that installation directory must be
writable for the initial build. Prebuild the helper for read-only runtime deployments.

Only the trusted parser project is built. Generated projects, MSBuild targets and source
code are never executed by this syntax check. Source is passed as JSON on standard input.
Each parse has a timeout, results are cached by complete file contents, and up to 100 syntax
errors are returned per pack. No SDK or runtime installation happens automatically.

## What this establishes

Roslyn **syntax parsing** does not resolve third-party packages, types, method calls or
cross-file references. It is not semantic compilation and does not demonstrate passing tests.
Build the generated project and execute its ReqnRoll scenarios in the configured environment
before claiming those checks passed. Source checks do not alter the required Codex or Copilot
model policies, approved quotation payload, HttpClient requirements or human approval gates.

## Repeatable verification

```sh
PYTHONPATH=. .venv/bin/python -m pytest tests/test_roslyn_syntax.py tests/test_code_syntax.py tests/test_reqnroll_validation.py
PYTHONPATH=. .venv/bin/python tests/support/run_roslyn_framework_acceptance.py
```

The latter creates a full generated framework with two approved quotation transport scenarios,
all bindings, HttpClient services, request builders and approved input files. It runs the
entire pack through ReqnRoll against a temporary loopback echo fixture and inspects actual
TRX executed/passed counts. The generated pack and reports remain in its printed temporary
folder. This checks framework wiring and payload preservation, not production quotation
rules or an external target environment.
