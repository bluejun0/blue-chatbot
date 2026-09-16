"""모델 호출 경계.

앱이 모델에게 필요로 하는 것만 정의한다. 특정 제공자의 SDK를 알지 않는다.
"""

from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel


class Message(BaseModel):
    """대화 한 줄. 제공자와 무관한 형태로 보관한다."""

    role: Literal["user", "assistant"]
    content: str


class ModelError(Exception):
    """모델 호출 실패."""


class ModelRateLimitError(ModelError):
    """요청량을 초과했다. retry_after 뒤에 다시 시도할 수 있다."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"요청량 초과. {retry_after}초 후 재시도")


class ModelUnreachableError(ModelError):
    """모델에 닿지 못했다. 연결 실패나 타임아웃. 재시도할 수 있다."""


class ModelUpstreamError(ModelError):
    """모델에 닿았지만 제공자 쪽에서 실패했다."""


class ModelRequestError(ModelError):
    """설정이나 요청이 잘못됐다. 그대로 재시도해도 소용없다."""


T = TypeVar("T", bound=BaseModel)


class ModelClient(Protocol):
    """앱이 모델에게 요구하는 전부."""

    def generate(
        self, *, system: str, messages: list[Message], output_format: type[T]
    ) -> T | None:
        """구조화된 답을 받아낸다. 쓸 만한 출력을 못 받으면 None."""
        ...
