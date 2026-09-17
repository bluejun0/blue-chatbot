from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlmodel import SQLModel

from blue_chatbot.repositories.conversation import (
    Conversation,
    ConversationMessage,
    ConversationMessageRepository,
    ConversationRepository,
)
from blue_chatbot.support import utc_now


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def conversations(engine: Engine) -> ConversationRepository:
    return ConversationRepository(engine)


@pytest.fixture
def messages(engine: Engine) -> ConversationMessageRepository:
    return ConversationMessageRepository(engine)


def saved(conversations: ConversationRepository, key: str = "key-1") -> Conversation:
    conversation = Conversation(key=key, created_at=utc_now())
    conversations.save(conversation)
    return conversation


def message(conversation: Conversation, role: str, content: str) -> ConversationMessage:
    return ConversationMessage(
        conversation_id=conversation.persisted_id(), role=role, content=content, created_at=utc_now()
    )


# --- ConversationRepository ------------------------------------------------


def test_저장하면_id가_채워진다(conversations: ConversationRepository) -> None:
    conversation = Conversation(key="key-1", created_at=utc_now())

    conversations.save(conversation)

    assert conversation.id is not None


def test_저장한_대화를_키로_찾는다(conversations: ConversationRepository) -> None:
    conversation = saved(conversations)

    found = conversations.find_by_key("key-1")

    assert found is not None
    assert (found.id, found.key) == (conversation.id, conversation.key)


def test_없는_키면_None을_돌려준다(conversations: ConversationRepository) -> None:
    assert conversations.find_by_key("없는-키") is None


def test_저장_전_대화는_id를_요구할_수_없다() -> None:
    with pytest.raises(ValueError):
        Conversation(key="unsaved", created_at=utc_now()).persisted_id()


# --- ConversationMessageRepository -----------------------------------------


def test_새_대화는_메시지가_없다(
    conversations: ConversationRepository, messages: ConversationMessageRepository
) -> None:
    assert messages.find_messages(saved(conversations).persisted_id()) == []


def test_저장한_메시지를_순서대로_돌려준다(
    conversations: ConversationRepository, messages: ConversationMessageRepository
) -> None:
    conversation = saved(conversations)
    messages.save(message(conversation, "user", "연차 어떻게 신청해요?"))
    messages.save(message(conversation, "assistant", "포털 > 근태에서 신청합니다."))

    stored = messages.find_messages(conversation.persisted_id())

    assert [(m.role, m.content) for m in stored] == [
        ("user", "연차 어떻게 신청해요?"),
        ("assistant", "포털 > 근태에서 신청합니다."),
    ]


def test_다른_대화의_메시지는_섞이지_않는다(
    conversations: ConversationRepository, messages: ConversationMessageRepository
) -> None:
    first = saved(conversations, "key-1")
    second = saved(conversations, "key-2")
    messages.save(message(first, "user", "첫 대화"))
    messages.save(message(second, "user", "둘째 대화"))

    assert [m.content for m in messages.find_messages(first.persisted_id())] == ["첫 대화"]
