"""Safe logging, request correlation, HTTP controls, and generation cancellation."""

import asyncio
import contextvars
import json
import logging
import re
import time
import traceback
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import Lock
from types import TracebackType
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
logger = logging.getLogger(__name__)
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def format_safe_exception(exception_type: type[BaseException], trace: TracebackType) -> str:
    """Format exception type and call locations without messages or source payload literals."""
    frames = traceback.extract_tb(trace)
    locations = "\n".join(f"{frame.filename}:{frame.lineno} in {frame.name}" for frame in frames)
    return f"{exception_type.__name__}\n{locations}"


@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    level: str
    logger: str
    message: str
    request_id: str
    exception: str
    details: dict[str, str]


class InMemoryLogHandler(logging.Handler):
    """Keep a bounded, payload-free log view for local UI diagnostics."""

    def __init__(self, capacity: int = 1000) -> None:
        super().__init__()
        self._entries: deque[LogEntry] = deque(maxlen=capacity)
        self._lock = Lock()

    def emit(self, record: logging.LogRecord) -> None:
        exception = ""
        if record.exc_info and record.exc_info[2]:
            exception = format_safe_exception(record.exc_info[0], record.exc_info[2])
        entry = LogEntry(
            timestamp=datetime.now(UTC).isoformat(),
            level=record.levelname,
            logger=record.name,
            message=record.getMessage(),
            request_id=getattr(record, "request_id_override", request_id_context.get()),
            exception=exception,
            details=getattr(record, "event_details", {}),
        )
        with self._lock:
            self._entries.append(entry)

    def search(self, request_id: str = "", limit: int = 100) -> list[dict[str, object]]:
        with self._lock:
            entries = list(self._entries)
        if request_id:
            entries = [entry for entry in entries if entry.request_id == request_id]
        return [asdict(entry) for entry in reversed(entries[-limit:])]


ui_log_handler = InMemoryLogHandler()


class JsonFormatter(logging.Formatter):
    """Small dependency-free JSON formatter for centralized log ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id_override", request_id_context.get()),
        }
        details = getattr(record, "event_details", None)
        if details:
            payload["details"] = details
        if record.exc_info:
            if record.exc_info[0] and record.exc_info[2]:
                payload["exception"] = format_safe_exception(record.exc_info[0], record.exc_info[2])
        return json.dumps(payload, separators=(",", ":"))


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter()
        if json_logs
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.addHandler(ui_log_handler)
    root.setLevel(level.upper())


@dataclass(frozen=True)
class ActiveGeneration:
    task: asyncio.Task[object]
    operation: str
    started_at: float


class GenerationCancellationRegistry:
    """Track and cancel user-controlled long-running generation requests."""

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


class OrganizationHttpMiddleware:
    """Add correlation, safe request logs, and baseline browser protections."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        supplied = headers.get(b"x-request-id", b"").decode("ascii", "ignore")
        request_id = supplied if _SAFE_REQUEST_ID.fullmatch(supplied) else str(uuid4())
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_headers(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = list(message.get("headers", []))
                response_headers.extend(
                    [
                        (b"x-request-id", request_id.encode("ascii")),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    ]
                )
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except asyncio.CancelledError:
            status_code = 499
            raise
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            log = (
                logger.error
                if status_code >= 500
                else logger.warning
                if status_code >= 400
                else logger.info
            )
            log(
                "request_complete method=%s path=%s status=%s duration_ms=%s",
                scope.get("method"),
                scope.get("path"),
                status_code,
                duration_ms,
            )
            request_id_context.reset(token)
