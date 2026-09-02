from datetime import UTC, datetime

import httpx

from app.config import Settings
from app.exporter import suite_to_csv
from app.models import JiraPublishResult, JiraRequirement, TestSuite


def jira_document_to_text(value: object) -> str:
    """Flatten Jira Cloud ADF (or plain custom-field content) into readable text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(filter(None, (jira_document_to_text(item) for item in value))).strip()
    if not isinstance(value, dict):
        return str(value).strip()
    node_type = value.get("type")
    if node_type == "text":
        return str(value.get("text", ""))
    content = value.get("content", [])
    rendered = (
        [jira_document_to_text(item) for item in content] if isinstance(content, list) else []
    )
    separator = "" if node_type in {"paragraph", "heading", "listItem"} else "\n"
    text = separator.join(filter(None, rendered)).strip()
    if node_type == "listItem" and text:
        return f"- {text}"
    return text


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

    async def read_requirement(self, issue_key: str) -> JiraRequirement:
        """Read a Jira/Xray-backed story and extract its testable requirement text."""
        self._validate_config()
        base_url = self.settings.jira_base_url.rstrip("/")
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(
            auth=(self.settings.jira_email, self.settings.jira_api_token), timeout=30
        )
        try:
            configured = self.settings.jira_acceptance_criteria_field_list
            field_ids: list[str] = []
            field_names: dict[str, str] = {}
            fields_response = await client.get(
                f"{base_url}/rest/api/3/field", headers={"Accept": "application/json"}
            )
            fields_response.raise_for_status()
            for item in fields_response.json():
                field_id, name = str(item.get("id", "")), str(item.get("name", ""))
                if not field_id:
                    continue
                is_acceptance_field = (
                    field_id in configured
                    or name in configured
                    or "acceptance criteria" in name.casefold()
                )
                if is_acceptance_field:
                    field_ids.append(field_id)
                    field_names[field_id] = name or field_id

            requested_fields = ["summary", "description", *dict.fromkeys(field_ids)]
            response = await client.get(
                f"{base_url}/rest/api/3/issue/{issue_key}",
                headers={"Accept": "application/json"},
                params={"fields": ",".join(requested_fields)},
            )
            response.raise_for_status()
            fields = response.json().get("fields", {})
            criteria: list[str] = []
            sources: list[str] = []
            for field_id in field_ids:
                text = jira_document_to_text(fields.get(field_id))
                if text:
                    criteria.extend(
                        line.removeprefix("- ").strip()
                        for line in text.splitlines()
                        if line.strip()
                    )
                    sources.append(field_names[field_id])
            return JiraRequirement(
                issue_key=issue_key.upper(),
                summary=str(fields.get("summary") or issue_key),
                description=jira_document_to_text(fields.get("description")),
                acceptance_criteria=list(dict.fromkeys(criteria)),
                source_fields=sources,
            )
        finally:
            if owns_client:
                await client.aclose()
