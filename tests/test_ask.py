from blue_chatbot.services.ask import Answer, _validate_answer, answer
from blue_chatbot.services.faq import FaqEntry
from blue_chatbot.services.model import Message

FAQS = [
    FaqEntry(id="refund", question="환불 되나요?", answer="7일 이내 가능합니다."),
]
FALLBACK = "질문에 알맞은 대답을 찾을 수 없습니다."


class FakeModel:
    """모델 경계만 흉내낸다. 어떤 SDK도 알지 않는다."""

    def __init__(self, result: Answer | None):
        self._result = result
        self.calls: list[dict] = []

    def generate(self, *, system, messages, output_format):
        self.calls.append(
            {"system": system, "messages": messages, "output_format": output_format}
        )
        return self._result


def ask(model, question: str = "환불 되나요?") -> Answer:
    return answer(model, FAQS, [Message(role="user", content=question)])


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


# --- answer: 경계 위에서의 동작 -------------------------------------------


def test_검증을_통과한_응답을_그대로_돌려준다():
    parsed = Answer(content="7일 이내 가능합니다.", matched_id="refund")

    assert ask(FakeModel(parsed)) == parsed


def test_지어낸_matched_id는_고정_문구로_바뀐다():
    parsed = Answer(content="지어낸 답", matched_id="없는-id")

    assert ask(FakeModel(parsed), "배송 문의").content == FALLBACK


def test_모델이_쓸_만한_출력을_못_주면_고정_문구를_돌려준다():
    assert ask(FakeModel(None)).content == FALLBACK


def test_FAQ를_시스템_프롬프트로_넘긴다():
    model = FakeModel(Answer(content="답", matched_id="refund"))

    ask(model)

    assert "refund" in model.calls[0]["system"]


def test_발화_목록과_출력_형식을_그대로_넘긴다():
    model = FakeModel(Answer(content="답", matched_id="refund"))
    messages = [
        Message(role="user", content="환불 되나요?"),
        Message(role="assistant", content="7일 이내 가능합니다."),
        Message(role="user", content="배송은요?"),
    ]

    answer(model, FAQS, messages)

    assert model.calls[0]["messages"] == messages
    assert model.calls[0]["output_format"] is Answer
