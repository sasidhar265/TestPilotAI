"""Persistent, payload-free application usage and explicitly partial cost estimates."""

import json
import logging
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)
PRICING_SOURCE = "https://developers.openai.com/api/docs/models/gpt-5.4"
# Standard public USD / million tokens, verified 2026-09-19. No subscription conversion.
OPENAI_RATES = {"gpt-5.4": (2.5, 0.25, 15.0), "gpt-5.4-2026-03-05": (2.5, 0.25, 15.0)}


class UsageStore:
    def __init__(self, memory_path: Path):
        self.path = memory_path.with_name("usage.db")

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS generations (
                id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, manual INTEGER NOT NULL,
                automation INTEGER NOT NULL, reused INTEGER NOT NULL, status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS calls (
                id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, provider TEXT NOT NULL,
                model TEXT NOT NULL, input_tokens INTEGER, cached_tokens INTEGER,
                output_tokens INTEGER, cost_usd REAL, rates TEXT);
            CREATE INDEX IF NOT EXISTS generation_time ON generations(timestamp);
            CREATE INDEX IF NOT EXISTS call_time ON calls(timestamp);
        """)
        return connection

    def generation(self, record: dict[str, Any]) -> None:
        if record.get("operation") != "test_generation":
            return
        details = record.get("details", {})
        cases = details.get("cases", [])
        reused = details.get("source") == "organizational-memory"
        with closing(self.connect()) as connection, connection:
            connection.execute(
                "INSERT OR IGNORE INTO generations VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record["id"],
                    record["finished_at"],
                    sum(c.get("mode") == "manual" for c in cases) if not reused else 0,
                    sum(c.get("mode") == "automation" for c in cases) if not reused else 0,
                    len(cases) if reused else 0,
                    record["status"],
                ),
            )

    def record(
        self,
        provider: str,
        model: str,
        input_tokens: Any,
        output_tokens: Any,
        cached_tokens: Any = 0,
        *,
        priced: bool = False,
        identifier: str | None = None,
    ) -> None:
        def count(value: Any) -> int | None:
            return value if type(value) is int and value >= 0 else None

        incoming, outgoing = count(input_tokens), count(output_tokens)
        cached = count(cached_tokens)
        cost = None
        rates = OPENAI_RATES.get(model) if provider == "openai-api" and priced else None
        if rates and incoming is not None and outgoing is not None and cached is not None:
            cached = min(cached, incoming)
            multiplier = 2 if incoming > 272_000 else 1
            output_multiplier = 1.5 if incoming > 272_000 else 1
            rates = (rates[0] * multiplier, rates[1] * multiplier, rates[2] * output_multiplier)
            cost = (
                (incoming - cached) * rates[0] + cached * rates[1] + outgoing * rates[2]
            ) / 1_000_000
        with closing(self.connect()) as connection, connection:
            connection.execute(
                "INSERT OR IGNORE INTO calls VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"{provider}:{identifier or uuid4().hex}",
                    datetime.now(UTC).isoformat(),
                    provider,
                    model or "Provider default",
                    incoming,
                    cached,
                    outgoing,
                    cost,
                    json.dumps(rates) if rates else None,
                ),
            )

    def snapshot(self, days: int = 30) -> dict[str, Any]:
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat() if days else ""
        with closing(self.connect()) as connection:
            totals = dict(
                connection.execute(
                    "SELECT COUNT(*) runs, COALESCE(SUM(manual),0) manual, "
                    "COALESCE(SUM(automation),0) automation, COALESCE(SUM(reused),0) reused, "
                    "COALESCE(SUM(status='validation_failed'),0) validation_failed, "
                    "COALESCE(SUM(status IN ('failed','cancelled')),0) failed "
                    "FROM generations WHERE timestamp >= ?",
                    (since,),
                ).fetchone()
            )
            models = [
                dict(row)
                for row in connection.execute(
                    "SELECT provider, model, COUNT(*) calls, SUM(input_tokens) input_tokens, "
                    "SUM(cached_tokens) cached_tokens, SUM(output_tokens) output_tokens, "
                    "SUM(cost_usd) cost_usd, SUM(cost_usd IS NULL) unpriced_calls, "
                    "SUM(input_tokens IS NULL OR output_tokens IS NULL) unmetered_calls "
                    "FROM calls WHERE timestamp >= ? GROUP BY provider, model ORDER BY calls DESC",
                    (since,),
                )
            ]
            daily = [
                dict(row)
                for row in connection.execute(
                    "SELECT substr(timestamp,1,10) day, SUM(manual) manual, "
                    "SUM(automation) automation FROM generations WHERE timestamp >= ? "
                    "GROUP BY day ORDER BY day DESC LIMIT 30",
                    (since,),
                )
            ]
        return {
            "days": days,
            "totals": totals,
            "models": models,
            "daily": daily[::-1],
            "pricing_source": PRICING_SOURCE,
            "pricing_checked": "2026-09-19",
            "rates": [
                {"model": model, "input": rate[0], "cached": rate[1], "output": rate[2]}
                for model, rate in OPENAI_RATES.items()
            ],
            "scope": "Shared workspace usage. Includes retained generation history and all "
            "new activity since tracking began. Revisions count as generation output; "
            "reused cases are separate. Validation-failed output is included. "
            "Token tracking starts with this update and includes model calls for all stages, "
            "including retries. Historical tokens and unreported usage cannot be recovered.",
        }


def record_provider_usage(settings: Any, provider: str, payload: dict[str, Any]) -> None:
    """Telemetry failure must never turn a successful generation into a failed request."""
    try:
        store = UsageStore(settings.organizational_memory_path)
        if provider == "openai-api":
            usage = payload.get("usage") or {}
            store.record(
                provider,
                payload.get("model") or settings.openai_model,
                usage.get("input_tokens"),
                usage.get("output_tokens"),
                (usage.get("input_tokens_details") or {}).get("cached_tokens", 0),
                priced=settings.openai_base_url.rstrip("/") == "https://api.openai.com/v1"
                and payload.get("service_tier", "default") in (None, "default", "auto"),
                identifier=payload.get("id"),
            )
        elif provider == "gemini-api":
            usage = payload.get("usageMetadata") or {}
            output = usage.get("candidatesTokenCount")
            if output is not None:
                output += usage.get("thoughtsTokenCount", 0)
            store.record(
                provider,
                payload.get("modelVersion") or settings.gemini_model,
                usage.get("promptTokenCount"),
                output,
                usage.get("cachedContentTokenCount", 0),
                identifier=payload.get("responseId"),
            )
        else:
            store.record(
                provider,
                payload.get("model") or settings.codex_model,
                payload.get("input_tokens"),
                payload.get("output_tokens"),
                payload.get("cached_input_tokens", 0),
                identifier=payload.get("id"),
            )
    except (OSError, sqlite3.Error, TypeError, ValueError):
        logger.warning("usage_record_unavailable provider=%s", provider)


def codex_output(settings: Any, stdout: bytes) -> str:
    """Read JSONL usage and preserve the final message fallback for CLI versions/test doubles."""
    message = stdout.decode("utf-8", errors="replace")
    metered = False
    for line in message.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "turn.completed":
            record_provider_usage(settings, "codex-cli", event.get("usage") or {})
            metered = True
        if (
            event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "agent_message"
        ):
            message = event["item"].get("text", "")
    if not metered:
        record_provider_usage(settings, "codex-cli", {})
    return message
