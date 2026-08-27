"""Cancellation registry for user-controlled long-running generation requests."""

import asyncio
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActiveGeneration:
    task: asyncio.Task[object]
    operation: str
    started_at: float


class GenerationCancellationRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, ActiveGeneration] = {}

    def register(self, request_id: str, operation: str = "test_case_generation") -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks[request_id] = ActiveGeneration(task, operation, time.perf_counter())
            logger.info(
                "generation_started operation=%s",
                operation,
                extra={
                    "event_details": {
                        "operation": operation,
                        "state": "running",
                        "initiator": "user",
                    }
                },
            )

    def unregister(self, request_id: str) -> None:
        self._tasks.pop(request_id, None)

    def cancel(self, request_id: str) -> bool:
        active = self._tasks.get(request_id)
        if active is None or active.task.done():
            return False
        duration_ms = round((time.perf_counter() - active.started_at) * 1000, 2)
        active.task.cancel("Generation stopped by the user")
        logger.warning(
            "generation_stopped operation=%s outcome=cancel_requested duration_ms=%s",
            active.operation,
            duration_ms,
            extra={
                "request_id_override": request_id,
                "event_details": {
                    "operation": active.operation,
                    "outcome": "cancel_requested",
                    "elapsed_ms": str(duration_ms),
                    "task_state": "cancelling",
                    "initiated_by": "user",
                    "provider_session_cleanup": "initiated",
                },
            },
        )
        return True


generation_cancellations = GenerationCancellationRegistry()
