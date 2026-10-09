"""Unit checks for durable structured logging without request payloads."""

import atexit
import json
import logging
from datetime import UTC, datetime

from app.config import Settings
from app.observability import InMemoryLogHandler, JsonFormatter, configure_file_logging


def test_handlers_use_event_timestamp_and_safe_exception_locations():
    try:
        raise ValueError("private request payload")
    except ValueError:
        import sys

        record = logging.LogRecord(
            "app.unit", logging.ERROR, __file__, 10, "operation_failed", (), sys.exc_info()
        )
    record.created = 1700000000.123
    record.request_id_override = "trace-1"
    record.event_details = {"operation": "graph_snapshot", "status": "failed"}
    ui = InMemoryLogHandler()
    ui.emit(record)
    entry = ui.search()[0]
    encoded = json.loads(JsonFormatter().format(record))
    assert entry["timestamp"] == encoded["timestamp"] == "2023-11-14T22:13:20.123+00:00"
    assert entry["request_id"] == encoded["request_id"] == "trace-1"
    assert "ValueError" in entry["exception"]
    assert "private request payload" not in json.dumps(entry)
    assert "private request payload" not in json.dumps(encoded)


def test_rotating_files_preserve_structured_events(tmp_path):
    path = tmp_path / "logs" / "application.jsonl"
    settings = Settings(
        runtime_config_path=None,
        log_file_path=path,
        log_file_max_bytes=1024,
        log_file_backup_count=2,
    )
    handler = configure_file_logging(settings)
    assert handler is not None
    try:
        for index in range(20):
            record = logging.LogRecord(
                "app.unit", logging.INFO, __file__, 1, "operation_complete", (), None
            )
            record.request_id_override = f"trace-{index}"
            record.event_details = {"operation": "snapshot", "status": "200"}
            handler.handle(record)
        handler.queue.join()
        files = list(path.parent.glob("application.jsonl*"))
        assert len(files) == 3
        entries = [json.loads(line) for file in files for line in file.read_text().splitlines()]
        assert any(entry["request_id"] == "trace-19" for entry in entries)
        assert all(entry["details"]["status"] == "200" for entry in entries)
        assert all(datetime.fromisoformat(entry["timestamp"]).tzinfo == UTC for entry in entries)
    finally:
        atexit.unregister(handler.listener.stop)
        handler.listener.stop()
        for output in handler.listener.handlers:
            output.close()
