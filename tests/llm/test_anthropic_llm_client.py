"""SDK 예외를 애플리케이션 예외로 변환하는지, 설정을 요청에 반영하는지 확인한다."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2 as httpx
import pytest
from pydantic import BaseModel

from blue_chatbot.messages import Message
from blue_chatbot.configs.core import config
from blue_chatbot.llm.anthropic_llm import AnthropicLLMClient
from blue_chatbot.services.llm import (
    LLMClientRateLimitError,
    LLMClientRequestError,
    LLMClientUnreachableError,
    LLMClientVendorError,
)

REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


class Reply(BaseModel):
    content: str


def fake_sdk(
    *,
    parsed: Reply | None = None,
    error: Exception | None = None,
    stop_reason: str = "end_turn",
) -> Any:
    """messages.parse만 흉내내는 가짜 Anthropic SDK 클라이언트."""
    calls: list[dict[str, Any]] = []

    def parse(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        if error is not None:
            raise error
        return SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason)

    return SimpleNamespace(messages=SimpleNamespace(parse=parse), calls=calls)


def status_error(kind: type[Any], status_code: int, message: str = "오류") -> Any:
    response = type(
        "R", (), {"headers": {}, "status_code": status_code, "request": REQUEST}
    )()
    return kind(message, response=response, body=None)


def rate_limit_error(retry_after: str) -> anthropic.RateLimitError:
    response = type(
        "R",
        (),
        {"headers": {"retry-after": retry_after}, "status_code": 429, "request": REQUEST},
    )()
    return anthropic.RateLimitError("rate limited", response=response, body=None)


def call(client: AnthropicLLMClient) -> Reply | None:
    return client.generate(
        system="지시",
        messages=[Message(role="user", content="질문")],
        output_format=Reply,
    )


# --- SDK 예외를 앱 예외로 번역한다 -----------------------------------------


def test_요청량_초과를_번역하고_retry_after를_보존한다() -> None:
    client = AnthropicLLMClient(fake_sdk(error=rate_limit_error("30")))

    with pytest.raises(LLMClientRateLimitError) as caught:
        call(client)

    assert caught.value.retry_after == 30


def test_연결_실패를_번역한다() -> None:
    client = AnthropicLLMClient(fake_sdk(error=anthropic.APIConnectionError(request=REQUEST)))

    with pytest.raises(LLMClientUnreachableError):
        call(client)


def test_타임아웃을_번역한다() -> None:
    client = AnthropicLLMClient(fake_sdk(error=anthropic.APITimeoutError(request=REQUEST)))

    with pytest.raises(LLMClientUnreachableError):
        call(client)


def test_제공자_5xx를_번역한다() -> None:
    client = AnthropicLLMClient(fake_sdk(error=status_error(anthropic.APIStatusError, 529)))

    with pytest.raises(LLMClientVendorError):
        call(client)


def test_인증_오류를_번역한다() -> None:
    client = AnthropicLLMClient(fake_sdk(error=status_error(anthropic.AuthenticationError, 401)))

    with pytest.raises(LLMClientRequestError):
        call(client)


def test_제공자_4xx를_번역한다() -> None:
    client = AnthropicLLMClient(fake_sdk(error=status_error(anthropic.APIStatusError, 400)))

    with pytest.raises(LLMClientRequestError):
        call(client)


# --- 쓸 만한 출력을 못 받으면 None --------------------------------------


def test_파싱된_결과를_그대로_돌려준다() -> None:
    reply = Reply(content="답변")

    assert call(AnthropicLLMClient(fake_sdk(parsed=reply))) == reply


def test_refusal이면_None을_돌려준다() -> None:
    sdk = fake_sdk(parsed=Reply(content="무언가"), stop_reason="refusal")

    assert call(AnthropicLLMClient(sdk)) is None


def test_구조화_출력_파싱에_실패하면_None을_돌려준다(caplog: pytest.LogCaptureFixture) -> None:
    assert call(AnthropicLLMClient(fake_sdk(parsed=None))) is None
    assert "파싱 실패" in caplog.text


# --- 설정을 요청에 반영한다 ------------------------------------------------


def test_호출_파라미터가_설정을_따른다(monkeypatch: pytest.MonkeyPatch) -> None:
    # 로컬 .env의 EFFORT에 좌우되지 않도록 값을 고정한다.
    monkeypatch.setattr(config, "effort", "low")
    sdk = fake_sdk(parsed=Reply(content="답"))

    AnthropicLLMClient(sdk).generate(
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


def test_effort가_비면_output_config를_보내지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    # effort를 지원하지 않는 모델에 이 파라미터를 넘기면 400이 난다.
    # Omit은 SDK가 요청 본문에서 파라미터를 빼는 센티널이다.
    monkeypatch.setattr(config, "effort", None)
    sdk = fake_sdk(parsed=Reply(content="답"))

    AnthropicLLMClient(sdk).generate(
        system="지시",
        messages=[Message(role="user", content="질문")],
        output_format=Reply,
    )

    assert isinstance(sdk.calls[0]["output_config"], anthropic.Omit)
