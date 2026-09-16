from fastapi import Request

from blue_chatbot.services import anthropic_model
from blue_chatbot.services.faq import FaqEntry
from blue_chatbot.services.model import ModelClient

_model: ModelClient | None = None


def get_faq(request: Request) -> list[FaqEntry]:
    return request.app.state.faq


def get_model() -> ModelClient:
    """구현체를 고르는 유일한 자리. 제공자를 바꾸면 이 한 줄만 바뀐다."""
    global _model
    if _model is None:
        _model = anthropic_model.build_from_config()
    return _model
