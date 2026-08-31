import pytest

from otterai_mcp.settings import Settings


def test_settings_accepts_library_variable_names(monkeypatch):
    monkeypatch.setenv("OTTERAI_USERNAME", "user")
    monkeypatch.setenv("OTTERAI_PASSWORD", "password")

    assert Settings.from_env() == Settings(username="user", password="password")


def test_settings_requires_credentials(monkeypatch):
    for name in (
        "OTTERAI_USERNAME",
        "OTTERAI_PASSWORD",
        "OTTER_USERNAME",
        "OTTER_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="OTTERAI_USERNAME"):
        Settings.from_env()

