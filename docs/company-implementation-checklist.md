# Company implementation checklist

Use this checklist as the project entry gate and production-readiness record. Replace each owner
placeholder with a named person or team and link evidence in the company delivery system.

## Project initiation

- [ ] Sponsor and product owner assigned.
- [ ] QA, engineering, platform, security, privacy, GitHub, Jira, and support owners assigned.
- [ ] Scope, initial use cases, pilot group, budget, and success measures approved.
- [ ] Risks, assumptions, dependencies, and out-of-scope items recorded.

## Provider and data approval

- [ ] GitHub Copilot licences available.
- [ ] Copilot CLI policy enabled.
- [ ] Approved models and identity strategy documented.
- [ ] Premium-request budget and monitoring agreed.
- [ ] Data classifications allowed for Copilot processing approved.
- [ ] Retention, deletion, geographic processing, and legal requirements approved.

## Engineering foundation

- [ ] Company repository created with protected branches.
- [ ] CODEOWNERS and pull-request approvals configured.
- [ ] Development environment and package source documented.
- [ ] `make quality` passes on developer workstations and CI.
- [ ] Dependency, secret, source, and container scanning enabled.
- [ ] Build artifacts are immutable and traceable to a source revision.

## Application and agents

- [ ] Input Agent types and safety limits approved.
- [ ] Generator prompt and output schema approved by QA.
- [ ] Manual/automation classification policy agreed.
- [ ] Validator dimensions, score, and failure threshold agreed.
- [ ] Storage retention and isolation rules implemented.
- [ ] Agent metadata is visible through `/api/agents` and application documentation.
- [ ] Failure paths are tested without external AI or Jira calls in CI.

## Security controls

- [ ] Threat model completed.
- [ ] Corporate SSO implemented.
- [ ] Role-based access controls implemented and tested.
- [ ] Secrets supplied through the approved secret manager.
- [ ] TLS and browser security headers enabled.
- [ ] Upload malware scanning implemented for production.
- [ ] Request-size, rate, and concurrency limits enforced at ingress.
- [ ] Logs verified to exclude customer content and credentials.
- [ ] External publishing remains explicit and human initiated.

## Infrastructure and operations

- [ ] Development, test, pilot, and production environments isolated.
- [ ] Managed database selected for multi-replica production deployment.
- [ ] Encryption, backup, restoration, retention, and deletion tested.
- [ ] Central logs, metrics, traces, dashboards, and alerts configured.
- [ ] Copilot, Jira, database, disk, latency, and error conditions monitored.
- [ ] Support hours, service objectives, severity definitions, and escalation paths approved.
- [ ] Incident, rollback, recovery, and provider-outage runbooks tested.

## Jira or test-management integration

- [ ] Jira Cloud, Jira Data Center, Xray, or Zephyr target selected.
- [ ] Dedicated least-privileged integration identity created.
- [ ] Browse, attachment, and comment permissions tested.
- [ ] Selected-case validation and unknown-ID rejection tested.
- [ ] Audit requirements for attachments and comments documented.

## Quality evaluation

- [ ] Representative, approved requirement dataset created.
- [ ] Expected test coverage and traceability baselines defined.
- [ ] Generated suites reviewed by qualified QA personnel.
- [ ] Accuracy, usefulness, duplication, edit rate, and automation classification measured.
- [ ] Accessibility, security, privacy, and performance testing completed.
- [ ] User acceptance testing completed by the pilot group.

## Pilot exit and production approval

- [ ] Pilot success measures achieved or deviations accepted by the sponsor.
- [ ] Outstanding high-risk findings resolved.
- [ ] Operating cost and premium-request forecasts accepted.
- [ ] User guidance and mandatory human-review training published.
- [ ] Production change, rollback, and support approvals recorded.
- [ ] Data deletion and access-removal procedures demonstrated.
