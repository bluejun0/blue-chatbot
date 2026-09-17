"""라우트가 쿠키로 대화를 잇고, 예외를 어떤 HTTP 상태 코드로 변환하는지 확인한다."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from blue_chatbot.main import app
from blue_chatbot.repositories.conversation import (
    ConversationMessageRepository,
    ConversationRepository,
)
from sqlmodel import SQLModel
from blue_chatbot.routes.dependencies import COOKIE_NAME, get_conversation_service, get_faq
from blue_chatbot.services.ask import LLMAnswer
from blue_chatbot.services.conversation import ConversationService
from blue_chatbot.services.faq import FaqEntry
from blue_chatbot.services.llm import (
    LLMClientRateLimitError,
    LLMClientRequestError,
    LLMClientUnreachableError,
    LLMClientVendorError,
)
from tests.clock import FakeClock
from tests.fakes import FakeLLMClient

FAQS = [
    FaqEntry(id="refund", question="환불 되나요?", answer="7일 이내 가능합니다."),
]
FALLBACK = "질문에 알맞은 대답을 찾을 수 없습니다."
EXPIRES_AFTER = timedelta(minutes=30)


class Harness:
    """라우트 테스트가 LLM 응답과 시각을 바꿀 수 있게 서비스 조립을 대신한다."""

    def __init__(self) -> None:
        # TestClient는 앱을 다른 스레드에서 실행한다. 메모리 SQLite는 커넥션마다 별개라
        # 커넥션 하나를 모든 스레드가 공유하게 한다.
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        SQLModel.metadata.create_all(self.engine)
        self.clock = FakeClock()
        self.llm_client = FakeLLMClient(LLMAnswer(content="답", matched_id="refund"))

    def service(self) -> ConversationService:
        return ConversationService(
            ConversationRepository(self.engine),
            ConversationMessageRepository(self.engine),
            self.llm_client,
            FAQS,
            EXPIRES_AFTER,
            now=self.clock,
        )


@pytest.fixture
def harness() -> Iterator[Harness]:
    harness = Harness()
    app.dependency_overrides[get_faq] = lambda: FAQS
    app.dependency_overrides[get_conversation_service] = harness.service
    yield harness
    app.dependency_overrides.clear()
    harness.engine.dispose()


@pytest.fixture
def client(harness: Harness) -> TestClient:
    return TestClient(app)


def start(client: TestClient) -> str:
    """대화를 시작하고 쿠키의 key를 돌려준다. TestClient가 쿠키를 보관한다."""
    response = client.get("/conversations")
    assert response.status_code == 200
    return response.cookies[COOKIE_NAME]


def test_health가_faq_수를_알려준다(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "faq_count": 1}


# --- GET /conversations ----------------------------------------------------


def test_첫_요청은_새_대화와_쿠키를_준다(client: TestClient) -> None:
    response = client.get("/conversations")

    assert response.status_code == 200
    assert response.json()["messages"] == []
    assert len(response.cookies[COOKIE_NAME]) == 36
    assert response.headers["cache-control"] == "no-store"


def test_쿠키는_HttpOnly이고_만료_시간이_서버와_같다(client: TestClient) -> None:
    response = client.get("/conversations")

    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert f"max-age={int(EXPIRES_AFTER.total_seconds())}" in set_cookie


def test_쿠키가_있으면_같은_대화를_준다(client: TestClient) -> None:
    key = start(client)

    assert client.get("/conversations").json()["key"] == key


def test_만료된_대화면_새_대화를_준다(client: TestClient, harness: Harness) -> None:
    key = start(client)
    harness.clock.advance(EXPIRES_AFTER + timedelta(seconds=1))

    assert client.get("/conversations").json()["key"] != key


# --- POST /ask ---------------------------------------------------------------


def test_쿠키_없이_보내면_404다(client: TestClient) -> None:
    assert client.post("/ask", json={"question": "환불 되나요?"}).status_code == 404


def test_모르는_키_쿠키로_보내면_404다(client: TestClient) -> None:
    client.cookies.set(COOKIE_NAME, "unknown-key")

    assert client.post("/ask", json={"question": "환불 되나요?"}).status_code == 404


def test_만료된_대화에_보내면_409다(client: TestClient, harness: Harness) -> None:
    start(client)
    harness.clock.advance(EXPIRES_AFTER + timedelta(seconds=1))

    assert client.post("/ask", json={"question": "환불 되나요?"}).status_code == 409


def test_정상_답변(client: TestClient, harness: Harness) -> None:
    harness.llm_client = FakeLLMClient(LLMAnswer(content="7일 이내 가능합니다.", matched_id="refund"))
    start(client)

    response = client.post("/ask", json={"question": "환불 되나요?"})

    assert response.status_code == 200
    assert response.json() == {"content": "7일 이내 가능합니다.", "matched_id": "refund"}


def test_답을_받으면_대화에_쌓이고_다음_질문에_이력이_붙는다(
    client: TestClient, harness: Harness
) -> None:
    start(client)
    client.post("/ask", json={"question": "환불 되나요?"})

    client.post("/ask", json={"question": "배송은요?"})

    assert [(m.role, m.content) for m in harness.llm_client.calls[1]["messages"]] == [
        ("user", "환불 되나요?"),
        ("assistant", "답"),
        ("user", "배송은요?"),
    ]
    assert [m["content"] for m in client.get("/conversations").json()["messages"]] == [
        "환불 되나요?", "답", "배송은요?", "답",
    ]


def test_근거_없는_답변은_고정_문구로_내려간다(client: TestClient, harness: Harness) -> None:
    harness.llm_client = FakeLLMClient(LLMAnswer(content="지어낸 답", matched_id="없는-id"))
    start(client)

    response = client.post("/ask", json={"question": "배송 문의"})

    assert response.json() == {"content": FALLBACK, "matched_id": None}


@pytest.mark.parametrize("payload", [{"question": ""}, {"question": "   "}, {}])
def test_질문이_비면_422다(client: TestClient, payload: dict[str, str]) -> None:
    assert client.post("/ask", json=payload).status_code == 422


def test_질문_앞뒤_공백은_제거된다(client: TestClient, harness: Harness) -> None:
    start(client)

    client.post("/ask", json={"question": "  환불 되나요?  "})

    assert [m.content for m in harness.llm_client.calls[0]["messages"]] == ["환불 되나요?"]


def fail_with(harness: Harness, error: Exception) -> None:
    harness.llm_client = FakeLLMClient(error=error)


def test_요청량_초과면_429다(client: TestClient, harness: Harness) -> None:
    fail_with(harness, LLMClientRateLimitError(retry_after=30))
    start(client)

    response = client.post("/ask", json={"question": "환불 되나요?"})

    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"


def test_LLM에_접속하지_못하면_503이다(client: TestClient, harness: Harness) -> None:
    fail_with(harness, LLMClientUnreachableError("연결 실패"))
    start(client)

    assert client.post("/ask", json={"question": "환불 되나요?"}).status_code == 503


def test_제공자_오류면_502다(client: TestClient, harness: Harness) -> None:
    fail_with(harness, LLMClientVendorError("overloaded"))
    start(client)

    assert client.post("/ask", json={"question": "환불 되나요?"}).status_code == 502


def test_설정_오류면_500이고_원인을_노출하지_않는다(client: TestClient, harness: Harness) -> None:
    fail_with(harness, LLMClientRequestError("api key sk-ant-verysecret is invalid"))
    start(client)

    response = client.post("/ask", json={"question": "환불 되나요?"})

    assert response.status_code == 500
    assert "sk-ant" not in response.text
