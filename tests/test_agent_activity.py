"""Provider telemetry must describe real waiting and preserve cancellation."""

import asyncio

import pytest

from app.agent_activity import await_agent_activity


@pytest.mark.asyncio
async def test_waiting_events_and_success_do_not_expose_provider_payload(monkeypatch):
    events = []
    monkeypatch.setattr(
        "app.agent_activity.publish_lifecycle_event", lambda *event: events.append(event)
    )

    async def provider():
        await asyncio.sleep(0.025)
        return "private provider output"

    result = await await_agent_activity(
        provider(), "codex-cli / gpt-6-astra", "stories", interval=0.005
    )
    assert result == "private provider output"
    assert events[0][1:3] == ("provider_call", "running")
    assert any(event[1] == "provider_wait" for event in events)
    assert events[-1][1:3] == ("provider_response", "success")
    assert "private provider output" not in str(events)


@pytest.mark.asyncio
async def test_provider_cancellation_stops_child_task(monkeypatch):
    events = []
    monkeypatch.setattr(
        "app.agent_activity.publish_lifecycle_event", lambda *event: events.append(event)
    )
    started, stopped = asyncio.Event(), asyncio.Event()

    async def provider():
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            stopped.set()

    task = asyncio.create_task(await_agent_activity(provider(), "provider", "scenarios"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
    assert events[-1][1:3] == ("provider_cancelled", "cancelled")


@pytest.mark.asyncio
async def test_failed_attempt_does_not_mark_recoverable_route_as_failed(monkeypatch):
    events = []
    monkeypatch.setattr(
        "app.agent_activity.publish_lifecycle_event", lambda *event: events.append(event)
    )

    async def provider():
        raise ValueError("secret failure detail")

    with pytest.raises(ValueError):
        await await_agent_activity(provider(), "provider", "stories")
    assert events[-1][1:3] == ("provider_unavailable", "warning")
    assert "secret failure detail" not in str(events)
