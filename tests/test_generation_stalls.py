"""Regressions for blocked console output and abandoned CLI descendants."""

import asyncio
import logging
import os
import sys
from queue import Queue

import pytest

from app.observability import NonBlockingConsoleHandler, request_id_context
from app.subprocess_cleanup import stop_process_tree


def test_console_queue_is_bounded_and_preserves_request_context() -> None:
    queue = Queue(maxsize=1)
    handler = NonBlockingConsoleHandler(queue)
    token = request_id_context.set("stalled-run")
    try:
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "progress", (), None)
        handler.handle(record)
        # Even a full console queue must return immediately to the event loop.
        for _ in range(2000):
            handler.handle(record)
        assert queue.qsize() == 1
        assert queue.get_nowait().request_id_override == "stalled-run"
    finally:
        request_id_context.reset(token)


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
async def test_cleanup_kills_launcher_and_child_holding_output_pipe() -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import subprocess, sys, time; "
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        "print('ready', flush=True); time.sleep(60)",
        start_new_session=True,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        assert await asyncio.wait_for(process.stdout.readline(), timeout=5) == b"ready\n"
        await asyncio.wait_for(stop_process_tree(process), timeout=2)
        assert process.returncode is not None
        assert await asyncio.wait_for(process.stdout.read(), timeout=2) == b""
    finally:
        await stop_process_tree(process)
