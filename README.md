# Story-to-Tests AI Agent

A local web application that turns a user story, feature description, or acceptance criteria
into structured test cases. It classifies cases as critical, smoke, sanity, or regression,
generates safe synthetic test data, exports Xray-ready CSV/Excel/JSON through the Context
Converter Agent, and can attach the CSV to a Jira Cloud
story with a summary comment.

Requirements can be pasted or uploaded as Word (`.docx`), text PDF, Excel (`.xlsx`), Apple
Pages (`.pages`), Apple Numbers (`.numbers`), PNG, or JPEG. Pages/Numbers packages are read from
Quick Look previews or legacy XML when available; binary-only IWA packages must first be exported
from the Mac as PDF or XLSX. A document-ingestion component extracts normalized text, the requirement-to-test-case
agent generates the suite, and an independent validator reports coverage, traceability,
duplicates, clarity, and expected-result quality. Image extraction uses local Tesseract OCR.

The functional pipeline uses discoverable agents: Input, SpecForge Router, focused Manual and
Automation Test Case Generators, Validator, and Test Storage. `GET /api/agents` lists their responsibilities,
runtimes, and capabilities. Only suites that pass independent validation are newly stored for
future exact-match reuse.

Agent behavior is defined in readable `.github/agents/*.agent.md` files. The FastAPI/Python layer
loads the relevant SpecForge, specialist, and quality-gate policies into each Copilot session and
retains deterministic enforcement for validation, conversion, storage, security, and the web UI.
Team and project customization is layered through `.github/agent-profiles/<profile>/`. Set
`AGENT_PROFILE` to select a profile; `profile.md` applies common rules and optional files named
after an agent add role-specific conventions. The base safety and quality policies cannot be
replaced by a profile.

The active default is `auto-finance-quotation`. Its `knowledge/quotation-brd-baseline.md` is the
reviewable BRD v1.0 knowledge source used by the agents. This is prompt-time grounded context, not
irreversible model fine-tuning; updating or reverting the Markdown changes the baseline cleanly.

At generation time, choose either manual test cases with numbered steps and expected results or BDD
scenarios written as `Scenario / Given / When / Then`. Both formats retain category, priority,
automation/manual feasibility, a decision rationale, test data, acceptance-criteria traceability,
and CSV/JSON/Jira export support.

BDD output is ready for SpecFlow feature files. Data-driven flows use `Scenario Outline` with
parameter placeholders and `Examples` tables where appropriate. The results screen can copy an
individual scenario or a complete feature containing all generated scenarios.

Before calling Copilot, the application checks a repository-local organizational memory at
`.agent-memory/test_suites.db`. An exact normalized match returns the previously validated suite
immediately and avoids a new premium request. New results are stored for subsequent reuse. The
database is local operational data and is excluded from source control.

For this proof of concept, generation returns 4–5 concise, high-level, non-duplicate risk
scenarios, including at least two automation and two manual cases, while keeping Copilot response
times practical. Before publishing, select individual cases
with the Jira checkboxes; only those cases are included in the Jira attachment and summary.

## Run locally

1. Install Python 3.11 or newer.
2. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e '.[dev]'
   ```

3. Copy `.env.example` to `.env`.
4. Ensure GitHub Copilot CLI is installed, then authenticate it using your Copilot-enabled
   account:

   ```bash
   copilot login
   ```

   Your organization administrator must enable the Copilot CLI policy. For non-interactive
   deployments, configure `COPILOT_GITHUB_TOKEN` instead.
5. Start the app:

   ```bash
   uvicorn app.main:app --reload
   ```

6. Open <http://127.0.0.1:8000>. API documentation is at `/docs`.

## Engineering quality

The repository enforces a shared organizational baseline through executable checks:

```bash
make quality
```

This runs Ruff formatting/lint policy, MyPy type checks, tests with branch coverage, and Python
compilation. CI also audits installed dependencies for known vulnerabilities. The application
ships with JSON request logs, correlation IDs, baseline browser security headers, a non-root
container image, bounded document processing, sanitized provider errors, and an explicit
human-controlled Jira publication boundary.

## GitHub Copilot runtime

GitHub Copilot is the only AI runtime in this application. The official Python Copilot SDK
starts its bundled Copilot CLI runtime and uses either the locally signed-in GitHub identity or
`COPILOT_GITHUB_TOKEN`. The app does not support OpenAI keys, GitHub Models, Ollama, BYOK, mock
generation, or any other agent/provider.

Each generation prompt counts toward the Copilot usage allowance associated with the
authenticated identity. The browser requests 4–5 high-level scenarios in one prompt so a
failed follow-up cannot leave partial results. Leave `COPILOT_MODEL` blank to use the account
default, or set it to a
model allowed by your organization's Copilot policy. Never commit a token.

## Jira Cloud setup

Set `JIRA_BASE_URL`, `JIRA_EMAIL`, and `JIRA_API_TOKEN` in `.env`. The Jira user needs Browse
Projects, Add Attachments, and Add Comments permissions for the target project. The app uses
Jira Cloud REST API v3. Publishing is always initiated by the user and attaches a timestamped
CSV; it does not create or overwrite Jira issues.

For Jira Data Center or a test-management plugin such as Xray/Zephyr, implement a separate
adapter because their authentication and test-case APIs differ.

## Develop with GitHub Copilot

Open the folder in VS Code, install the GitHub Copilot and GitHub Copilot Chat extensions, and
sign in. Repository guidance is already provided in `.github/copilot-instructions.md`.

This repository also includes:

- `.github/agents/test-designer.agent.md`: a custom QA-focused Copilot agent.
- `.github/prompts/add-test-generation-feature.prompt.md`: a reusable agent-mode prompt.
- `.github/workflows/ci.yml`: GitHub Actions checks for every pull request and main-branch push.

In Copilot Chat, select the `test-designer` custom agent when designing or changing test-suite
behaviour. Use `/add-test-generation-feature` for implementation tasks where
prompt files are supported.

Useful Copilot Chat tasks:

- `Add unit tests for JiraClient using respx; cover attachment and comment failures.`
- `Add an editable review screen before publishing while preserving the TestSuite schema.`
- `Add an Xray Cloud publisher as a new adapter without changing JiraClient.`
- `Add Playwright end-to-end tests for generation, download, and validation errors.`

Always review generated code and test cases. The AI output is a draft, not evidence of coverage
or a substitute for security, accessibility, performance, and domain-expert testing.

## Architecture

### End-to-end agent flow

```mermaid
flowchart TD
    A[User enters a requirement or uploads a BRD] --> B[Web UI and FastAPI]
    B --> C[Input Agent extracts and normalizes text]
    C --> D{Validated suite in local memory?}

    D -->|Yes| Q[Quality Gate Agent revalidates the suite]
    D -->|No| S[SpecForge Router classifies the request]

    P[Markdown agent policies] --> S
    K[Active project profile and BRD knowledge] --> S
    O[Relevant approved organizational knowledge] --> S

    S --> R{Generation route}
    R -->|Manual| M[Manual Test Case Generator]
    R -->|Automation| T[Automation Test Generator]
    R -->|Both| M
    R -->|Both| T

    M --> MQ[Manual quality review]
    T --> AQ[Automation quality review]
    MQ -->|Revise once when needed| M
    AQ -->|Revise once when needed| T
    MQ -->|Passed| G[Merge approved test cases]
    AQ -->|Passed| G
    G --> Q

    Q -->|Failed| E[Return actionable validation errors]
    Q -->|Passed| TS[Test Storage Agent saves validated suite]
    TS --> V[Display reviewable results in the UI]

    V --> CC[Context Converter Agent]
    CC --> CSV[Xray-ready CSV]
    CC --> XLSX[Xray-ready Excel]
    CC --> JSON[Xray-ready JSON]
    CC --> FEATURE[BDD feature file]

    CSV --> OA[Output Agent stores artifacts and scenarios]
    XLSX --> OA
    JSON --> OA
    FEATURE --> OA
    OA -. relevant approved context .-> O

    V -->|Explicit user action| J[Jira Cloud attachment and comment]
```

SpecForge can select one specialist or both. BDD scenarios target exactly three concise steps
(`Given`, `When`, and `Then`) and never exceed four steps. Generated content must pass the
deterministic quality gate before it is stored, converted, reused, or offered for publication.

### Architectural view

```mermaid
flowchart TB
    subgraph CLIENT[Presentation layer]
        UI[Browser UI]
    end

    subgraph APP[FastAPI application]
        API[HTTP API and security middleware]
        INGEST[Document ingestion and OCR]

        subgraph ORCH[Agent orchestration]
            INPUT[Input Agent]
            ROUTER[SpecForge Router]
            MANUAL[Manual Test Generator]
            AUTO[Automation Test Generator]
            GATE[Quality Gate Agent]
            CONVERT[Context Converter Agent]
            OUTPUT[Output Agent]
            STORAGE[Test Storage Agent]
        end

        subgraph GOVERNANCE[Markdown-driven governance]
            BASE[Base agent policies]
            PROFILE[Team or project profile]
            BRD[Versioned BRD knowledge]
            LOADER[Instruction loader and allowlist]
        end
    end

    subgraph LOCAL[Local persistence]
        DB[(SQLite organizational memory)]
        FILES[CSV, XLSX, JSON, and feature artifacts]
    end

    subgraph EXTERNAL[External services]
        COPILOT[GitHub Copilot SDK and CLI service]
        JIRA[Jira Cloud]
    end

    UI <--> API
    API --> INGEST --> INPUT --> ROUTER
    ROUTER --> MANUAL
    ROUTER --> AUTO
    MANUAL --> GATE
    AUTO --> GATE
    GATE --> STORAGE
    GATE --> CONVERT --> OUTPUT

    BASE --> LOADER
    PROFILE --> LOADER
    BRD --> LOADER
    LOADER --> ROUTER
    LOADER --> MANUAL
    LOADER --> AUTO
    LOADER --> GATE

    ROUTER --> COPILOT
    MANUAL --> COPILOT
    AUTO --> COPILOT
    STORAGE <--> DB
    OUTPUT <--> DB
    OUTPUT --> FILES
    API -->|User-approved publish| JIRA
```

The Markdown files provide customizable instructions and domain context; Python retains the
trusted runtime boundary for schema enforcement, deterministic validation, storage, conversion,
security, and external integrations. Prompt-time knowledge grounding can be updated per project
without retraining or changing the underlying model.

- `app/agents/`: typed capability contract and fail-closed Copilot runtime registry.
- `app/agents/test_case_validator.py`: independent deterministic test-suite validation agent.
- `app/services/`: application use-case orchestration, independent of HTTP transport.
- `app/services/document_ingestion.py`: bounded Word, PDF, Excel, and image text extraction.
- `app/dependencies.py`: composition root for the approved runtime and application services.
- `app/generator.py`: GitHub Copilot SDK generation, schema validation, and QA instructions.
- `app/models.py`: validated API and model-output contracts.
- `app/jira.py`: Jira Cloud attachment/comment integration.
- `app/exporter.py`: CSV export.
- `app/static/index.html`: dependency-free browser UI.
- `tests/`: fast local tests; external APIs should always be mocked.

See [architecture](docs/architecture.md), [operations](docs/operations.md),
[engineering standards](docs/engineering-standards.md), [contributing](CONTRIBUTING.md), and
[security policy](SECURITY.md) for the organization-standard framework and governance rules.

For company adoption, use the [project prerequisites](docs/company-project-prerequisites.md),
[solution requirements](docs/company-solution-requirements.md), and
[implementation checklist](docs/company-implementation-checklist.md) as the approval and delivery
pack.

For stakeholder presentations, use the [client demonstration guide](docs/client-demo-guide.md)
and the downloadable [client demo PowerPoint](docs/TestPilot_AI_Client_Demo.pptx).
