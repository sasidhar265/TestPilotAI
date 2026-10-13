"""Report provider execution and waiting, without exposing prompts or reasoning."""

import asyncio
import time
from collections.abc import Awaitable
from typing import TypeVar

from app.observability import publish_lifecycle_event

Result = TypeVar("Result")


async def await_agent_activity(
    operation: Awaitable[Result], provider: str, purpose: str, *, interval: float = 10
) -> Result:
    """Keep cancellation attached to the provider task and report real elapsed waiting."""
    agent = "AI Provider"
    started = time.monotonic()
    publish_lifecycle_event(agent, "provider_call", "running", f"{provider}: generating {purpose}.")
    task = asyncio.ensure_future(operation)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=interval)
            if done:
                result = task.result()
                publish_lifecycle_event(
                    agent,
                    "provider_response",
                    "success",
                    f"{provider}: response received for {purpose}; returning it for validation.",
                )
                return result
            elapsed = int(time.monotonic() - started)
            publish_lifecycle_event(
                agent,
                "provider_wait",
                "running",
                f"{provider}: waiting for {purpose} output ({elapsed}s elapsed). "
                "The provider has not returned a completed response yet.",
            )
    except asyncio.CancelledError:
        publish_lifecycle_event(
            agent,
            "provider_cancelled",
            "cancelled",
            f"{provider}: generation cancelled; stopping provider work.",
        )
        raise
    except Exception:
        publish_lifecycle_event(
            agent,
            "provider_unavailable",
            "warning",
            f"{provider}: this attempt could not complete. "
            "The workflow will report fallback or failure.",
        )
        raise
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
