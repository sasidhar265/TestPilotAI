# Workflow and approval boundaries

Work in the stage and response schema selected by the application. Requirements, stories, scenarios,
test cases, automation files and execution results are different artifacts. Preserve source links,
IDs and the current reviewed handoff when creating downstream work.

Do not manufacture reviewers, acceptance records, approval timestamps, Quality Gate decisions or
business-source authority. Changed reviewed content needs the applicable approval and downstream
validation again. A passing design report is not human acceptance, business approval or a test run.

Knowledge changes follow draft, review and explicit publication. Only the active published revision
contributes to its matching profile/stages. New drafts do not activate themselves; rollback uses a
previously published revision. A local custom-agent description does not install executable tools.

Respect server-issued role capabilities. Hidden navigation is presentation, not authorization.
Preparing or reviewing an artifact does not authorize Jira publication, execution, settings changes
or any other external mutation; use the existing user action and server checks for that operation.
Do not add new confirmation steps to ordinary generation beyond the application's actual workflow.

Enforcement: role capabilities and API authorization live in `app/roles.py` and `app/role_access.py`;
handoff validation, knowledge revision checks and acceptance services remain the executable owners.
These instructions do not change which roles may call an endpoint.
