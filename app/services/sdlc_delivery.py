"""Durable sequential delivery coordinator. Stage ownership stays with executable agents."""

import asyncio
from contextlib import suppress
from typing import Any

from app.agents.sdlc_agent import AGENT_CATALOG, SDLCStageAgents, StageBlocked
from app.config import Settings
from app.lifecycle_workflow import PHASES, WORKFLOW
from app.sdlc_models import DeliveryMission
from app.services.sdlc import SDLCError, SDLCStore
from app.services.sdlc_tools import DeliveryTools

ACTIVE_TASKS: dict[str, asyncio.Task[None]] = {}
STAGE_TOOL_LOCKS = {"testing": asyncio.Lock(), "release": asyncio.Lock()}


def release_worker(identifier: str, task: asyncio.Task[None]) -> None:
    if ACTIVE_TASKS.get(identifier) is task:
        ACTIVE_TASKS.pop(identifier, None)
    if not task.cancelled():
        task.exception()  # Retrieve terminal errors; run evidence is recorded by execute().


def capabilities(settings: Settings) -> dict[str, Any]:
    configured = dict(
        repository=settings.sdlc_repository_path is not None or settings.sdlc_greenfield_enabled,
        build=bool(settings.sdlc_build_command),
        preview=bool(
            settings.sdlc_preview_command
            and settings.sdlc_preview_base_url
            and settings.sdlc_preview_health_url
        ),
        staging=bool(settings.sdlc_staging_command and settings.sdlc_staging_health_url),
        production=bool(
            settings.sdlc_production_enabled
            and settings.sdlc_production_command
            and settings.sdlc_production_health_url
        ),
        rollback=bool(settings.sdlc_rollback_command),
    )
    return dict(
        agents=AGENT_CATALOG,
        workflow=dict(phases=list(PHASES), definition=list(WORKFLOW.values())),
        configured=configured,
        models={"codex": "gpt-6-astra", "github-copilot": "claude-haiku-4.5"},
        production_policy="enabled" if settings.sdlc_production_enabled else "disabled",
    )


class DeliveryCoordinator:
    def __init__(self, settings: Settings, store: SDLCStore):
        self.settings, self.store = settings, store

    def start(self, project: str, owner: str, mission: DeliveryMission) -> dict[str, Any]:
        self.store.recover_runs(owner)
        if mission.requirements_version is None:
            raise SDLCError("Save Requirements before starting delivery")
        if len(ACTIVE_TASKS) >= self.settings.sdlc_max_active_runs:
            raise SDLCError("Delivery workers are at capacity; retry when a run finishes")
        record = self.store.create_run(project, owner, mission.model_dump(mode="json"))
        task = asyncio.create_task(self.execute(record["id"], owner))
        ACTIVE_TASKS[record["id"]] = task
        task.add_done_callback(lambda completed: release_worker(record["id"], completed))
        return record

    def resume(self, identifier: str, owner: str) -> dict[str, Any]:
        self.store.recover_runs(owner)
        if len(ACTIVE_TASKS) >= self.settings.sdlc_max_active_runs:
            raise SDLCError("Delivery workers are at capacity")
        previous = ACTIVE_TASKS.get(identifier)
        if previous and not previous.done():
            raise SDLCError("Previous worker is still exiting; retry resume shortly")
        current = self.store.run(identifier, owner)
        owner = current["owner"]
        version = current["mission"].get("requirements_version")
        if version:
            latest = next(
                (
                    item
                    for item in self.store.snapshot(current["project"], owner)["artifacts"]
                    if item["stage"] == "requirements-input"
                ),
                None,
            )
            if latest is None or latest["version"] != version:
                raise SDLCError("Requirements changed. Start a new run from the latest baseline.")
        record = self.store.resume_run(identifier, owner)
        task = asyncio.create_task(self.execute(identifier, owner))
        ACTIVE_TASKS[identifier] = task
        task.add_done_callback(lambda completed: release_worker(identifier, completed))
        return record

    async def cancel(self, identifier: str, owner: str) -> dict[str, Any]:
        current = self.store.run(identifier, owner)
        owner = current["owner"]
        if current["status"] not in {"queued", "running", "cancelling"}:
            return current
        self.store.update_run(identifier, owner, cancel_requested=True, status="cancelling")
        task = ACTIVE_TASKS.get(identifier)
        if current["status"] == "queued":
            self.store.update_run(identifier, owner, status="cancelled")
        # Record promotion cancellation and stop at the next boundary.
        if (
            task
            and current["stage"] not in {"release", "operations"}
            and not current.get("action", "").startswith("deploy:")
        ):
            task.cancel()
        return self.store.run(identifier, owner)

    async def heartbeat(self, identifier: str, owner: str) -> None:
        while True:
            await asyncio.sleep(10)
            self.store.update_run(identifier, owner)

    def persist(
        self,
        project: str,
        owner: str,
        stage: str,
        content: dict[str, Any],
        artifacts: dict[str, Any],
        links: list[dict[str, Any]],
        base_version: int,
    ) -> dict[str, Any]:
        content.update(agent=stage, agent_validation="passed", source="agent-delivery")
        result = self.store.save(
            project, owner, stage, content, base_version, links, run_id=content["run_id"]
        )
        artifacts[stage] = result["content"]
        return result

    async def execute(self, identifier: str, owner: str) -> None:
        try:
            run = self.store.claim_run(identifier, owner)
        except SDLCError:
            return
        project = run["project"]
        mission = DeliveryMission.model_validate(run["mission"])
        tools = DeliveryTools(self.settings, project, identifier)
        tools.cancel_requested = lambda: self.store.run(identifier, owner)["cancel_requested"]

        def record_action(action: str) -> None:
            if action in {"deploy:staging", "deploy:production"}:
                from app.services.project_lifecycle import ProjectLifecycle

                ProjectLifecycle(self.store).require_deployment(
                    project, owner, action.split(":")[1]
                )
            if action.startswith("deploy:"):
                snapshot = self.store.snapshot(project, owner)
                for link in links:
                    latest = next(
                        item for item in snapshot["artifacts"] if item["stage"] == link["stage"]
                    )
                    if latest["version"] != link["version"]:
                        raise StageBlocked(
                            "Deployment source versions changed; reconcile before promotion"
                        )
            current = self.store.update_run(identifier, owner, action=action)
            if action != "idle":
                self.store.run_event(
                    identifier,
                    owner,
                    current["stage"],
                    "specialist_action",
                    "running",
                    action.replace("agent:", "Agent: ").replace("deploy:", "Deploy: "),
                )

        tools.on_action = record_action
        agents = SDLCStageAgents(self.settings, mission, tools)
        heartbeat = asyncio.create_task(self.heartbeat(identifier, owner))
        artifacts: dict[str, Any] = run.get("artifacts", {})
        links: list[dict[str, Any]] = run.get("artifact_versions", [])
        if mission.requirements_version and not links:
            links = [{"stage": "requirements-input", "version": mission.requirements_version}]
        completed: list[str] = run.get("completed", [])
        stage = "planning"
        end = {
            "design": "design",
            "tested": "testing",
            "staging": "operations",
            "production": "operations",
        }[mission.target]
        try:
            for descriptor in AGENT_CATALOG:
                stage = descriptor["stage"]
                if stage in completed:
                    continue
                current = self.store.run(identifier, owner)
                if current["cancel_requested"]:
                    raise asyncio.CancelledError()
                if stage in {"development", "testing", "release"}:
                    from app.services.project_lifecycle import ProjectLifecycle

                    lifecycle = ProjectLifecycle(self.store).snapshot(project, owner, "admin")
                    minimum = {
                        "development": "development",
                        "testing": "qa_testing",
                        "release": "staging_validation",
                    }[stage]
                    if list(WORKFLOW).index(lifecycle["stage"]) < list(WORKFLOW).index(minimum):
                        raise StageBlocked(
                            f"Complete human workflow gates through {minimum} "
                            "before this agent continues"
                        )
                self.store.update_run(identifier, owner, stage=stage)
                self.store.run_event(
                    identifier,
                    owner,
                    stage,
                    "agent_started",
                    "running",
                    descriptor["name"] + " took ownership",
                )
                # Every downstream task consumes the exact versioned outputs of this run.
                for link in links:
                    latest = next(
                        item
                        for item in self.store.snapshot(project, owner)["artifacts"]
                        if item["stage"] == link["stage"]
                    )
                    if latest["version"] != link["version"]:
                        raise StageBlocked(
                            "Upstream artifact changed; reconcile its baseline before continuing"
                        )
                existing = next(
                    (
                        item
                        for item in self.store.snapshot(project, owner)["artifacts"]
                        if item["stage"] == stage
                    ),
                    None,
                )
                base_version = existing["version"] if existing else 0
                context = dict(mission=mission.model_dump(mode="json"), artifacts=artifacts)
                if stage in STAGE_TOOL_LOCKS:
                    record_action("Wait for shared environment ownership")
                    async with STAGE_TOOL_LOCKS[stage]:
                        if self.store.run(identifier, owner)["cancel_requested"]:
                            raise asyncio.CancelledError()
                        content = await getattr(agents, stage)(context)
                else:
                    content = await getattr(agents, stage)(context)
                content["run_id"] = identifier
                revision = self.persist(
                    project, owner, stage, content, artifacts, links.copy(), base_version
                )
                links.append(dict(stage=stage, version=revision["version"]))
                completed.append(stage)
                self.store.update_run(
                    identifier,
                    owner,
                    completed=completed,
                    artifacts=artifacts,
                    artifact_versions=links.copy(),
                )
                self.store.run_event(
                    identifier,
                    owner,
                    stage,
                    "agent_completed",
                    "passed",
                    content.get("summary", f"{descriptor['name']} produced a validated handoff"),
                )
                if stage == "testing" or (stage == "requirements" and "request" in content):
                    self.save_testing_handoff(project, owner, artifacts)
                if stage == end:
                    break
            if self.store.run(identifier, owner)["cancel_requested"]:
                raise asyncio.CancelledError()
            self.store.update_run(identifier, owner, status="completed", error=None)
            self.store.run_event(
                identifier,
                owner,
                stage,
                "delivery_completed",
                "completed",
                "Requested delivery target completed with recorded evidence: " + mission.target,
            )
        except asyncio.CancelledError:
            cancelled = self.store.run(identifier, owner)["cancel_requested"]
            self.store.update_run(
                identifier,
                owner,
                status="cancelled" if cancelled else "interrupted",
                error="Worker stopped; artifacts and deployment receipts are retained",
            )
            self.store.run_event(
                identifier,
                owner,
                stage,
                "cancelled" if cancelled else "interrupted",
                "cancelled" if cancelled else "interrupted",
                "Worker stopped; inspect retained evidence before resuming",
            )
        except (StageBlocked, SDLCError) as error:
            self.store.update_run(
                identifier,
                owner,
                status="blocked",
                error=tools.redact(str(error)),
                blocking_evidence=getattr(error, "evidence", {}),
            )
            self.store.run_event(
                identifier, owner, stage, "gate_blocked", "blocked", tools.redact(str(error))
            )
        except Exception as error:
            # The provider/command may include credentials in errors; redact before persisting.
            self.store.update_run(
                identifier, owner, status="failed", error=tools.redact(str(error))
            )
            self.store.run_event(
                identifier, owner, stage, "agent_failed", "failed", tools.redact(str(error))
            )
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    def save_testing_handoff(self, project: str, owner: str, artifacts: dict[str, Any]) -> None:
        requirements, testing = artifacts["requirements"], artifacts.get("testing", {})
        # Agent validation does not fabricate human business acceptance.
        content = dict(
            version=1,
            controls={
                "description": requirements["request"]["description"],
                "sdlc-constraints": requirements["request"].get("additional_context", ""),
                "llm-model": requirements["request"]["llm_model"],
            },
            state=dict(
                request=requirements["request"],
                stories=requirements["stories"],
                scenarios=testing.get("scenarios"),
                storiesReviewed=False,
                scenariosReviewed=False,
                acceptedStories=[],
                jiraStories=[],
                dirtyStories=[],
                acceptedScenarios=[],
                dirtyScenarios=[],
                busy=False,
                plan=None,
                runReport=testing.get("execution"),
                stage=4 if testing else 2,
            ),
            suite=testing.get("suite"),
            validationReport=testing.get("validation"),
            reviewSourceRequest=testing.get("source_request", requirements["request"]),
            executionSummary=None,
            stepDefinitionArtifact=testing.get("pack"),
            savedBaReport=requirements["ba_report"],
            savedRequirementsReport=requirements["requirements_report"],
            latestBrdText=None,
            caseSelections=[],
        )
        snapshot = self.store.snapshot(project, owner)
        previous = next(
            (item for item in snapshot["artifacts"] if item["stage"] == "workflow"), None
        )
        self.store.save(
            project, owner, "workflow", content, previous["version"] if previous else 0, []
        )
