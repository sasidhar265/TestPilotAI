"""Server-owned lifecycle policy; agent execution never grants human approval."""

from typing import Any

# id, accountable roles, evidence required to leave, rejection/rework destination
_POLICY = (
    ("brd_upload", ("ba",), ("brd",), None),
    ("requirements_analysis", ("ba",), ("analysis",), "brd_upload"),
    ("ba_validation", ("ba",), ("ba_validation",), "clarification"),
    ("clarification", ("ba",), ("clarification",), "brd_upload"),
    ("stakeholder_approval", ("business_stakeholder",), (), "clarification"),
    ("backlog_generation", ("product_owner",), ("backlog",), "ba_validation"),
    ("backlog_refinement", ("product_owner",), ("refinement",), "backlog_generation"),
    ("prioritisation_estimation", ("product_owner",), ("estimation",), "backlog_refinement"),
    ("sprint_planning", ("product_owner",), ("assignment",), "backlog_refinement"),
    ("development", ("developer",), ("implementation",), "backlog_refinement"),
    ("code_review", ("developer",), ("pull_request", "code_review"), "development"),
    ("ci_checks", ("developer", "release_manager"), ("build",), "development"),
    (
        "qa_testing",
        ("functional_tester", "automation_tester", "test_lead"),
        ("test_execution",),
        "defect_resolution",
    ),
    ("defect_resolution", ("developer",), ("defect_fix",), "development"),
    (
        "qa_retesting",
        ("functional_tester", "automation_tester", "test_lead"),
        ("retest",),
        "defect_resolution",
    ),
    ("qa_signoff", ("test_lead",), (), "defect_resolution"),
    ("uat", ("business_stakeholder", "product_owner"), ("uat",), "defect_resolution"),
    (
        "release_readiness",
        ("release_manager",),
        ("release_checklist", "rollback_plan"),
        "development",
    ),
    ("release_approval", ("release_manager",), (), "release_readiness"),
    ("staging_validation", ("release_manager",), ("staging",), "release_readiness"),
    ("production_approval", ("release_manager",), (), "release_readiness"),
    ("production_deployment", ("release_manager",), ("deployment",), "release_readiness"),
    ("post_deployment_verification", ("release_manager",), ("verification",), "release_readiness"),
    ("release_closure", ("release_manager",), ("release_notes",), "release_readiness"),
    ("closed", ("release_manager",), (), None),
)
GATES = frozenset({"stakeholder_approval", "qa_signoff", "release_approval", "production_approval"})
_NEXT = {
    "ba_validation": "stakeholder_approval",
    "clarification": "requirements_analysis",
    "qa_testing": "qa_signoff",
    "defect_resolution": "qa_retesting",
    "qa_retesting": "qa_signoff",
}
WORKFLOW: dict[str, dict[str, Any]] = {
    row[0]: {
        "id": row[0],
        "label": row[0].replace("_", " ").capitalize(),
        "roles": list(row[1]),
        "evidence": list(row[2]),
        "reject_to": row[3],
        "next": _NEXT.get(row[0], _POLICY[index + 1][0] if index + 1 < len(_POLICY) else None),
        "human_approval": row[0] in GATES,
        "entry_criteria": "Previous stage completed against the current requirements version",
        "exit_criteria": "Required current-version evidence and accountable human decision",
    }
    for index, row in enumerate(_POLICY)
}


def can_act(role: str, stage: str) -> bool:
    return role == "admin" or role in WORKFLOW[stage]["roles"]


# Presentation groups belong to the same policy as the authoritative business stages.
# Selecting a workspace group never transitions a project.
PHASES: tuple[dict[str, Any], ...] = (
    dict(
        id="requirements",
        label="Requirements",
        description="Upload the BRD and run initial requirements analysis.",
        stages=["brd_upload", "requirements_analysis"],
        record_kinds=["requirement", "documentation"],
        agent_stages=["planning", "requirements"],
        links=[
            dict(label="Open requirements and BRD upload", href="/?view=requirements"),
            dict(label="Review business analysis", href="/sdlc?stage=requirements"),
        ],
    ),
    dict(
        id="business-approval",
        label="BA review & approval",
        description=(
            "Review the saved BRD and AI findings, resolve clarifications, "
            "and record the human BA decision."
        ),
        stages=["ba_validation", "clarification", "stakeholder_approval"],
        record_kinds=["requirement", "documentation"],
        agent_stages=[],
        links=[],
    ),
    dict(
        id="backlog",
        label="Backlog",
        description=(
            "Generate and refine stories, agree priorities and estimates, "
            "then plan sprint assignments."
        ),
        stages=[
            "backlog_generation",
            "backlog_refinement",
            "prioritisation_estimation",
            "sprint_planning",
        ],
        record_kinds=["epic", "story", "documentation"],
        agent_stages=["requirements"],
        links=[],
    ),
    dict(
        id="development",
        label="Development",
        description=(
            "Review architecture, implement assigned stories, review code, "
            "and complete build checks."
        ),
        stages=["development", "code_review", "ci_checks"],
        record_kinds=["story", "defect", "documentation"],
        agent_stages=["design", "development"],
        links=[
            dict(label="Review architecture", href="/sdlc?stage=design"),
            dict(label="Review implementation and build evidence", href="/sdlc?stage=development"),
        ],
    ),
    dict(
        id="qa",
        label="Quality assurance",
        description=(
            "Design and execute tests, resolve defects, retest fixes, and obtain QA sign-off."
        ),
        stages=["qa_testing", "defect_resolution", "qa_retesting", "qa_signoff"],
        record_kinds=["test_case", "defect", "documentation"],
        agent_stages=["testing"],
        links=[
            dict(label="Design test scenarios", href="/?view=scenarios"),
            dict(label="Review test cases", href="/?view=test-cases"),
            dict(label="Open automation packs", href="/?view=automation"),
            dict(label="Review execution reports", href="/progress"),
        ],
    ),
    dict(
        id="release",
        label="Release readiness",
        description=(
            "Complete user acceptance testing, the release checklist, "
            "rollback planning, and release approval."
        ),
        stages=["uat", "release_readiness", "release_approval"],
        record_kinds=["release", "documentation"],
        agent_stages=["release"],
        links=[dict(label="Review release evidence", href="/sdlc?stage=release")],
    ),
    dict(
        id="deployment",
        label="Deployment",
        description=(
            "Validate staging, obtain human production approval, deploy, and "
            "verify the released revision."
        ),
        stages=[
            "staging_validation",
            "production_approval",
            "production_deployment",
            "post_deployment_verification",
        ],
        record_kinds=["release", "documentation"],
        agent_stages=["release", "operations"],
        links=[
            dict(label="Review deployment evidence", href="/sdlc?phase=deployment&stage=release")
        ],
    ),
    dict(
        id="closure",
        label="Closure",
        description=(
            "Review release notes, operational handover, documentation, and "
            "the final release closure."
        ),
        stages=["release_closure", "closed"],
        record_kinds=["release", "documentation"],
        agent_stages=["operations"],
        links=[
            dict(label="Review operations and handover", href="/sdlc?stage=operations"),
            dict(label="Open documentation centre", href="/documentation"),
        ],
    ),
)
# Responsibility and artifact contracts are shared by navigation, project snapshots
# and AI instructions. They describe ownership, never grant transition authority.
DELIVERY_RESPONSIBILITIES = {
    "requirements": dict(
        ai=(
            "Extract requirements from the PDF or Word BRD; identify gaps, ambiguities, "
            "conflicts and dependencies."
        ),
        human=(
            "The BA checks extraction against the source and confirms correctness before handoff."
        ),
        artifacts=["Versioned BRD", "Extracted requirements", "Gap and dependency analysis"],
    ),
    "business-approval": dict(
        ai=(
            "Recommend corrections and clarification questions with references to the "
            "current BRD version."
        ),
        human=(
            "The BA validates corrections; the business stakeholder signs off the "
            "requirements baseline."
        ),
        artifacts=["BA validation", "Clarification decisions", "Requirements sign-off"],
    ),
    "backlog": dict(
        ai=(
            "Draft epics, user stories, acceptance criteria, priorities and estimates "
            "from approved requirements."
        ),
        human=(
            "The PO and team refine stories, agree priorities and estimates, and "
            "approve sprint assignments."
        ),
        artifacts=["Epics and stories", "Acceptance criteria", "Refinement and planning decisions"],
    ),
    "development": dict(
        ai=(
            "Assist with implementation and unit tests; draft design notes and code "
            "review findings."
        ),
        human=(
            "The developer picks up an approved story, implements code, opens a pull "
            "request and reviews changes."
        ),
        artifacts=[
            "Design notes",
            "Implementation and unit tests",
            "Pull request and code review",
            "Build evidence",
        ],
    ),
    "qa": dict(
        ai=(
            "Draft test cases and API/UI automation; summarise execution evidence and "
            "suggest defect investigations."
        ),
        human=(
            "QA executes tests, investigates failures, manages defects, retests fixes "
            "and provides QA sign-off."
        ),
        artifacts=[
            "Test cases and automation drafts",
            "Test execution evidence",
            "Defects and retests",
            "QA sign-off",
        ],
    ),
    "release": dict(
        ai=(
            "Summarise business acceptance, regression and security evidence, release "
            "risks and rollback readiness."
        ),
        human=(
            "Business owners accept UAT; the release manager reviews readiness and "
            "approves release progression."
        ),
        artifacts=[
            "UAT acceptance",
            "Regression and security evidence",
            "Release checklist",
            "Rollback plan",
        ],
    ),
    "deployment": dict(
        ai=(
            "Prepare deployment and monitoring summaries from configured CI/CD receipts "
            "and verification results."
        ),
        human=(
            "The release manager validates staging, approves production deployment and "
            "verifies monitoring and rollback readiness."
        ),
        artifacts=[
            "Staging validation",
            "Production approval",
            "CI/CD deployment receipt",
            "Monitoring and verification evidence",
        ],
    ),
    "closure": dict(
        ai=(
            "Produce and update draft release notes, operational handover and "
            "documentation from recorded evidence."
        ),
        human=(
            "Artifact owners validate and publish documentation; the release manager "
            "closes the release."
        ),
        artifacts=[
            "Release notes",
            "Operational handover",
            "Validated documentation",
            "Audit history",
        ],
    ),
}
DOCUMENTATION_POLICY = dict(
    ai=(
        "Produce and update draft artifacts throughout delivery, preserving source and "
        "version references."
    ),
    human=(
        "Artifact owners validate and publish drafts. AI generation does not constitute "
        "approval or publication."
    ),
    artifacts=[
        "Requirements traceability",
        "Design notes",
        "Test evidence",
        "Release notes",
        "Audit history",
    ],
)
for _phase in PHASES:
    _phase["responsibilities"] = DELIVERY_RESPONSIBILITIES[_phase["id"]]
    _phase["documentation"] = DOCUMENTATION_POLICY
    for _stage in _phase["stages"]:
        WORKFLOW[_stage]["phase"] = _phase["id"]
