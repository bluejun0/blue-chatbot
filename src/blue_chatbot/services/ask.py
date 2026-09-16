from pydantic import BaseModel

from blue_chatbot.services.faq import FaqEntry
from blue_chatbot.services.llm import Message, LLMModel
from blue_chatbot.services.prompt import build_prompt_system


class Answer(BaseModel):
    content: str
    matched_id: str | None = None


def _fallback() -> Answer:
    return Answer(content="질문에 알맞은 대답을 찾을 수 없습니다.", matched_id=None)


def _validate_answer(raw: Answer, faq: list[FaqEntry]) -> Answer:
    if raw.matched_id is None:
        return _fallback()
    if raw.matched_id not in {entry.id for entry in faq}:
        return _fallback()
    return raw


def answer(
    model: LLMModel, faqs: list[FaqEntry], messages: list[Message]
) -> Answer:
    """FAQ를 근거로 답한다. 근거가 없으면 고정 문구로 대체한다."""
    raw = model.generate(
        system=build_prompt_system(faqs),
        messages=messages,
        output_format=Answer,
    )

    if raw is None:
        return _fallback()

    return _validate_answer(raw, faqs)
