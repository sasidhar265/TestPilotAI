import asyncio

import pytest

from app.cancellation import GenerationCancellationRegistry
from app.observability import request_id_context, ui_log_handler


@pytest.mark.asyncio
async def test_registered_generation_can_be_cancelled() -> None:
    registry = GenerationCancellationRegistry()
    registered = asyncio.Event()

    async def generation() -> None:
        token = request_id_context.set("generation-guid")
        registry.register("generation-guid", "bdd_generation")
        registered.set()
        try:
            await asyncio.Event().wait()
        finally:
            registry.unregister("generation-guid")
            request_id_context.reset(token)

    task = asyncio.create_task(generation())
    await registered.wait()

    assert registry.cancel("generation-guid") is True
    with pytest.raises(asyncio.CancelledError):
        await task
    assert registry.cancel("generation-guid") is False
    stopped = [
        entry
        for entry in ui_log_handler.search(request_id="generation-guid")
        if "generation_stopped" in str(entry["message"])
    ][0]
    assert stopped["details"] == {
        "operation": "bdd_generation",
        "outcome": "cancel_requested",
        "elapsed_ms": stopped["details"]["elapsed_ms"],
        "task_state": "cancelling",
        "initiated_by": "user",
        "provider_session_cleanup": "initiated",
    }
