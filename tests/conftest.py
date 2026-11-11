"""Keep tests away from developer credentials, data stores and production keys."""

import os
from tempfile import TemporaryDirectory

from cryptography.fernet import Fernet

_memory_directory = TemporaryDirectory(prefix="afq-test-memory-")
_test_environment = {
    "ORGANIZATIONAL_MEMORY_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "ORGANIZATIONAL_MEMORY_ENABLED": "true",
    "ORGANIZATIONAL_MEMORY_PATH": _memory_directory.name + "/memory.db",
    "APP_PASSWORD": "",
    "SESSION_SECRET": "",
    "API_AUTH_TOKEN": "",
    "USER_SECRETS_ENABLED": "false",
    "ENVIRONMENT": "development",
    "USER_DATABASE_PATH": _memory_directory.name + "/users.db",
    "ACCEPTED_OUTPUT_DIRECTORY": _memory_directory.name + "/outputs",
    "LOG_FILE_PATH": _memory_directory.name + "/application.jsonl",
}
_previous = {name: os.environ.get(name) for name in _test_environment}
os.environ.update(_test_environment)


def pytest_unconfigure(config):
    for name, value in _previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    _memory_directory.cleanup()
