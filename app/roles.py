"""Shared account roles and operation permissions for browser and API access."""

from typing import Literal

Role = Literal[
    "ba", "functional_tester", "automation_tester", "non_functional_tester", "test_lead", "admin"
]
ROLE_LABELS = {
    "ba": "Business analyst",
    "functional_tester": "Functional tester",
    "automation_tester": "Automation tester",
    "non_functional_tester": "Non-functional tester",
    "test_lead": "Test lead",
    "admin": "Admin",
}
ROLE_TARGETS = {
    "ba": [],
    "functional_tester": ["manual"],
    "automation_tester": ["automation"],
    "non_functional_tester": ["non_functional"],
    "test_lead": ["manual", "automation", "non_functional", "both"],
    "admin": ["manual", "automation", "non_functional", "both"],
}


def capabilities(role: str) -> dict:
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
