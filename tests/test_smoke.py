"""실제 Claude API를 호출하는 테스트. 비용이 발생한다.

실행: uv run pytest -m smoke
"""

from pathlib import Path

import pytest

from blue_chatbot.services.anthropic_model import build_from_config
from blue_chatbot.services.ask import answer
from blue_chatbot.services.faq import load
from blue_chatbot.services.model import Message


@pytest.fixture(scope="module")
def faqs():
    return load(Path("data/faq.yaml"))


@pytest.fixture(scope="module")
def model():
    return build_from_config()


def ask(model, faqs, question: str):
    return answer(model, faqs, [Message(role="user", content=question)])


@pytest.mark.smoke
def test_FAQ에_있는_질문에_근거를_밝히며_답한다(model, faqs):
    result = ask(model, faqs, "점심 몇 시부터예요?")

    assert result.matched_id == "lunch-time"
    assert result.content


@pytest.mark.smoke
def test_FAQ에_없는_질문은_답하지_않는다(model, faqs):
    result = ask(model, faqs, "오늘 서울 날씨 어때요?")

    assert result.matched_id is None
    assert result.content == "질문에 알맞은 대답을 찾을 수 없습니다."
