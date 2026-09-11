from pathlib import Path

import pytest
from pydantic import ValidationError

from blue_chatbot.configs.core import CoreConfig


def test_기본값():
    config = CoreConfig()

    assert config.claude_model == "claude-sonnet-5"
    assert config.max_tokens == 16000
    assert config.effort == "low"
    assert config.faq_path == Path("data/faq.yaml")


def test_환경변수로_덮어쓸_수_있다(monkeypatch):
    monkeypatch.setenv("FAQ_PATH", "/etc/other.yaml")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-opus-5")

    config = CoreConfig()

    assert config.faq_path == Path("/etc/other.yaml")
    assert config.claude_model == "claude-opus-5"


def test_effort_오타는_기동_시점에_거부된다():
    with pytest.raises(ValidationError, match="literal_error"):
        CoreConfig(effort="lowe")


@pytest.mark.parametrize("value", ["low", "medium", "high", "xhigh", "max"])
def test_허용된_effort_값(value):
    assert CoreConfig(effort=value).effort == value
