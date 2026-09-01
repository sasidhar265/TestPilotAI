"""Safe logging, request correlation, HTTP controls, and generation cancellation."""

import asyncio
import contextvars
import hmac
import json
import logging
import re
import time
import traceback
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from http.cookies import SimpleCookie
from threading import Lock
from types import TracebackType
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth import SESSION_COOKIE, valid_session
from app.config import Settings

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


@dataclass(frozen=True)
class LifecycleEvent:
    sequence: int
    timestamp: str
    agent: str
    action: str
    status: str
    summary: str


class LifecycleEventRegistry:
    """Keep bounded, payload-free agent activity for live UI inspection."""

    def __init__(self, request_capacity: int = 200, events_per_request: int = 100) -> None:
        self._request_capacity = request_capacity
        self._events_per_request = events_per_request
        self._events: dict[str, deque[LifecycleEvent]] = {}
        self._order: deque[str] = deque()
        self._completed: set[str] = set()
        self._lock = Lock()

    def start(self, request_id: str) -> None:
        with self._lock:
            if request_id not in self._events:
                while len(self._events) >= self._request_capacity and self._order:
                    expired = self._order.popleft()
                    self._events.pop(expired, None)
                    self._completed.discard(expired)
                self._events[request_id] = deque(maxlen=self._events_per_request)
                self._order.append(request_id)
                self._completed.discard(request_id)

    def publish(
        self,
        request_id: str,
        agent: str,
        action: str,
        status: str,
        summary: str,
    ) -> None:
        self.start(request_id)
        with self._lock:
            if request_id in self._completed:
                return
            events = self._events[request_id]
            events.append(
                LifecycleEvent(
                    sequence=(events[-1].sequence + 1) if events else 1,
                    timestamp=datetime.now(UTC).isoformat(),
                    agent=agent,
                    action=action,
                    status=status,
                    summary=summary,
                )
            )

    def complete(self, request_id: str) -> None:
        with self._lock:
            if request_id in self._events:
                self._completed.add(request_id)

    def read(self, request_id: str, after: int = 0) -> dict[str, object]:
        with self._lock:
            events = list(self._events.get(request_id, ()))
            complete = request_id in self._completed
        return {
            "request_id": request_id,
            "events": [asdict(event) for event in events if event.sequence > after],
            "complete": complete,
        }


lifecycle_events = LifecycleEventRegistry()


def publish_lifecycle_event(agent: str, action: str, status: str, summary: str) -> None:
    """Publish against the active correlation ID without recording request content."""
    request_id = request_id_context.get()
    if request_id != "-":
        lifecycle_events.publish(request_id, agent, action, status, summary)


class OrganizationHttpMiddleware:
    """Enforce API access, resource bounds, safe logs, and browser protections."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self._request_slots = asyncio.Semaphore(settings.max_concurrent_requests)
        self._generation_slots = asyncio.Semaphore(settings.max_concurrent_generations)

    @staticmethod
    async def _reject(send: Send, status: int, detail: str, request_id: str) -> None:
        body = json.dumps({"detail": detail}, separators=(",", ":")).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"cache-control", b"no-store"),
                    (b"x-request-id", request_id.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    def _authorized(self, scope: Scope, headers: dict[bytes, bytes]) -> bool:
        expected = self.settings.api_auth_token_value
        path = str(scope.get("path", ""))
        public_paths = {"/login", "/api/auth/login", "/api/health", "/api/live", "/api/ready"}
        if path in public_paths or path.startswith("/static/"):
            return True
        cookie = SimpleCookie()
        try:
            cookie.load(headers.get(b"cookie", b"").decode("latin-1"))
        except ValueError:
            cookie.clear()
        session = cookie.get(SESSION_COOKIE)
        if session is not None and valid_session(session.value, self.settings):
            return True
        if not path.startswith("/api/"):
            return not self.settings.browser_login_enabled
        if not expected:
            return not self.settings.browser_login_enabled
        supplied = headers.get(b"authorization", b"").decode("ascii", "ignore")
        scheme, separator, token = supplied.partition(" ")
        return bool(
            separator and scheme.casefold() == "bearer" and hmac.compare_digest(token, expected)
        )

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
        slot_acquired = False
        generation_slot_acquired = False

        content_length = headers.get(b"content-length", b"0")
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = -1

        if declared_length < 0:
            await self._reject(send, 400, "Invalid Content-Length header", request_id)
            request_id_context.reset(token)
            return
        if declared_length > self.settings.max_request_body_bytes:
            await self._reject(send, 413, "Request body exceeds the configured limit", request_id)
            request_id_context.reset(token)
            return
        if not self._authorized(scope, headers):
            if not str(scope.get("path", "")).startswith("/api/"):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 303,
                        "headers": [
                            (b"location", b"/login"),
                            (b"cache-control", b"no-store"),
                            (b"x-request-id", request_id.encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": b""})
                request_id_context.reset(token)
                return
            await self._reject(send, 401, "Authentication required", request_id)
            request_id_context.reset(token)
            return

        try:
            await asyncio.wait_for(
                self._request_slots.acquire(),
                timeout=self.settings.request_queue_timeout_seconds,
            )
            slot_acquired = True
        except TimeoutError:
            await self._reject(send, 503, "Server is at request capacity", request_id)
            request_id_context.reset(token)
            return

        generation_paths = {
            "/api/generate",
            "/api/agent/run",
            "/api/generate/document",
            "/api/generate/expand",
            "/api/step-definitions/reqnroll",
        }
        if scope.get("method") == "POST" and scope.get("path") in generation_paths:
            try:
                await asyncio.wait_for(
                    self._generation_slots.acquire(),
                    timeout=self.settings.request_queue_timeout_seconds,
                )
                generation_slot_acquired = True
            except TimeoutError:
                self._request_slots.release()
                slot_acquired = False
                await self._reject(send, 503, "Generation capacity is currently full", request_id)
                request_id_context.reset(token)
                return

        received_bytes = 0

        async def bounded_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.settings.max_request_body_bytes:
                    raise RequestBodyTooLarge
            return message

        async def send_with_headers(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = list(message.get("headers", []))
                content_security_policy = (
                    b"default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
                    b"form-action 'self'; object-src 'none'; img-src 'self' data:; "
                    b"script-src 'self'; style-src 'self' 'unsafe-inline'"
                )
                if not self.settings.is_production and scope.get("path") in {"/docs", "/redoc"}:
                    content_security_policy = (
                        b"default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
                        b"form-action 'self'; object-src 'none'; img-src 'self' data:; "
                        b"script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                        b"style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
                    )
                response_headers.extend(
                    [
                        (b"x-request-id", request_id.encode("ascii")),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                        (
                            b"content-security-policy",
                            content_security_policy,
                        ),
                        (b"cross-origin-opener-policy", b"same-origin"),
                        (b"cross-origin-resource-policy", b"same-origin"),
                    ]
                )
                if self.settings.is_production:
                    response_headers.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, bounded_receive, send_with_headers)
        except RequestBodyTooLarge:
            status_code = 413
            await self._reject(send, 413, "Request body exceeds the configured limit", request_id)
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
            if slot_acquired:
                self._request_slots.release()
            if generation_slot_acquired:
                self._generation_slots.release()
            request_id_context.reset(token)


class RequestBodyTooLarge(Exception):
    """Internal signal raised when a streamed body crosses the configured maximum."""
