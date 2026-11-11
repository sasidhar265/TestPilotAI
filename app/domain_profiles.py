"""Admin-managed domain guidance and profile selection, independent of source files."""

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.auth import SESSION_COOKIE, session_username
from app.config import Settings, get_settings
from app.knowledge_agents import KnowledgeAgentError

DIRECTORY = Path(__file__).parent.parent / ".github/agent-profiles"
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
router = APIRouter()
Config = Annotated[Settings, Depends(get_settings)]


class DomainProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$", max_length=64)
    name: str = Field(min_length=3, max_length=100)
    description: str = Field(min_length=10, max_length=1000)
    instructions: str = Field(min_length=20, max_length=8000)
    baseline: dict[str, Any] = Field(default_factory=lambda: {"sources": []})
    expected_revision: int = Field(default=0, ge=0)
    review_note: str = Field(min_length=10, max_length=1000)
    confirmed: Literal[True]


class ProfileSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$", max_length=64)
    expected_revision: int = Field(ge=0)


class DomainProfileStore:
    def __init__(self, user_database: Path):
        self.path = user_database.with_name("domain_profiles.db")
        self.baselines = user_database.parent / "profile-baselines"

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.executescript(
            "CREATE TABLE IF NOT EXISTS domain_profiles "
            "(id TEXT PRIMARY KEY, document TEXT NOT NULL, revision INTEGER NOT NULL, "
            "updated_by TEXT NOT NULL, updated_at TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS domain_selection "
            "(id INTEGER PRIMARY KEY, profile TEXT NOT NULL, revision INTEGER NOT NULL);"
        )
        return connection

    def custom(self, identifier: str) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM domain_profiles WHERE id=?", (identifier,)
            ).fetchone()
            return (
                (
                    json.loads(row["document"])
                    | {
                        "revision": row["revision"],
                        "updated_by": row["updated_by"],
                        "updated_at": row["updated_at"],
                        "builtin": False,
                    }
                )
                if row
                else None
            )

    def selection(self, fallback: str) -> dict[str, Any]:
        if self.path.exists():
            with closing(self.connect()) as connection:
                row = connection.execute(
                    "SELECT profile,revision FROM domain_selection WHERE id=1"
                ).fetchone()
                if row:
                    return dict(row)
        return {"profile": fallback, "revision": 0}

    def inventory(self) -> list[dict[str, Any]]:
        profiles = []
        for path in sorted(DIRECTORY.glob("*/profile.md")):
            text = path.read_text()
            profiles.append(
                {
                    "id": path.parent.name,
                    "name": text.splitlines()[0].removeprefix("# "),
                    "description": (
                        "Built-in project guidance. Base application policies remain mandatory."
                    ),
                    "instructions": text,
                    "baseline": {"sources": []},
                    "builtin": True,
                    "revision": 0,
                }
            )
        if self.path.exists():
            with closing(self.connect()) as connection:
                identifiers = [
                    row[0]
                    for row in connection.execute("SELECT id FROM domain_profiles ORDER BY id")
                ]
            profiles.extend(item for identifier in identifiers if (item := self.custom(identifier)))
        return profiles

    def baseline_path(self, identifier: str) -> Path:
        if not SLUG.fullmatch(identifier):
            raise KnowledgeAgentError(422, "Invalid profile ID")
        return self.baselines / (identifier + ".json")

    def write_baseline(self, identifier: str, baseline: dict[str, Any]) -> None:
        path = self.baseline_path(identifier)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(baseline, stream)
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def save(self, profile: DomainProfile, actor: str) -> dict[str, Any]:
        from pydantic import ValidationError

        from app.agents.requirements_validation import BusinessBaseline

        if (DIRECTORY / profile.id).exists():
            raise KnowledgeAgentError(
                409, "Built-in profiles cannot be overwritten. Create a new profile ID"
            )
        try:
            baseline = BusinessBaseline.model_validate(profile.baseline).model_dump(mode="json")
        except ValidationError as error:
            raise KnowledgeAgentError(
                422,
                "Business baseline JSON is invalid. Preserve source IDs, status, reviewer, "
                "effective dates and content",
            ) from error
        if len(json.dumps(baseline)) > 500000:
            raise KnowledgeAgentError(422, "Business baseline exceeds 500 KB")
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT revision FROM domain_profiles WHERE id=?", (profile.id,)
            ).fetchone()
            revision = row[0] if row else 0
            if revision != profile.expected_revision:
                raise KnowledgeAgentError(409, "This profile changed. Reload before saving")
            if (
                not row
                and connection.execute("SELECT count(*) FROM domain_profiles").fetchone()[0] >= 100
            ):
                raise KnowledgeAgentError(409, "The custom profile limit has been reached")
            document = profile.model_dump(exclude={"expected_revision", "confirmed"}) | {
                "baseline": baseline
            }
            connection.execute(
                "INSERT INTO domain_profiles VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "document=excluded.document,revision=excluded.revision,"
                "updated_by=excluded.updated_by,updated_at=excluded.updated_at",
                (
                    profile.id,
                    json.dumps(document),
                    revision + 1,
                    actor,
                    datetime.now(UTC).isoformat(),
                ),
            )
        result = self.custom(profile.id)
        assert result is not None
        return result

    def activate(self, selection: ProfileSelection, fallback: str) -> dict[str, Any]:
        profiles = {item["id"]: item for item in self.inventory()}
        if selection.profile not in profiles:
            raise KnowledgeAgentError(422, "Select an existing profile")
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT revision FROM domain_selection WHERE id=1").fetchone()
            revision = row[0] if row else 0
            if revision != selection.expected_revision:
                raise KnowledgeAgentError(
                    409, "The selected profile changed. Reload before applying"
                )
            if (
                selection.profile != "auto-finance-quotation"
                and profiles[selection.profile]["builtin"]
                and not self.baseline_path(selection.profile).exists()
            ):
                self.write_baseline(selection.profile, {"sources": []})
            connection.execute(
                "INSERT INTO domain_selection VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET "
                "profile=excluded.profile,revision=excluded.revision",
                (selection.profile, revision + 1),
            )
        return self.selection(fallback)

    def delete(self, identifier: str, expected: int, fallback: str) -> None:
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT revision FROM domain_profiles WHERE id=?", (identifier,)
            ).fetchone()
            active = connection.execute(
                "SELECT profile FROM domain_selection WHERE id=1"
            ).fetchone()
            if row is None:
                raise KnowledgeAgentError(404, "Custom profile not found")
            if row[0] != expected or (active[0] if active else fallback) == identifier:
                raise KnowledgeAgentError(409, "Select another profile and reload before deleting")
            connection.execute("DELETE FROM domain_profiles WHERE id=?", (identifier,))
            self.baseline_path(identifier).unlink(missing_ok=True)


def effective_settings(settings: Settings) -> Settings:
    storage = DomainProfileStore(settings.user_database_path)
    selection = storage.selection(settings.agent_profile)
    if not selection["revision"]:
        return settings
    identifier = selection["profile"]
    if identifier == "auto-finance-quotation":
        baseline = (
            settings.requirements_baseline_path
            if settings.agent_profile == identifier
            else Path("workspace/requirements-baseline.json")
        )
    else:
        baseline = storage.baseline_path(identifier)
    return settings.model_copy(
        update={
            "agent_profile": identifier,
            "auto_finance_domain_enabled": identifier == "auto-finance-quotation"
            and settings.auto_finance_domain_enabled,
            "requirements_baseline_path": baseline,
        }
    )


def baseline_bytes(settings: Settings) -> bytes:
    profile = DomainProfileStore(settings.user_database_path).custom(settings.agent_profile)
    if profile:
        return json.dumps(profile["baseline"], sort_keys=True).encode()
    return settings.requirements_baseline_path.read_bytes()


def profile_fingerprint(settings: Settings) -> str:
    profile = DomainProfileStore(settings.user_database_path).custom(settings.agent_profile)
    return hashlib.sha256(
        json.dumps(
            {"profile": settings.agent_profile, "definition": profile}, sort_keys=True
        ).encode()
    ).hexdigest()


@router.get("/api/domain-profiles")
async def list_domain_profiles(settings: Config) -> dict[str, Any]:
    storage = DomainProfileStore(settings.user_database_path)
    return {
        "profiles": storage.inventory(),
        "selection": storage.selection(settings.agent_profile),
        "finance_enabled": settings.auto_finance_domain_enabled,
    }


@router.post("/api/admin/domain-profiles", status_code=201)
async def save_domain_profile(
    profile: DomainProfile, request: Request, settings: Config
) -> dict[str, Any]:
    actor = session_username(request.cookies.get(SESSION_COOKIE, ""), settings) or "service-admin"
    return DomainProfileStore(settings.user_database_path).save(profile, actor)


@router.put("/api/admin/domain-profiles/selection")
async def activate_domain_profile(selection: ProfileSelection, settings: Config) -> dict[str, Any]:
    return DomainProfileStore(settings.user_database_path).activate(
        selection, settings.agent_profile
    )


@router.delete("/api/admin/domain-profiles/{identifier}")
async def delete_domain_profile(
    identifier: str, expected_revision: int, settings: Config
) -> dict[str, bool]:
    DomainProfileStore(settings.user_database_path).delete(
        identifier, expected_revision, settings.agent_profile
    )
    return {"deleted": True}
