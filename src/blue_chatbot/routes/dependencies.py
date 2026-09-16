from fastapi import Request

from blue_chatbot.llm import anthropic_llm
from blue_chatbot.services.faq import FaqEntry
from blue_chatbot.services.llm import LLMModel

_model: LLMModel | None = None


def get_faq(request: Request) -> list[FaqEntry]:
    return request.app.state.faq


def get_model() -> LLMModel:
    """구현체를 고르는 유일한 자리. 제공자를 바꾸면 이 한 줄만 바뀐다."""
    global _model
    if _model is None:
        _model = anthropic_llm.build_from_config()
    return _model
