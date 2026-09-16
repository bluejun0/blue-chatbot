"""실제 Claude API를 호출하는 테스트. 비용이 발생한다.

실행: uv run pytest -m smoke
"""

from pathlib import Path

import anthropic
import pytest

from blue_chatbot.services.ask import answer
from blue_chatbot.services.faq import load


@pytest.fixture(scope="module")
def faqs():
    return load(Path("data/faq.yaml"))


@pytest.mark.smoke
def test_FAQ에_있는_질문에_근거를_밝히며_답한다(faqs):
    result = answer(anthropic.Anthropic(), faqs, "점심 몇 시부터예요?")

    assert result.matched_id == "lunch-time"
    assert result.content


@pytest.mark.smoke
def test_FAQ에_없는_질문은_답하지_않는다(faqs):
    result = answer(anthropic.Anthropic(), faqs, "오늘 서울 날씨 어때요?")

    assert result.matched_id is None
    assert result.content == "질문에 알맞은 대답을 찾을 수 없습니다."
