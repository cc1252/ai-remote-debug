import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_TOKEN = "test-token-that-is-longer-than-thirty-two-characters"
ARTIFACT_TEMP_DIR = tempfile.TemporaryDirectory(prefix="ard-test-artifacts-")
os.environ["ARD_API_TOKEN"] = TEST_TOKEN
os.environ["ARD_ARTIFACT_DIR"] = ARTIFACT_TEMP_DIR.name

spec = importlib.util.spec_from_file_location(
    "ard_relay", PROJECT_ROOT / "relay-server" / "main.py"
)
assert spec and spec.loader
relay = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = relay
spec.loader.exec_module(relay)

AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}


def setup_function() -> None:
    relay.devices.clear()
    for path in relay.ARTIFACT_DIR.iterdir():
        if path.is_file():
            path.unlink()


def test_health_and_api_authentication() -> None:
    with TestClient(relay.app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/devices").status_code == 401
        assert client.get("/api/devices", headers=AUTH).json() == []


def test_insecure_relay_configuration_is_rejected() -> None:
    original_token = relay.API_TOKEN
    relay.API_TOKEN = "short"
    try:
        with pytest.raises(RuntimeError, match="ARD_API_TOKEN"):
            relay.validate_configuration()
    finally:
        relay.API_TOKEN = original_token


def test_artifact_round_trip_requires_authorization_header() -> None:
    payload = b"open-source-ready"
    with TestClient(relay.app) as client:
        uploaded = client.post("/api/artifacts", content=payload, headers=AUTH)
        assert uploaded.status_code == 200
        artifact_id = uploaded.json()["artifact_id"]

        assert client.get(f"/api/artifacts/{artifact_id}?token={TEST_TOKEN}").status_code == 401
        downloaded = client.get(f"/api/artifacts/{artifact_id}", headers=AUTH)
        assert downloaded.status_code == 200
        assert downloaded.content == payload

        deleted = client.delete(f"/api/artifacts/{artifact_id}", headers=AUTH)
        assert deleted.json() == {"deleted": artifact_id}
        assert client.get(f"/api/artifacts/{artifact_id}", headers=AUTH).status_code == 404


def test_artifact_id_and_size_are_limited() -> None:
    original_limit = relay.MAX_ARTIFACT_BYTES
    relay.MAX_ARTIFACT_BYTES = 4
    try:
        with TestClient(relay.app) as client:
            assert client.post("/api/artifacts/bad.id", content=b"ok", headers=AUTH).status_code == 400
            assert client.post("/api/artifacts", content=b"12345", headers=AUTH).status_code == 413
            assert list(relay.ARTIFACT_DIR.iterdir()) == []
    finally:
        relay.MAX_ARTIFACT_BYTES = original_limit


def test_websocket_accepts_header_token() -> None:
    with TestClient(relay.app) as client:
        with client.websocket_connect("/ws/mobile/test-device", headers=AUTH) as socket:
            socket.send_json({"type": "hello", "name": "Test Device", "root": False})
            assert socket.receive_json() == {"type": "hello_ack", "deviceId": "test-device"}
