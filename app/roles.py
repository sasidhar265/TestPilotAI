"""Shared account roles and operation permissions for browser and API access."""

from typing import Literal, TypedDict

Role = Literal[
    "business_stakeholder",
    "product_owner",
    "developer",
    "release_manager",
    "ba",
    "functional_tester",
    "automation_tester",
    "non_functional_tester",
    "test_lead",
    "admin",
]
ROLE_LABELS = {
    "business_stakeholder": "Business stakeholder",
    "product_owner": "Product owner / Scrum master",
    "developer": "Developer",
    "release_manager": "Release manager / DevOps",
    "ba": "Business analyst",
    "functional_tester": "Functional tester",
    "automation_tester": "Automation tester",
    "non_functional_tester": "Non-functional tester",
    "test_lead": "Test lead",
    "admin": "Admin",
}
ROLE_TARGETS: dict[str, list[str]] = {
    "business_stakeholder": [],
    "product_owner": [],
    "developer": [],
    "release_manager": [],
    "ba": [],
    "functional_tester": ["manual"],
    "automation_tester": ["automation"],
    "non_functional_tester": ["non_functional"],
    "test_lead": ["manual", "automation", "non_functional", "both"],
    "admin": ["manual", "automation", "non_functional", "both"],
}


class RoleCapabilities(TypedDict):
    home_path: str
    role_label: str
    generation_targets: list[str]
    business_analysis: bool
    stories: bool
    scenarios: bool
    test_cases: bool
    automation: bool
    non_functional: bool
    admin: bool


def capabilities(role: str) -> RoleCapabilities:
    targets = ROLE_TARGETS.get(role, [])
    return {
        "home_path": "/",
        "role_label": ROLE_LABELS.get(role, role),
        "generation_targets": targets,
        "business_analysis": role in ROLE_LABELS,
        "stories": role in ROLE_LABELS,
        "scenarios": bool(targets),
        "test_cases": bool(targets),
        "automation": "automation" in targets,
        "non_functional": "non_functional" in targets,
        "admin": role == "admin",
    }
