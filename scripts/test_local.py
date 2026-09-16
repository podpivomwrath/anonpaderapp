"""Isolated tests: never load .env or contact external services.

Optional TEST_DATABASE_URL must point at a loopback database named pines_test.
Run: python scripts/test_local.py [pytest arguments]
"""
import os
from pathlib import Path
import socket
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
sys.dont_write_bytecode = True
url = os.environ.get("TEST_DATABASE_URL")
if url:
    parsed = urlparse(url)
    if parsed.hostname not in ("127.0.0.1", "localhost", "::1") or parsed.path != "/pines_test":
        raise SystemExit("TEST_DATABASE_URL must use loopback and database pines_test")
for key in ("VK_TOKEN", "VK_SECRET", "VK_MINIAPP_SECRET", "VK_SERVICE_KEY"):
    os.environ[key] = "local-test-dummy"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://audit:audit@127.0.0.1:1/audit"
os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"

import config
config.Settings.model_config["env_file"] = None


def guard(original):
    def connect(self, address):
        if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise RuntimeError("Tests may only connect to loopback")
        return original(self, address)
    return connect


socket.socket.connect = guard(socket.socket.connect)
socket.socket.connect_ex = guard(socket.socket.connect_ex)

if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main(["-p", "no:cacheprovider", *sys.argv[1:]]))
