import anthropic
from fastapi import Request

from blue_chatbot.services.faq import FaqEntry

_client: anthropic.Anthropic | None = None


def get_faq(request: Request) -> list[FaqEntry]:
    return request.app.state.faq


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client
