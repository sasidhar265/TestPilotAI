# Company project prerequisites

## Document control

| Field | Value |
|---|---|
| Project | TestPilot AI — Requirements-to-Tests Platform |
| Document | Company implementation prerequisites |
| Status | Draft for organizational review |
| Owners | Product, Quality Engineering, Platform Engineering, Security |
| Review cycle | Before pilot and before every production expansion |

## Purpose

This document defines the organizational, technical, security, and operational conditions that
must be satisfied before TestPilot AI is developed, piloted, or deployed inside the company.

## Business prerequisites

- A named executive or departmental sponsor.
- A product owner accountable for scope, adoption, and success measures.
- A QA lead accountable for generated-test quality and validation policy.
- A defined initial user group, product area, and pilot duration.
- Approved business use cases, such as story refinement, document-to-test conversion, BDD
  generation, regression reuse, or Jira publishing.
- Agreement that generated tests are drafts requiring human review.
- A budget for engineering, platform infrastructure, Copilot licences, model usage, and support.

## Required stakeholders

| Role | Responsibility |
|---|---|
| Business sponsor | Funding, organizational priority, escalation |
| Product owner | Requirements, backlog, adoption, benefits measurement |
| QA owner | Test-design policy, validation rules, approval criteria |
| Engineering owner | Architecture, implementation, code ownership |
| Platform/DevOps | Environments, CI/CD, monitoring, backups, recovery |
| Security | Threat modelling, secrets, vulnerability and incident policy |
| Privacy/legal | Data classification, retention, provider approval |
| GitHub administrator | Copilot licences, CLI policy, model policy |
| Jira administrator | Service account, permissions, project integration |
| Support owner | Runbooks, service requests, incidents, user communication |

## GitHub Copilot prerequisites

- The company has an eligible GitHub Copilot plan.
- Required users or service identities have assigned licences.
- The Copilot CLI policy is enabled by the GitHub organization administrator.
- Approved models are documented and available to the intended identities.
- Premium-request allowances, expected volume, and cost monitoring are agreed.
- Interactive authentication or a company-approved non-interactive token method is selected.
- Security and privacy teams approve sending the permitted requirement classifications to
  GitHub Copilot.
- The application must remain fail-closed when the approved runtime is unavailable.

## Development environment prerequisites

- Python 3.11 or newer.
- Git and access to the company source repository.
- GitHub Copilot CLI and an authenticated Copilot identity.
- Docker for container development and production-parity testing.
- Tesseract OCR for PNG and JPEG requirement extraction.
- Access to the company's package registry or approved public package sources.
- IDE configuration for Python, Ruff, MyPy, and pytest.

Recommended setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
copilot login
make quality
uvicorn app.main:app --reload
```

## Infrastructure prerequisites

### Pilot

- One containerized FastAPI instance.
- TLS termination through a corporate ingress or reverse proxy.
- Persistent encrypted storage for organizational memory.
- Centralized application logs.
- Secret-manager integration.
- Restricted outbound access to GitHub Copilot and optional Jira Cloud endpoints.

### Production

- Managed container platform with separate development, test, and production environments.
- Corporate SSO through OIDC or SAML and role-based authorization.
- API gateway or ingress with TLS, request-size enforcement, rate limiting, and access logs.
- Managed relational database instead of local SQLite when running multiple replicas.
- Encryption in transit and at rest.
- Backups with tested restoration procedures.
- Metrics, alerting, log aggregation, and request tracing.
- Malware scanning for uploaded files.
- Approved container registry with image scanning and signing.
- Network egress controls and documented provider allowlists.

## Jira prerequisites

Jira is optional. When enabled, use a dedicated least-privileged integration identity with:

- Browse Projects.
- Add Attachments.
- Add Comments.

The company must also decide whether publishing targets basic Jira attachments or a test-management
product such as Xray or Zephyr. Each product requires a separate adapter and approval process.

## Security and privacy prerequisites

- Complete a threat model covering uploads, prompt injection, generated content, local storage,
  Copilot, Jira, and administrative access.
- Define allowed and prohibited data classifications.
- Prohibit credentials, production personal data, payment data, and secrets in requirements.
- Define retention, deletion, backup, and legal-hold rules for uploaded and generated content.
- Approve the provider data flow and geographic-processing requirements.
- Store secrets only in the company secret manager.
- Enable dependency, secret, source, and container scanning.
- Define incident-response ownership and notification paths.
- Confirm that logs never contain document content, prompts, generated tests, or credentials.
- Require explicit human authorization for Jira and other external writes.

## Governance prerequisites

- Protected main branch and pull-request review.
- Named code owners for agents, application services, infrastructure, and security-sensitive code.
- CI must pass formatting, linting, type checking, tests, coverage, compilation, and dependency
  vulnerability auditing.
- Architecture changes must be documented and reviewed.
- Prompts, schemas, validation policies, and model choices must be version controlled.
- Generated-output quality must be evaluated against an approved representative dataset before
  pilot and after material changes.

## Readiness exit criteria

The project is ready for a controlled pilot only when:

- All required owners are assigned.
- Copilot and data-processing approvals are recorded.
- Development and test environments are operational.
- Authentication and least-privilege access are implemented.
- The quality gate passes without suppressed critical findings.
- Logging, monitoring, backup, and incident procedures are tested.
- Pilot use cases and success metrics are approved.
- A user-review and feedback process exists.
- Rollback and data-deletion procedures have been demonstrated.
