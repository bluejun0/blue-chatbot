from types import SimpleNamespace

import anthropic
import pytest
from pydantic import BaseModel

from blue_chatbot.configs.core import config
from blue_chatbot.llm.anthropic_llm import AnthropicLLM
from blue_chatbot.services.llm import (
    Message,
    LLMRequestError,
    LLMRateLimitError,
    LLMUnreachableError,
    LLMUpstreamError,
)


class Reply(BaseModel):
    content: str


def fake_sdk(*, parsed=None, error=None, stop_reason="end_turn"):
    """messages.parse만 흉내내는 가짜 Anthropic SDK 클라이언트."""
    calls: list[dict] = []

    def parse(**kwargs):
        calls.append(kwargs)
        if error is not None:
            raise error
        return SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason)

    return SimpleNamespace(messages=SimpleNamespace(parse=parse), calls=calls)


def rate_limit_error(retry_after: str) -> anthropic.RateLimitError:
    response = type(
        "R",
        (),
        {"headers": {"retry-after": retry_after}, "status_code": 429, "request": None},
    )()
    return anthropic.RateLimitError("rate limited", response=response, body=None)


def test_SDK의_요청량_초과를_LLMRateLimitError로_번역한다():
    client = AnthropicLLM(fake_sdk(error=rate_limit_error("30")))

    with pytest.raises(LLMRateLimitError) as caught:
        client.generate(
            system="지시",
            messages=[Message(role="user", content="질문")],
            output_format=Reply,
        )

    assert caught.value.retry_after == 30


def status_error(kind, status_code: int, message: str = "오류"):
    response = type(
        "R", (), {"headers": {}, "status_code": status_code, "request": None}
    )()
    return kind(message, response=response, body=None)


def call(client):
    return client.generate(
        system="지시",
        messages=[Message(role="user", content="질문")],
        output_format=Reply,
    )


def test_연결_실패를_LLMUnreachableError로_번역한다():
    client = AnthropicLLM(fake_sdk(error=anthropic.APIConnectionError(request=None)))

    with pytest.raises(LLMUnreachableError):
        call(client)


def test_타임아웃을_LLMUnreachableError로_번역한다():
    client = AnthropicLLM(fake_sdk(error=anthropic.APITimeoutError(request=None)))

    with pytest.raises(LLMUnreachableError):
        call(client)


def test_제공자_5xx를_LLMUpstreamError로_번역한다():
    error = status_error(anthropic.APIStatusError, 529, "overloaded")
    client = AnthropicLLM(fake_sdk(error=error))

    with pytest.raises(LLMUpstreamError):
        call(client)


def test_인증_오류를_LLMRequestError로_번역한다():
    error = status_error(anthropic.AuthenticationError, 401, "bad key")
    client = AnthropicLLM(fake_sdk(error=error))

    with pytest.raises(LLMRequestError):
        call(client)


def test_제공자_4xx를_LLMRequestError로_번역한다():
    error = status_error(anthropic.APIStatusError, 400, "bad request")
    client = AnthropicLLM(fake_sdk(error=error))

    with pytest.raises(LLMRequestError):
        call(client)


def test_파싱된_결과를_그대로_돌려준다():
    reply = Reply(content="답변")
    client = AnthropicLLM(fake_sdk(parsed=reply))

    assert call(client) == reply


def test_refusal이면_None을_돌려준다():
    client = AnthropicLLM(fake_sdk(parsed=Reply(content="무언가"), stop_reason="refusal"))

    assert call(client) is None


def test_구조화_출력_파싱에_실패하면_None을_돌려준다(caplog):
    client = AnthropicLLM(fake_sdk(parsed=None))

    assert call(client) is None
    assert "파싱 실패" in caplog.text


def test_호출_파라미터가_설정을_따른다(monkeypatch):
    # 로컬 .env의 EFFORT에 좌우되지 않도록 값을 고정한다.
    monkeypatch.setattr(config, "effort", "low")
    sdk = fake_sdk(parsed=Reply(content="답"))

    AnthropicLLM(sdk).generate(
        system="지시",
        messages=[Message(role="user", content="질문")],
        output_format=Reply,
    )

    kwargs = sdk.calls[0]
    assert kwargs["model"] == config.claude_model
    assert kwargs["max_tokens"] == config.max_tokens
    assert kwargs["output_config"] == {"effort": config.effort}
    assert kwargs["output_format"] is Reply
    assert kwargs["system"] == "지시"
    assert kwargs["messages"] == [{"role": "user", "content": "질문"}]
    assert "thinking" not in kwargs


def test_effort가_비면_output_config를_보내지_않는다(monkeypatch):
    # effort를 지원하지 않는 모델에 이 파라미터를 넘기면 400이 난다.
    # Omit은 SDK가 요청 본문에서 파라미터를 빼는 센티널이다.
    monkeypatch.setattr(config, "effort", None)
    sdk = fake_sdk(parsed=Reply(content="답"))

    AnthropicLLM(sdk).generate(
        system="지시",
        messages=[Message(role="user", content="질문")],
        output_format=Reply,
    )

    assert isinstance(sdk.calls[0]["output_config"], anthropic.Omit)


def test_경계_밖에서는_anthropic_SDK를_모른다():
    """제공자 교체 시 고칠 파일이 하나로 유지되는지 구조로 확인한다."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "src" / "blue_chatbot"
    boundary = root / "llm" / "anthropic_llm.py"
    importing = re.compile(r"^\s*(?:import anthropic|from anthropic)", re.MULTILINE)

    offenders = sorted(
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if path != boundary and importing.search(path.read_text(encoding="utf-8"))
    )

    assert offenders == []
