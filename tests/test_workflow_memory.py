"""Duplicate requirements reuse durable stages without another provider call."""

from unittest.mock import AsyncMock

import pytest
from test_memory import suite
from test_workflow import handoff

from app.agents.workflow_agent import WorkflowAgent
from app.agents.workflow_agent import test_case_request as build_request
from app.config import Settings
from app.memory import OrganizationalMemory
from app.models import GenerationSource
from app.workflow_models import StoryHandoff


@pytest.mark.asyncio
async def test_duplicate_workflow_survives_new_agent_and_preserves_suite_identity(tmp_path):
    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    source = handoff()
    first = WorkflowAgent(settings)
    first.runner.generate_structured = AsyncMock(side_effect=[source.stories, source.scenarios])
    stories = await first.stories(source.request)
    scenarios = await first.scenarios(StoryHandoff(request=source.request, stories=stories))
    memory = OrganizationalMemory(settings.organizational_memory_path)
    memory.put(build_request(source), suite())

    second = WorkflowAgent(settings)
    second.runner.generate_structured = AsyncMock(side_effect=AssertionError("Provider called"))
    recalled_stories = await second.stories(source.request)
    recalled_scenarios = await second.scenarios(
        StoryHandoff(request=source.request, stories=recalled_stories)
    )
    assert recalled_stories == stories
    assert recalled_scenarios == scenarios
    recreated = source.model_copy(
        update={"stories": recalled_stories, "scenarios": recalled_scenarios}
    )
    recalled_suite = memory.get(build_request(recreated))
    assert recalled_suite.generation_source == GenerationSource.ORGANIZATIONAL_MEMORY
    assert recalled_suite.test_cases == suite().test_cases
    second.runner.generate_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_changed_requirement_and_reviewed_story_generate_fresh_stages(tmp_path):
    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    source = handoff()
    agent = WorkflowAgent(settings)
    agent.runner.generate_structured = AsyncMock(return_value=source.stories)
    await agent.stories(source.request)
    await agent.stories(source.request.model_copy(update={"additional_context": "New constraint"}))
    assert agent.runner.generate_structured.await_count == 2
    agent.runner.generate_structured = AsyncMock(return_value=source.scenarios)
    await agent.scenarios(source)
    edited = source.model_copy(deep=True)
    edited.stories.stories[0].title += " reviewed"
    await agent.scenarios(edited)
    assert agent.runner.generate_structured.await_count == 2


@pytest.mark.asyncio
async def test_disabled_memory_does_not_reuse_stages(tmp_path):
    settings = Settings(
        _env_file=None,
        organizational_memory_path=tmp_path / "memory.db",
        organizational_memory_enabled=False,
    )
    agent = WorkflowAgent(settings)
    source = handoff()
    agent.runner.generate_structured = AsyncMock(return_value=source.stories)
    await agent.stories(source.request)
    await agent.stories(source.request)
    assert agent.runner.generate_structured.await_count == 2
    assert not settings.organizational_memory_path.exists()


@pytest.mark.asyncio
async def test_invalid_stored_stories_are_regenerated(tmp_path):
    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    agent = WorkflowAgent(settings)
    source = handoff()
    key = agent.knowledge.key("stories", source.request)
    invalid = source.stories.model_copy(deep=True)
    invalid.stories[0].source_excerpt = "This is not in the original requirements."
    agent.knowledge.remember(key, invalid)
    agent.runner.generate_structured = AsyncMock(return_value=source.stories)
    assert await agent.stories(source.request) == source.stories
    agent.runner.generate_structured.assert_awaited_once()
