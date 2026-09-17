"""Recall validated workflow stages for matching requirements and reviewed handoffs."""

import hashlib
import json
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.agent_instructions import policy_fingerprint
from app.config import Settings
from app.memory import OrganizationalMemory
from app.observability import publish_lifecycle_event
from app.workspace_policy import load_business_rules, standards

Artifact = TypeVar("Artifact", bound=BaseModel)


class WorkflowKnowledgeAgent:
    def __init__(self, settings: Settings) -> None:
        self.memory = OrganizationalMemory(
            settings.organizational_memory_path, settings.organizational_memory_enabled
        )
        self.profile = settings.agent_profile

    def key(self, stage: str, source: BaseModel) -> str:
        # Preserve case, payload values, and reviewed text: these can change meaning.
        source_payload = source.model_dump(mode="json")
        self._remove_provenance(source_payload)
        identity = {
            "version": 1,
            "stage": stage,
            "source": source_payload,
            "profile": self.profile,
            "policy": policy_fingerprint(),
            "standards": standards("feature"),
            "rules": [rule.model_dump() for rule in load_business_rules()],
        }
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _remove_provenance(value: object) -> None:
        if isinstance(value, dict):
            value.pop("generation_source", None)
            value.pop("memory_key", None)
            for child in value.values():
                WorkflowKnowledgeAgent._remove_provenance(child)
        elif isinstance(value, list):
            for child in value:
                WorkflowKnowledgeAgent._remove_provenance(child)

    def recall(
        self, key: str, model: type[Artifact], validate: Callable[[Artifact], Artifact]
    ) -> Artifact | None:
        stored = self.memory.recall_workflow(key)
        if stored is None:
            return None
        try:
            result = validate(model.model_validate_json(stored))
        except (ValidationError, ValueError):
            return None
        publish_lifecycle_event(
            "Knowledge Agent",
            "recall_workflow",
            "success",
            f"Recreated {model.__name__.lower()} from validated organizational knowledge.",
        )
        return result.model_copy(
            update={"generation_source": "organizational-memory", "memory_key": key[:12]}
        )

    def remember(self, key: str, artifact: BaseModel) -> None:
        self.memory.remember_workflow(key, artifact.model_dump_json())
