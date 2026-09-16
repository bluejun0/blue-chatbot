from fastapi import Request

from blue_chatbot.llm import anthropic_llm
from blue_chatbot.services.faq import FaqEntry
from blue_chatbot.services.llm import LLMClient

_model: LLMClient | None = None


def get_faq(request: Request) -> list[FaqEntry]:
    # app.state는 Any라 반환 전에 타입을 고정한다.
    entries: list[FaqEntry] = request.app.state.faq
    return entries


def get_model() -> LLMClient:
    """구현체를 고르는 유일한 자리. 제공자를 바꾸면 이 한 줄만 바뀐다."""
    global _model
    if _model is None:
        _model = anthropic_llm.build_from_config()
    return _model
