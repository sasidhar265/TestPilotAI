from datetime import UTC, datetime

import httpx

from app.config import Settings
from app.exporter import suite_to_csv
from app.models import JiraPublishResult, TestSuite


class JiraClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client

    def _validate_config(self) -> None:
        missing = [
            name
            for name, value in {
                "JIRA_BASE_URL": self.settings.jira_base_url,
                "JIRA_EMAIL": self.settings.jira_email,
                "JIRA_API_TOKEN": self.settings.jira_api_token,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing Jira configuration: {', '.join(missing)}")

    async def publish(
        self, issue_key: str, suite: TestSuite, add_comment: bool = True
    ) -> JiraPublishResult:
        self._validate_config()
        base_url = self.settings.jira_base_url.rstrip("/")
        filename = f"test-cases-{issue_key}-{datetime.now(UTC):%Y%m%d-%H%M%S}.csv"
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(
            auth=(self.settings.jira_email, self.settings.jira_api_token), timeout=30
        )
        try:
            attachment = await client.post(
                f"{base_url}/rest/api/3/issue/{issue_key}/attachments",
                headers={"X-Atlassian-Token": "no-check", "Accept": "application/json"},
                files={"file": (filename, suite_to_csv(suite), "text/csv")},
            )
            attachment.raise_for_status()
            attachment_json = attachment.json()
            attachment_url = attachment_json[0].get("content") if attachment_json else None

            comment_added = False
            if add_comment:
                counts: dict[str, int] = {}
                for case in suite.test_cases:
                    counts[case.category.value] = counts.get(case.category.value, 0) + 1
                summary = ", ".join(f"{name}: {count}" for name, count in sorted(counts.items()))
                comment = await client.post(
                    f"{base_url}/rest/api/3/issue/{issue_key}/comment",
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                    json={
                        "body": {
                            "type": "doc",
                            "version": 1,
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": (
                                                f"AI-generated test suite attached as {filename} "
                                                f"({summary}). Please review before execution."
                                            ),
                                        }
                                    ],
                                }
                            ],
                        }
                    },
                )
                comment.raise_for_status()
                comment_added = True
            return JiraPublishResult(
                issue_key=issue_key,
                attachment_name=filename,
                attachment_url=attachment_url,
                comment_added=comment_added,
            )
        finally:
            if owns_client:
                await client.aclose()
