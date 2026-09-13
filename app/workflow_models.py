"""Reviewable, traceable handoffs for the five-stage quality workspace."""

from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from app.models import GenerateRequest

Criterion = Annotated[str, Field(min_length=3, max_length=2000)]


class Story(BaseModel):
    id: str = Field(pattern=r"^ST-\d+$")
    title: str = Field(min_length=3, max_length=200)
    narrative: str = Field(min_length=10, max_length=2000)
    source_excerpt: str = Field(min_length=10, max_length=2000)
    acceptance_criteria: list[Criterion] = Field(min_length=1, max_length=50)


class Stories(BaseModel):
    stories: list[Story] = Field(min_length=1, max_length=100)
    open_questions: list[str] = Field(default_factory=list, max_length=100)


class StoryHandoff(BaseModel):
    request: GenerateRequest
    stories: Stories

    @model_validator(mode="after")
    def grounded_stories(self) -> "StoryHandoff":
        ids = [story.id for story in self.stories.stories]
        if len(ids) != len(set(ids)):
            raise ValueError("Story IDs must be unique")
        source = " ".join(self.request.description.split())
        for story in self.stories.stories:
            if " ".join(story.source_excerpt.split()) not in source:
                raise ValueError(f"{story.id} must quote an excerpt from the source requirements")
        return self


class Scenario(BaseModel):
    id: str = Field(pattern=r"^SC-\d+$")
    story_id: str = Field(pattern=r"^ST-\d+$")
    title: str = Field(min_length=3, max_length=200)
    preconditions: list[str] = Field(default_factory=list, max_length=30)
    action: str = Field(min_length=3, max_length=2000)
    expected_result: str = Field(min_length=3, max_length=2000)
    acceptance_criteria: list[Criterion] = Field(min_length=1, max_length=50)


class Scenarios(BaseModel):
    scenarios: list[Scenario] = Field(min_length=1, max_length=500)
    open_questions: list[str] = Field(default_factory=list, max_length=100)


class ScenarioHandoff(StoryHandoff):
    scenarios: Scenarios

    @model_validator(mode="after")
    def linked_scenarios(self) -> "ScenarioHandoff":
        stories = {story.id: story for story in self.stories.stories}
        ids = [scenario.id for scenario in self.scenarios.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("Scenario IDs must be unique")
        covered: set[str] = set()
        for scenario in self.scenarios.scenarios:
            story = stories.get(scenario.story_id)
            if story is None:
                raise ValueError(f"{scenario.id} references an unknown story")
            if not set(scenario.acceptance_criteria) <= set(story.acceptance_criteria):
                raise ValueError(f"{scenario.id} must reference its story's acceptance criteria")
            covered.add(story.id)
        if covered != set(stories):
            raise ValueError("Every story needs at least one scenario")
        for story in stories.values():
            criteria = {
                criterion
                for scenario in self.scenarios.scenarios
                if scenario.story_id == story.id
                for criterion in scenario.acceptance_criteria
            }
            if criteria != set(story.acceptance_criteria):
                raise ValueError(f"Scenarios must cover every acceptance criterion in {story.id}")
        return self
