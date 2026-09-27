"""Keep organisational-memory tests away from developer data and production keys."""

import os
from tempfile import TemporaryDirectory

from cryptography.fernet import Fernet

_memory_directory = TemporaryDirectory(prefix="afq-test-memory-")
_memory_environment = {
    "ORGANIZATIONAL_MEMORY_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "ORGANIZATIONAL_MEMORY_ENABLED": "true",
    "ORGANIZATIONAL_MEMORY_PATH": _memory_directory.name + "/memory.db",
}
_previous = {name: os.environ.get(name) for name in _memory_environment}
os.environ.update(_memory_environment)


def pytest_unconfigure(config):
    for name, value in _previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    _memory_directory.cleanup()
