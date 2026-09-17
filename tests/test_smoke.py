"""실제 Claude API를 호출하는 테스트. 비용이 발생한다.

실행: uv run pytest -m smoke
"""

from pathlib import Path

import pytest

from blue_chatbot.repositories.conversation import ConversationMessage
from blue_chatbot.support import utc_now
from blue_chatbot.llm.anthropic_llm import build_from_config
from blue_chatbot.services.ask import LLMAnswer, answer
from blue_chatbot.services.faq import FaqEntry, load
from blue_chatbot.services.llm import LLMClient


@pytest.fixture(scope="module")
def faqs() -> list[FaqEntry]:
    return load(Path("data/faq.yaml"))


@pytest.fixture(scope="module")
def model() -> LLMClient:
    return build_from_config()


def ask(model: LLMClient, faqs: list[FaqEntry], question: str) -> LLMAnswer:
    question_message = ConversationMessage(
        conversation_id=0, role="user", content=question, created_at=utc_now()
    )
    return answer(model, faqs, [question_message])


@pytest.mark.smoke
def test_FAQ에_있는_질문에_근거를_밝히며_답한다(model: LLMClient, faqs: list[FaqEntry]) -> None:
    result = ask(model, faqs, "점심 몇 시부터예요?")

    assert result.matched_id == "lunch-time"
    assert result.content


@pytest.mark.smoke
def test_FAQ에_없는_질문은_답하지_않는다(model: LLMClient, faqs: list[FaqEntry]) -> None:
    result = ask(model, faqs, "오늘 서울 날씨 어때요?")

    assert result.matched_id is None
    assert result.content == "질문에 알맞은 대답을 찾을 수 없습니다."
