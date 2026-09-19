"""Usage accounting unit checks: no live provider calls or API scenarios."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.services.dashboard import DashboardStore
from app.services.usage import UsageStore, codex_output, record_provider_usage


def test_generation_reuse_and_retention(tmp_path):
    memory = tmp_path / "memory.db"
    store = DashboardStore(memory)
    usage = UsageStore(memory)
    for index in range(205):
        identifier = store.start("test_generation")
        store.finish(
            identifier,
            "completed",
            {
                "source": "organizational-memory" if index == 0 else "openai",
                "cases": [{"mode": "manual"}, {"mode": "automation"}],
            },
        )
    snapshot = store.snapshot()
    assert len(snapshot["history"]) == 200
    for record in snapshot["history"]:
        usage.generation(record)
    totals = usage.snapshot(0)["totals"]
    assert totals["runs"] == 205
    assert totals["manual"] == totals["automation"] == 204
    assert totals["reused"] == 2


def test_cost_cache_long_context_and_unknown_rates(tmp_path):
    store = UsageStore(tmp_path / "memory.db")
    store.record("openai-api", "gpt-5.4", 1000, 100, 200, priced=True, identifier="same")
    store.record("openai-api", "gpt-5.4", 1000, 100, 200, priced=True, identifier="same")
    store.record("openai-api", "gpt-5.4", 300000, 1000, 100000, priced=True)
    store.record("codex-cli", "gpt-5.4", 1000, 100, 200)
    store.record("openai-api", "unknown-model", 1000, 100, priced=True)
    rows = {r["provider"] + r["model"]: r for r in store.snapshot(0)["models"]}
    assert rows["openai-apigpt-5.4"]["calls"] == 2
    assert rows["openai-apigpt-5.4"]["cost_usd"] == pytest.approx(0.00355 + 1.0725)
    assert rows["codex-cligpt-5.4"]["cost_usd"] is None
    assert rows["openai-apiunknown-model"]["unpriced_calls"] == 1


def test_missing_tokens_zero_tokens_and_period_filter(tmp_path):
    store = UsageStore(tmp_path / "memory.db")
    store.record("openai-api", "gpt-5.4", None, None, priced=True)
    store.record("openai-api", "gpt-5.4", 0, 0, priced=True)
    old = (datetime.now(UTC) - timedelta(days=45)).isoformat()
    store.generation(
        {
            "id": "old",
            "operation": "test_generation",
            "finished_at": old,
            "status": "completed",
            "details": {"cases": [{"mode": "manual"}]},
        }
    )
    assert store.snapshot(30)["totals"]["manual"] == 0
    assert store.snapshot(90)["totals"]["manual"] == 1
    row = store.snapshot()["models"][0]
    assert row["unmetered_calls"] == row["unpriced_calls"] == 1
    assert row["cost_usd"] == 0


def test_provider_payloads_and_codex_final_message(tmp_path):
    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    record_provider_usage(
        settings,
        "openai-api",
        {
            "id": "resp-1",
            "model": "gpt-5.4",
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 100,
                "input_tokens_details": {"cached_tokens": 200},
            },
        },
    )
    record_provider_usage(
        settings,
        "gemini-api",
        {
            "usageMetadata": {
                "promptTokenCount": 80,
                "candidatesTokenCount": 20,
                "thoughtsTokenCount": 10,
            }
        },
    )
    output = "\n".join(
        json.dumps(event)
        for event in [
            {"type": "item.completed", "item": {"type": "agent_message", "text": '{"ok":true}'}},
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 50, "output_tokens": 10, "cached_input_tokens": 20},
            },
        ]
    )
    assert codex_output(settings, output.encode()) == '{"ok":true}'
    rows = {
        row["provider"]: row
        for row in UsageStore(settings.organizational_memory_path).snapshot()["models"]
    }
    assert rows["openai-api"]["cost_usd"] == pytest.approx(0.00355)
    assert rows["gemini-api"]["output_tokens"] == 30
    assert rows["codex-cli"]["input_tokens"] == 50
    assert rows["codex-cli"]["cost_usd"] is None


def test_concurrent_usage_records(tmp_path):
    store = UsageStore(tmp_path / "memory.db")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(lambda _: store.record("openai-api", "gpt-5.4", 10, 5, priced=True), range(24))
        )
    assert store.snapshot()["models"][0]["calls"] == 24
