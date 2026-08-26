# Company solution requirements

## 1. Objective

Build a governed internal platform that converts product requirements into independently
validated manual and automated test cases, stores approved suites for reuse, and optionally
publishes selected cases to Jira after human approval.

## 2. Scope

### In scope

- Pasted requirement text and supported document uploads.
- Manual and automation test-case generation.
- Normal step and SpecFlow BDD output.
- Independent validation and quality findings.
- Validated-suite retrieval and storage.
- CSV and JSON export.
- Explicit Jira Cloud publishing.
- Application documentation and agent discovery.

### Out of scope for the initial release

- Autonomous execution of generated tests.
- Automatic Jira publishing without human action.
- Production customer or payment data.
- Automatic model-provider fallback.
- Native Xray or Zephyr test entities unless separately approved.
- Semantic or approximate suite reuse in place of exact-match retrieval.

## 3. Functional requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-001 | Accept pasted requirements | Valid text from 10 to 30,000 characters is normalized and accepted |
| FR-002 | Accept supported documents | DOCX, PDF, XLSX, Pages, Numbers, PNG, and JPEG are handled or rejected with actionable guidance |
| FR-003 | Enforce upload limits | Files over 15 MB and images over the configured pixel limit are rejected before generation |
| FR-004 | Generate structured tests | Every case contains ID, title, objective, category, priority, execution mode, rationale, and observable steps |
| FR-005 | Support manual and automation | Each generated case is explicitly classified with a case-specific feasibility reason |
| FR-006 | Support BDD | Requested BDD output is valid copy-ready SpecFlow Gherkin |
| FR-007 | Validate output independently | Coverage, traceability, duplicates, clarity, and expected results are checked after generation |
| FR-008 | Prevent invalid storage | Newly generated suites with validation errors are not stored for reuse |
| FR-009 | Revalidate retrieved suites | Cached suites are independently validated before return |
| FR-010 | Reuse known suites | An exact normalized match can return from organizational memory without a new Copilot request |
| FR-011 | Export results | Users can download JSON and CSV versions of a generated suite |
| FR-012 | Publish selected cases | Only explicitly selected cases are attached to an existing Jira issue |
| FR-013 | Discover agents | The API and documentation list every agent, purpose, runtime, and capability |
| FR-014 | Report safe failures | Authentication, policy, quota, timeout, document, and Jira errors are actionable without leaking secrets |

## 4. Agent requirements

### Input Agent

- Normalize pasted text.
- Extract readable document content locally.
- Enforce type, byte, character, and image limits.
- Provide actionable errors for encrypted, scanned, malformed, and unsupported documents.
- Never send document content directly to an unapproved external service.

### Manual and Automation Test Case Generator

- Use only the approved GitHub Copilot runtime.
- Run with tools, MCP servers, file hooks, repository discovery, and model memory disabled.
- Produce Pydantic-compatible structured output.
- Cover critical paths, important negative cases, and relevant human-dependent risks.
- Generate synthetic test data only.

### Validator Agent

- Operate independently from generation.
- Return a structured score, pass/fail decision, and actionable findings.
- Check explicit acceptance-criteria coverage and per-case traceability.
- Detect duplicates and vague or unobservable assertions.
- Allow company-specific validation policies to be added without changing the generator.

### Test Storage Agent

- Store only validator-approved newly generated suites.
- Use normalized, versioned keys.
- Track access count and last-access time.
- Support organizational retention and deletion controls.
- Provide tenant or project isolation before organization-wide production use.

## 5. Non-functional requirements

| ID | Area | Requirement |
|---|---|---|
| NFR-001 | Security | All application traffic uses TLS outside local development |
| NFR-002 | Identity | Production users authenticate through corporate SSO |
| NFR-003 | Authorization | Roles control generation, administration, and publishing privileges |
| NFR-004 | Privacy | Logs exclude requirements, prompts, generated content, and credentials |
| NFR-005 | Traceability | Every HTTP response includes a safe `X-Request-ID` |
| NFR-006 | Availability | Target availability and support hours are defined before production approval |
| NFR-007 | Performance | Non-AI endpoints meet the company's interactive API latency target |
| NFR-008 | Timeout | Copilot and Jira calls use bounded, configurable timeouts |
| NFR-009 | Scalability | Multi-replica deployments use shared managed storage rather than local SQLite |
| NFR-010 | Resilience | Premium AI generation is not automatically retried without an explicit policy |
| NFR-011 | Accessibility | The browser UI targets WCAG 2.2 AA |
| NFR-012 | Maintainability | Ruff, MyPy, tests, coverage, audit, and compilation pass in CI |
| NFR-013 | Supply chain | Dependencies and container images are scanned; production artifacts are immutable |
| NFR-014 | Recovery | Backup, restoration, rollback, and deletion procedures are tested |

## 6. Data requirements

The following data classes must be documented:

- Uploaded requirement content.
- Extracted document text.
- Copilot prompts and structured responses.
- Generated test suites and validation reports.
- Organizational-memory metadata.
- Jira issue keys, attachments, comments, and integration identity.
- Operational metadata such as timestamps, status codes, duration, and request IDs.

For each class, specify owner, classification, permitted users, encryption, retention, backup,
deletion, geographic constraints, and whether it may be processed by GitHub Copilot.

## 7. Environment requirements

Maintain isolated environments:

| Environment | Purpose | Data rule |
|---|---|---|
| Development | Local implementation | Synthetic data only |
| Test | Automated and integration validation | Synthetic or approved masked data |
| Pilot | Controlled business evaluation | Approved low-risk requirements only |
| Production | General authorized use | Policy-controlled company data |

Secrets, databases, Copilot identities, Jira identities, and network policies must be separate by
environment.

## 8. Acceptance and launch criteria

- All functional requirements selected for the release have passing tests.
- `make quality` passes, including the vulnerability audit and coverage threshold.
- Security and privacy reviews are approved.
- Corporate authentication and authorization are tested.
- Representative QA evaluation demonstrates agreed coverage, correctness, duplication, and
  usefulness targets.
- Cost and premium-request consumption are observable.
- Support, incident, backup, recovery, and rollback procedures are tested.
- Pilot users complete training on limitations and mandatory human review.

## 9. Success measures

Agree measurable targets before the pilot, for example:

- Reduction in test-design lead time.
- Percentage of generated cases accepted with minor or no edits.
- Acceptance-criteria coverage after QA review.
- Duplicate-case rate.
- Manual-versus-automation classification accuracy.
- Copilot requests avoided through validated reuse.
- Jira publishing success rate.
- User satisfaction and weekly active users.
- Security, privacy, and production-incident count.
