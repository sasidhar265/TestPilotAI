"""Reviewable, traceable handoffs for the five-stage quality workspace."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

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
    generation_source: str = "copilot"
    memory_key: str | None = None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Stories):
            return NotImplemented
        return self.stories == other.stories and self.open_questions == other.open_questions


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
            excerpt = " ".join(story.source_excerpt.split())
            if excerpt not in source:
                raise ValueError(
                    f"{story.id} source_excerpt must be an exact, contiguous quote of at least "
                    "10 characters from request.description (whitespace may vary); "
                    f"received: {story.source_excerpt!r}"
                )
        return self


class JiraStoriesRequest(StoryHandoff):
    project_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=100)
    issue_type: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    selected_story_ids: list[str] = Field(min_length=1, max_length=100)
    approved_by: dict[
        str, Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    ]

    @model_validator(mode="after")
    def approved_selection(self) -> "JiraStoriesRequest":
        selected = set(self.selected_story_ids)
        if len(selected) != len(self.selected_story_ids):
            raise ValueError("Selected story IDs must be unique")
        if not selected <= {story.id for story in self.stories.stories}:
            raise ValueError("Unknown selected story IDs")
        if not selected <= self.approved_by.keys():
            raise ValueError("Every selected story must be approved with a reviewer name")
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
    generation_source: str = "copilot"
    memory_key: str | None = None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Scenarios):
            return NotImplemented
        return self.scenarios == other.scenarios and self.open_questions == other.open_questions


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
