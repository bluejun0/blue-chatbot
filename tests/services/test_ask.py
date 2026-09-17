"""FAQ를 근거로 답을 만들고 근거 없는 답을 걸러내는지 확인한다."""

from typing import Any, TypeVar, cast

from pydantic import BaseModel

from blue_chatbot.services.ask import Answer, _validate_answer, answer
from blue_chatbot.services.faq import FaqEntry
from blue_chatbot.services.llm import LLMClient, Message

T = TypeVar("T", bound=BaseModel)

FAQS = [
    FaqEntry(id="refund", question="환불 되나요?", answer="7일 이내 가능합니다."),
]
FALLBACK = "질문에 알맞은 대답을 찾을 수 없습니다."


class FakeLLMClient:
    """정해둔 답을 그대로 돌려준다."""

    def __init__(self, result: Answer | None) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    def generate(
        self, *, system: str, messages: list[Message], output_format: type[T]
    ) -> T | None:
        self.calls.append(
            {"system": system, "messages": messages, "output_format": output_format}
        )
        return cast(T | None, self._result)


def ask(client: FakeLLMClient, question: str = "환불 되나요?") -> Answer:
    return answer(client, FAQS, [Message(role="user", content=question)])


def test_가짜가_LLMClient_프로토콜을_만족한다() -> None:
    # 이 대입이 타입 검사를 통과한다는 것 자체가 검증이다.
    client: LLMClient = FakeLLMClient(None)

    assert client.generate(system="", messages=[], output_format=Answer) is None


# --- _validate_answer: 근거 검증 규칙 -------------------------------------


def test_실재하는_matched_id면_그대로_통과한다() -> None:
    raw = Answer(content="7일 이내 가능합니다.", matched_id="refund")

    assert _validate_answer(raw, FAQS) == raw


def test_matched_id가_없으면_거부한다() -> None:
    raw = Answer(content="아마 가능할 겁니다.", matched_id=None)

    assert _validate_answer(raw, FAQS).content == FALLBACK


def test_존재하지_않는_matched_id면_거부한다() -> None:
    raw = Answer(content="그럴듯한 답", matched_id="지어낸-id")

    result = _validate_answer(raw, FAQS)

    assert result.content == FALLBACK
    assert result.matched_id is None


# --- answer: LLMClient를 통한 동작 ----------------------------------------


def test_검증을_통과한_응답을_그대로_돌려준다() -> None:
    parsed = Answer(content="7일 이내 가능합니다.", matched_id="refund")

    assert ask(FakeLLMClient(parsed)) == parsed


def test_지어낸_matched_id는_고정_문구로_바뀐다() -> None:
    parsed = Answer(content="지어낸 답", matched_id="없는-id")

    assert ask(FakeLLMClient(parsed), "배송 문의").content == FALLBACK


def test_모델이_쓸_만한_출력을_못_주면_고정_문구를_돌려준다() -> None:
    assert ask(FakeLLMClient(None)).content == FALLBACK


def test_FAQ를_시스템_프롬프트로_넘긴다() -> None:
    client = FakeLLMClient(Answer(content="답", matched_id="refund"))

    ask(client)

    assert "refund" in client.calls[0]["system"]


def test_메시지_목록과_출력_형식을_그대로_넘긴다() -> None:
    client = FakeLLMClient(Answer(content="답", matched_id="refund"))
    messages = [
        Message(role="user", content="환불 되나요?"),
        Message(role="assistant", content="7일 이내 가능합니다."),
        Message(role="user", content="배송은요?"),
    ]

    answer(client, FAQS, messages)

    assert client.calls[0]["messages"] == messages
    assert client.calls[0]["output_format"] is Answer
