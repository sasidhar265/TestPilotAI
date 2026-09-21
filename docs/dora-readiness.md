# DORA readiness assessment

Assessment date: 21 September 2026. Status: **compliance not established**.
Deployment, regulated entity, competent authority and service criticality have not been supplied.
This is an application gap assessment, not a legal opinion or organizational certification.
Requirements are mapped to the [official DORA regulation](https://eur-lex.europa.eu/eli/reg/2022/2554/oj).
Applicable technical standards and supervisory requirements must be assessed by the responsible
compliance team for the actual entity and deployment.

| Area | Application evidence | Open acceptance evidence / responsible role |
| --- | --- | --- |
| Governance and ICT risk (Articles 5–8) | Engineering standards and runtime configuration | Management: scope, accountable owners, asset/dependency inventory, risk assessment, approved policies and review dates |
| Protection and detection (Articles 9–10) | Production configuration guards, request limits, authentication, security headers, structured logging; lifecycle audit hash chain | Security/operations: deployed SSO/MFA and role/access review, encryption/key management, monitoring alerts, vulnerability remediation evidence, independent audit retention |
| Response and recovery (Articles 11–12) | Verified SQLite snapshot and isolated restore commands | Operations: business impact analysis, approved RTO/RPO, encrypted isolated/off-site copies, full-system recovery/switchover exercise with measured outcomes |
| Learning and communication (Articles 13–14) | Operations guidance | Incident owner: exercises, lessons learned, remediation owners, internal/external communication plan |
| Incident management and reporting (Articles 17–23) | Structured logs and bounded provider failures support investigation | Incident/compliance owners: incident register, detection/classification workflow, contacts, applicable reporting deadlines/templates, authority submission evidence and post-incident reviews |
| Resilience testing (Articles 24–27) | Repository regression tests; local audit and recovery checks | Security/QA: approved risk-based test programme, production-representative exercises, independent security testing and remediation; determine TLPT applicability |
| ICT third-party risk (Articles 28–30) | Copilot and optional Jira dependencies documented | Procurement/risk: complete supplier register including hosting/identity, contract review, subcontracting/location/concentration assessment, exit and substitution exercises |

Each open item requires an assigned person, target date, evidence location, reviewer and approval
date in the organization's controlled register. A successful local command does not close these
items. The readiness command deliberately reports them as open; it does not award a compliance score.

## Operator commands

Run from the repository with its installed Python environment. Examples use fresh destination paths;
create the parent backup/evidence directory with restricted access beforehand.

```sh
python -m app.resilience audit .agent-memory/stlc.db --export-checkpoint /secure/evidence/checkpoint.json
python -m app.resilience audit .agent-memory/stlc.db --checkpoint /secure/evidence/checkpoint.json
python -m app.resilience readiness .agent-memory/stlc.db
python -m app.resilience backup .agent-memory/stlc.db /secure/backups/stlc-release-001
python -m app.resilience restore /secure/backups/stlc-release-001 /secure/drills/stlc-release-001
```

Audit migration runs when the lifecycle store starts. Existing events are chained in sequence and
counted as `legacy_events`; this does not prove their historical authenticity. Startup checks the
chain and refuses a corrupted store. SQL triggers block ordinary UPDATE/DELETE operations.
An administrator able to rewrite the database can also rewrite the chain or remove triggers.
Export checkpoints to separately controlled immutable storage and compare them during monitoring
and recovery to detect rewritten or truncated history. A locally supplied file is trusted input,
not proof that independent storage exists. This chain protects lifecycle event fields, not full
record contents or every application/security action. Review retention and security-event logging
separately. Run verification on an approved schedule and alert on nonzero command exit status.

Backups use SQLite's online backup interface, including committed WAL content, and validate SQLite
integrity, foreign keys and any lifecycle audit chain. New bundle directories use mode 0700 and
files 0600 where supported. A completion manifest records checksum, size and audit checkpoint.
Restore verifies the bundle and creates a fresh directory with a restore report; it never replaces
the live database. Incomplete bundles/drills have no completion manifest/report and must not be
treated as successful. Checksums detect corruption, not malicious replacement of both data and
manifest: use separately protected storage, encryption and signed/immutable backup manifests.

Repeat backup for every configured SQLite store (suite memory, lifecycle, users, dashboard, usage).
Separate database snapshots are not an atomic application snapshot: quiesce application writes
for a coordinated recovery point. Also protect accepted output/evidence files, deployment
configuration and secret-manager recovery separately. Do not place backups under static/web roots.
Database timings do not establish application RTO/RPO. In an isolated environment, restore the
complete set, start the matching application revision, validate identity/access and lifecycle data,
exercise generation/export/integrations, measure recovery time and data loss, and obtain sign-off
before an operator performs a planned cutover. Retain drill evidence under the approved policy.

## Validation boundary

`tests/test_resilience.py` exercises legacy migration, append protection, tamper/truncation detection,
committed WAL recovery, damaged-bundle rejection, destination protection and operator commands.
These are isolated application-control tests. They do not execute generated API automation packs
or establish deployed resilience, provider continuity, incident reporting or DORA compliance.

Validation recorded on 21 September 2026:

- Full repository run: 458 passed, 21 skipped. Test-process overrides disabled local login and
  user secrets and selected the expected default model (`APP_PASSWORD='' SESSION_SECRET=''
  API_AUTH_TOKEN='' USER_SECRETS_ENABLED=false OPENAI_MODEL=gpt-5.4 python3 -m pytest -q -rs`).
  No deployment configuration was changed. Skips cover opt-in browser checks and unavailable or
  opt-in .NET, Behave and JMeter execution.
- After adding rejection of a JSON-null checkpoint file, the focused resilience run passed all
  14 tests (`python3 -m pytest -q tests/test_resilience.py`).
- Changed Python files pass Ruff lint/format checks; `mypy app` passes. Repository-wide Ruff
  reports a pre-existing E501 in `app/agents/output_agent.py:174`.
- Generated API packs were neither changed nor executed. These results are not ReqnRoll BDD
  evidence. Production recovery, security and provider-outage exercises remain outstanding.

## Resume point

The application-control implementation and local validation are complete. Next requires the
actual deployment and regulated-entity scope: assign owners to the open requirements above,
configure independently protected evidence/backup storage, run the complete recovery and incident
exercises, collect supplier evidence and obtain compliance review. Do not label the application
DORA-compliant based on this change or the readiness command.
