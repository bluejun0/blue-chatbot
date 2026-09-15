from pathlib import Path

import pytest
from pydantic import ValidationError

from blue_chatbot.configs.core import CoreConfig


def test_기본값(monkeypatch):
    # 기본값을 보려면 .env와 환경변수 양쪽을 모두 걷어내야 한다.
    for name in ("FAQ_PATH", "CLAUDE_MODEL", "MAX_TOKENS", "EFFORT"):
        monkeypatch.delenv(name, raising=False)

    config = CoreConfig(_env_file=None)

    assert config.claude_model == "claude-sonnet-5"
    assert config.max_tokens == 16000
    assert config.effort == "low"
    assert config.faq_path == Path("data/faq.yaml")


def test_api_key는_없어도_된다(monkeypatch):
    # SDK가 환경변수와 ant auth login 프로필을 직접 읽으므로 필수가 아니다.
    # _env_file=None으로 로컬 .env의 영향을 차단한다.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert CoreConfig(_env_file=None).anthropic_api_key is None


def test_api_key는_로그에_노출되지_않는다(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-비밀")

    config = CoreConfig(_env_file=None)

    assert "비밀" not in repr(config)
    assert "비밀" not in str(config.model_dump())
    assert config.anthropic_api_key.get_secret_value() == "sk-ant-비밀"


def test_환경변수로_덮어쓸_수_있다(monkeypatch):
    monkeypatch.setenv("FAQ_PATH", "/etc/other.yaml")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-opus-5")

    config = CoreConfig(_env_file=None)

    assert config.faq_path == Path("/etc/other.yaml")
    assert config.claude_model == "claude-opus-5"


def test_effort_오타는_기동_시점에_거부된다():
    with pytest.raises(ValidationError, match="literal_error"):
        CoreConfig(_env_file=None, effort="lowe")


@pytest.mark.parametrize("value", ["low", "medium", "high", "xhigh", "max"])
def test_허용된_effort_값(value):
    assert CoreConfig(_env_file=None, effort=value).effort == value


def test_effort는_비울_수_있다(monkeypatch):
    # Sonnet 4.5, Haiku 4.5처럼 effort를 받지 않는 모델을 쓸 때 필요하다.
    monkeypatch.setenv("EFFORT", "")

    assert CoreConfig(_env_file=None).effort is None
