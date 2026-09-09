"""Bounded cleanup for CLI launchers and their child processes."""

import asyncio
import os
import signal
from contextlib import suppress


async def stop_process_tree(process: asyncio.subprocess.Process) -> None:
    """Processes passed here must be spawned with start_new_session on POSIX."""
    with suppress(ProcessLookupError):
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif process.returncode is None:
            process.kill()
    with suppress(TimeoutError):
        await asyncio.wait_for(process.wait(), timeout=5)
