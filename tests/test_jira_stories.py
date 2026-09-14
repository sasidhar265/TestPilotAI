"""Verify Jira creation payloads and partial failure without creating real issues."""

import copy
import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.jira import JiraClient
from app.workflow_models import JiraStoriesRequest


@pytest.mark.asyncio
async def test_jira_creates_selected_stories_with_approval_and_stops_on_failure():
    fixtures = json.loads(Path("automation/Input/Workflow.Json").read_text())
    body = copy.deepcopy(fixtures["jira-approved"]["body"])
    for number in (2, 3):
        story = copy.deepcopy(body["stories"]["stories"][0])
        story["id"] = f"ST-00{number}"
        body["stories"]["stories"].append(story)
        body["selected_story_ids"].append(story["id"])
        body["approved_by"][story["id"]] = "Another Reviewer"
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        assert request.url.path == "/rest/api/3/issue"
        return (
            httpx.Response(201, json={"key": "TEST-123"})
            if len(calls) == 1
            else httpx.Response(400)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        result = await JiraClient(
            Settings(
                _env_file=None,
                jira_base_url="https://jira.example",
                jira_email="test@example.com",
                jira_api_token="fixture-token",
            ),
            transport,
        ).create_stories(JiraStoriesRequest.model_validate(body))
    assert len(calls) == 2
    assert [item["status"] for item in result] == ["created", "unconfirmed"]
    fields = calls[0]["fields"]
    assert fields["project"] == {"key": "TEST"}
    assert fields["issuetype"] == {"name": "Story"}
    assert fields["summary"] == body["stories"]["stories"][0]["title"]
    assert "Approved by: BDD Reviewer" in json.dumps(fields["description"])
    assert body["stories"]["stories"][0]["source_excerpt"] in json.dumps(fields["description"])
    assert result[0]["url"] == "https://jira.example/browse/TEST-123"
