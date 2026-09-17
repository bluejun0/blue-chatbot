from typing import Any, TypeVar, cast

from pydantic import BaseModel
from blue_chatbot.messages import Message


T = TypeVar("T", bound=BaseModel)


class FakeLLMClient:
    """정해둔 결과를 돌려주거나 정해둔 예외를 던진다. 호출 인자를 기록한다."""

    def __init__(self, result: BaseModel | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def generate(
        self, *, system: str, messages: list[Message], output_format: type[T]
    ) -> T | None:
        self.calls.append(
            {"system": system, "messages": messages, "output_format": output_format}
        )
        if self._error is not None:
            raise self._error
        return cast(T | None, self._result)
