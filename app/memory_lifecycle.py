"""Expire organisational knowledge at startup and hourly while the app is running."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, closing, suppress

from fastapi import FastAPI

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def purge_memory(settings: Settings) -> None:
    if settings.organizational_memory_enabled and settings.organizational_memory_path.is_file():
        with closing(settings.memory_protection.connect(settings.organizational_memory_path)):
            pass


async def retention_worker(settings: Settings) -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            await asyncio.to_thread(purge_memory, settings)
        except Exception:
            # Storage/key exceptions must never publish payloads or secret values.
            logger.error("memory_retention_failed; operator attention required")


@asynccontextmanager
async def memory_lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # Refuse to serve an enabled but unreadable/legacy memory store.
    await asyncio.to_thread(purge_memory, settings)
    task = asyncio.create_task(retention_worker(settings))
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
