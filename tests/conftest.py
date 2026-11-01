"""Keep the test run independent of the developer's own .env.

A real GEMINI_API_KEY / ANTHROPIC_API_KEY in .env would otherwise make the tests call the live AI service and
remember which model answered. Tests that need a key set one themselves (see the ``key`` fixtures)."""
import pytest

from app import config, vision


@pytest.fixture(autouse=True)
def _no_live_ai(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "VISION_PROVIDER", "VISION_MODEL"):
        monkeypatch.setattr(config, name, "")
    monkeypatch.setattr(config, "READER_MODE", "auto")
    monkeypatch.setattr(vision, "_resolved", {})
