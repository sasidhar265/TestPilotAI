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
        description="Upload the BRD, analyse requirements, and complete BA validation.",
        stages=["brd_upload", "requirements_analysis", "ba_validation", "clarification"],
        record_kinds=["requirement", "documentation"],
        agent_stages=["planning", "requirements"],
        links=[
            dict(label="Open requirements and BRD upload", href="/?view=requirements"),
            dict(label="Review business analysis", href="/sdlc?stage=requirements"),
        ],
    ),
    dict(
        id="business-approval",
        label="Business approval",
        description=(
            "The business stakeholder reviews the validated requirements and records a decision."
        ),
        stages=["stakeholder_approval"],
        record_kinds=["requirement", "documentation"],
        agent_stages=[],
        links=[dict(label="Review requirements source", href="/?view=requirements")],
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
        links=[dict(label="Open story design", href="/?view=stories")],
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
for _phase in PHASES:
    for _stage in _phase["stages"]:
        WORKFLOW[_stage]["phase"] = _phase["id"]
