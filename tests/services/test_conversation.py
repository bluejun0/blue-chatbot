"""대화를 가져오거나 만들고, 메시지를 보내면 이력이 저장·전달되는지 확인한다."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import Engine, create_engine

from blue_chatbot.repositories.conversation import (
    ConversationMessageRepository,
    ConversationRepository,
)
from sqlmodel import SQLModel
from blue_chatbot.services.ask import LLMAnswer
from blue_chatbot.services.conversation import (
    ConversationExpiredError,
    ConversationNotFoundError,
    ConversationService,
)
from blue_chatbot.services.faq import FaqEntry
from tests.clock import FakeClock
from tests.fakes import FakeLLMClient

FAQS = [
    FaqEntry(id="refund", question="환불 되나요?", answer="7일 이내 가능합니다."),
]
EXPIRES_AFTER = timedelta(minutes=30)
A_SECOND = timedelta(seconds=1)


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def llm_client() -> FakeLLMClient:
    return FakeLLMClient(LLMAnswer(content="7일 이내 가능합니다.", matched_id="refund"))


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def service(engine: Engine, llm_client: FakeLLMClient, clock: FakeClock) -> ConversationService:
    return ConversationService(
        ConversationRepository(engine),
        ConversationMessageRepository(engine),
        llm_client,
        FAQS,
        EXPIRES_AFTER,
        now=clock,
    )


def new_key(service: ConversationService) -> str:
    conversation, _ = service.get_conversation(None)
    return conversation.key


# --- get_conversation ------------------------------------------------------


def test_키가_없으면_새_대화를_만든다(service: ConversationService) -> None:
    conversation, stored = service.get_conversation(None)

    assert len(conversation.key) == 36
    assert stored == []


def test_유효한_키면_같은_대화를_돌려준다(service: ConversationService) -> None:
    key = new_key(service)

    conversation, _ = service.get_conversation(key)

    assert conversation.key == key


def test_모르는_키면_새_대화를_만든다(service: ConversationService) -> None:
    conversation, stored = service.get_conversation("없는-키")

    assert conversation.key != "없는-키"
    assert stored == []


def test_만료된_키면_새_대화를_만든다(service: ConversationService, clock: FakeClock) -> None:
    key = new_key(service)
    service.send_message(key, "환불 되나요?")
    clock.advance(EXPIRES_AFTER + A_SECOND)

    conversation, stored = service.get_conversation(key)

    assert conversation.key != key
    assert stored == []


def test_메시지가_없는_대화도_만든_시각_기준으로_만료된다(
    service: ConversationService, clock: FakeClock
) -> None:
    key = new_key(service)
    clock.advance(EXPIRES_AFTER + A_SECOND)

    conversation, _ = service.get_conversation(key)

    assert conversation.key != key


def test_만료_시간_정각까지는_유효하다(service: ConversationService, clock: FakeClock) -> None:
    key = new_key(service)
    clock.advance(EXPIRES_AFTER)

    conversation, _ = service.get_conversation(key)

    assert conversation.key == key


def test_대화의_메시지를_순서대로_돌려준다(service: ConversationService) -> None:
    key = new_key(service)
    service.send_message(key, "환불 되나요?")

    _, stored = service.get_conversation(key)

    assert [(m.role, m.content) for m in stored] == [
        ("user", "환불 되나요?"),
        ("assistant", "7일 이내 가능합니다."),
    ]


# --- send_message ----------------------------------------------------------


def test_이력에_새_질문을_붙여_role_순서대로_LLM에_넘긴다(
    service: ConversationService, llm_client: FakeLLMClient
) -> None:
    key = new_key(service)
    service.send_message(key, "환불 되나요?")

    service.send_message(key, "배송은요?")

    assert [(m.role, m.content) for m in llm_client.calls[1]["messages"]] == [
        ("user", "환불 되나요?"),
        ("assistant", "7일 이내 가능합니다."),
        ("user", "배송은요?"),
    ]


def test_다른_대화의_이력은_섞이지_않는다(
    service: ConversationService, llm_client: FakeLLMClient
) -> None:
    first = new_key(service)
    second = new_key(service)
    service.send_message(first, "첫 대화")

    service.send_message(second, "둘째 대화")

    assert [m.content for m in llm_client.calls[1]["messages"]] == ["둘째 대화"]


def test_모르는_키에는_보낼_수_없다(service: ConversationService) -> None:
    with pytest.raises(ConversationNotFoundError):
        service.send_message("없는-키", "무언가")


def test_만료된_대화에는_보낼_수_없다(service: ConversationService, clock: FakeClock) -> None:
    key = new_key(service)
    clock.advance(EXPIRES_AFTER + A_SECOND)

    with pytest.raises(ConversationExpiredError):
        service.send_message(key, "무언가")


def test_메시지를_보내면_만료가_연장된다(service: ConversationService, clock: FakeClock) -> None:
    key = new_key(service)
    clock.advance(EXPIRES_AFTER - A_SECOND)
    service.send_message(key, "환불 되나요?")
    clock.advance(EXPIRES_AFTER - A_SECOND)

    conversation, _ = service.get_conversation(key)

    assert conversation.key == key


def test_LLM이_실패해도_질문은_저장된다(engine: Engine, clock: FakeClock) -> None:
    # 트랜잭션으로 묶지 않는다. 다음 턴 이력에 user 메시지가 연달아 남는다.
    failing = FakeLLMClient(error=RuntimeError("LLM 실패"))
    service = ConversationService(
        ConversationRepository(engine),
        ConversationMessageRepository(engine),
        failing,
        FAQS,
        EXPIRES_AFTER,
        now=clock,
    )
    key = new_key(service)

    with pytest.raises(RuntimeError):
        service.send_message(key, "환불 되나요?")

    _, stored = service.get_conversation(key)
    assert [(m.role, m.content) for m in stored] == [("user", "환불 되나요?")]
