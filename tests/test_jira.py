import asyncio

import httpx

from app.config import Settings
from app.jira import JiraClient, jira_document_to_text


def test_jira_document_to_text_flattens_adf() -> None:
    document = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "First line"}]},
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "Done"}]}
                        ],
                    }
                ],
            },
        ],
    }

    assert jira_document_to_text(document) == "First line\n- Done"


def test_read_requirement_discovers_acceptance_criteria_field() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/field"):
            return httpx.Response(
                200,
                json=[{"id": "customfield_10101", "name": "Acceptance Criteria"}],
            )
        assert request.url.params["fields"] == "summary,description,customfield_10101"
        return httpx.Response(
            200,
            json={
                "fields": {
                    "summary": "Reset a password",
                    "description": "As a customer I can request a reset.",
                    "customfield_10101": (
                        "A reset link expires after 15 minutes\nUnknown users are safe"
                    ),
                }
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        jira_base_url="https://example.atlassian.net",
        jira_email="qa@example.com",
        jira_api_token="secret",
    )
    try:
        result = asyncio.run(JiraClient(settings, client).read_requirement("QA-42"))
    finally:
        asyncio.run(client.aclose())

    assert result.issue_key == "QA-42"
    assert result.acceptance_criteria == [
        "A reset link expires after 15 minutes",
        "Unknown users are safe",
    ]
    assert "AC-001: A reset link expires" in result.generation_description
