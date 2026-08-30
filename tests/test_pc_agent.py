import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "ard_pc_agent", PROJECT_ROOT / "pc-agent" / "agent.py"
)
assert spec and spec.loader
agent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = agent
spec.loader.exec_module(agent)


def test_websocket_url_does_not_contain_token() -> None:
    host = agent.HostAgent(
        "wss://relay.example/ws/mobile",
        "secret-token-that-is-longer-than-thirty-two-characters",
        "host-test",
        "Test Host",
        "adb",
        "fastboot",
    )
    assert host.url() == "wss://relay.example/ws/mobile/host-test"
    assert "token" not in host.url()


def test_connection_settings_reject_insecure_values() -> None:
    valid_token = "secret-token-that-is-longer-than-thirty-two-characters"
    assert agent.settings_error("https://relay.example/ws/mobile", valid_token, "host-test")
    assert agent.settings_error("wss://relay.example/ws/mobile", "short", "host-test")
    assert agent.settings_error("wss://relay.example/ws/mobile", valid_token, "host/test")
    assert agent.settings_error("wss://relay.example/ws/mobile", valid_token, "host-test") is None
