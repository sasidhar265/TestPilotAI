"""Logging and request-correlation primitives that never include customer payloads."""

import contextvars
import json
import logging
import traceback
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import Lock
from types import TracebackType

request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def format_safe_exception(exception_type: type[BaseException], trace: TracebackType) -> str:
    """Format exception type and call locations without messages or source payload literals."""
    frames = traceback.extract_tb(trace)
    locations = "\n".join(
        f"{frame.filename}:{frame.lineno} in {frame.name}" for frame in frames
    )
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
                payload["exception"] = format_safe_exception(
                    record.exc_info[0], record.exc_info[2]
                )
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
