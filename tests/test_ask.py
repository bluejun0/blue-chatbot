from types import SimpleNamespace

import anthropic
import pytest

from blue_chatbot.configs.core import config
from blue_chatbot.services.ask import Answer, _validate_answer, answer
from blue_chatbot.services.faq import FaqEntry

FAQS = [
    FaqEntry(id="refund", question="환불 되나요?", answer="7일 이내 가능합니다."),
]
FALLBACK = "질문에 알맞은 대답을 찾을 수 없습니다."


class FakeClient:
    """messages.parse만 흉내내는 가짜 Anthropic 클라이언트."""

    def __init__(self, parsed: Answer | None, stop_reason: str = "end_turn"):
        message = SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason)
        self.calls: list[dict] = []

        def parse(**kwargs):
            self.calls.append(kwargs)
            return message

        self.messages = SimpleNamespace(parse=parse)


# --- _validate_answer: 근거 검증 규칙 -------------------------------------


def test_실재하는_matched_id면_그대로_통과한다():
    raw = Answer(content="7일 이내 가능합니다.", matched_id="refund")

    assert _validate_answer(raw, FAQS) == raw


def test_matched_id가_없으면_거부한다():
    raw = Answer(content="아마 가능할 겁니다.", matched_id=None)

    assert _validate_answer(raw, FAQS).content == FALLBACK


def test_존재하지_않는_matched_id면_거부한다():
    raw = Answer(content="그럴듯한 답", matched_id="지어낸-id")

    result = _validate_answer(raw, FAQS)

    assert result.content == FALLBACK
    assert result.matched_id is None


# --- answer: 호출과 예외 경로 ---------------------------------------------


def test_검증을_통과한_응답을_그대로_돌려준다():
    parsed = Answer(content="7일 이내 가능합니다.", matched_id="refund")

    assert answer(FakeClient(parsed), FAQS, "환불 되나요?") == parsed


def test_지어낸_matched_id는_고정_문구로_바뀐다():
    parsed = Answer(content="지어낸 답", matched_id="없는-id")

    assert answer(FakeClient(parsed), FAQS, "배송 문의").content == FALLBACK


def test_refusal이면_고정_문구를_돌려준다():
    parsed = Answer(content="무언가", matched_id="refund")

    result = answer(FakeClient(parsed, stop_reason="refusal"), FAQS, "무언가")

    assert result.content == FALLBACK


def test_구조화_출력_파싱에_실패하면_고정_문구를_돌려준다(caplog):
    result = answer(FakeClient(None), FAQS, "무언가")

    assert result.content == FALLBACK
    assert "파싱 실패" in caplog.text


def test_호출_파라미터가_설정을_따른다(monkeypatch):
    # 로컬 .env의 EFFORT에 좌우되지 않도록 값을 고정한다.
    monkeypatch.setattr(config, "effort", "low")
    parsed = Answer(content="답", matched_id="refund")
    client = FakeClient(parsed)

    answer(client, FAQS, "환불 되나요?")

    kwargs = client.calls[0]
    assert kwargs["model"] == config.claude_model
    assert kwargs["max_tokens"] == config.max_tokens
    assert kwargs["output_config"] == {"effort": config.effort}
    assert kwargs["output_format"] is Answer
    assert kwargs["messages"] == [{"role": "user", "content": "환불 되나요?"}]
    assert "thinking" not in kwargs
    assert "refund" in kwargs["system"]


def test_effort가_비면_output_config를_보내지_않는다(monkeypatch):
    # effort를 지원하지 않는 모델에 이 파라미터를 넘기면 400이 난다.
    # Omit은 SDK가 요청 본문에서 파라미터를 빼는 센티널이다.
    monkeypatch.setattr(config, "effort", None)
    client = FakeClient(Answer(content="답", matched_id="refund"))

    answer(client, FAQS, "환불 되나요?")

    assert isinstance(client.calls[0]["output_config"], anthropic.Omit)
