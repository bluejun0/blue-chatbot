"""Anthropic SDK로 모델 경계를 구현한다. anthropic import는 이 파일에만 둔다."""

import logging
from typing import TypeVar

import anthropic
from anthropic.types import OutputConfigParam
from pydantic import BaseModel

from blue_chatbot.configs.core import config
from blue_chatbot.services.llm import (
    Message,
    LLMRequestError,
    LLMRateLimitError,
    LLMUnreachableError,
    LLMUpstreamError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _output_config() -> OutputConfigParam | anthropic.Omit:
    if not config.effort:
        return anthropic.omit
    return {"effort": config.effort}


class AnthropicLLM:
    def __init__(self, client: anthropic.Anthropic):
        self._client = client

    def generate(
        self, *, system: str, messages: list[Message], output_format: type[T]
    ) -> T | None:
        """구조화된 답을 받아낸다. 쓸 만한 출력을 못 받으면 None을 돌려준다."""
        try:
            message = self._client.messages.parse(
                model=config.claude_model,
                max_tokens=config.max_tokens,
                output_config=_output_config(),
                system=system,
                messages=[m.model_dump() for m in messages],
                output_format=output_format,
            )
        except anthropic.RateLimitError as exc:
            retry_after = int(exc.response.headers.get("retry-after", "60"))
            raise LLMRateLimitError(retry_after) from exc
        except (anthropic.APIConnectionError, anthropic.APITimeoutError) as exc:
            raise LLMUnreachableError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMUpstreamError(str(exc)) from exc
            raise LLMRequestError(str(exc)) from exc

        if message.stop_reason == "refusal":
            return None

        if message.parsed_output is None:
            logger.warning("구조화 출력 파싱 실패 (stop_reason=%s)", message.stop_reason)
            return None

        return message.parsed_output


def build_from_config() -> AnthropicLLM:
    """설정으로 SDK 클라이언트를 만들어 경계 구현체에 싼다."""
    key = config.anthropic_api_key
    return AnthropicLLM(
        anthropic.Anthropic(api_key=key.get_secret_value() if key else None)
    )
