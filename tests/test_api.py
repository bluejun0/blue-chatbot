import pytest
from fastapi.testclient import TestClient

from blue_chatbot.main import app
from blue_chatbot.routes.dependencies import get_faq, get_model
from blue_chatbot.services.ask import Answer
from blue_chatbot.services.faq import FaqEntry
from blue_chatbot.services.model import (
    ModelRequestError,
    ModelRateLimitError,
    ModelUnreachableError,
    ModelUpstreamError,
)

FAQS = [
    FaqEntry(id="refund", question="환불 되나요?", answer="7일 이내 가능합니다."),
]
FALLBACK = "질문에 알맞은 대답을 찾을 수 없습니다."


class FakeModel:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.calls: list[dict] = []

    def generate(self, *, system, messages, output_format):
        self.calls.append({"system": system, "messages": messages})
        if self._error is not None:
            raise self._error
        return self._result


@pytest.fixture
def client():
    app.dependency_overrides[get_faq] = lambda: FAQS
    yield TestClient(app)
    app.dependency_overrides.clear()


def use(fake):
    app.dependency_overrides[get_model] = lambda: fake


def test_health가_faq_수를_알려준다(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "faq_count": 1}


def test_정상_답변(client):
    use(FakeModel(Answer(content="7일 이내 가능합니다.", matched_id="refund")))

    response = client.post("/ask", json={"question": "환불 되나요?"})

    assert response.status_code == 200
    assert response.json() == {
        "content": "7일 이내 가능합니다.",
        "matched_id": "refund",
    }


def test_근거_없는_답변은_고정_문구로_내려간다(client):
    use(FakeModel(Answer(content="지어낸 답", matched_id="없는-id")))

    response = client.post("/ask", json={"question": "배송 문의"})

    assert response.status_code == 200
    assert response.json() == {"content": FALLBACK, "matched_id": None}


@pytest.mark.parametrize("payload", [{"question": ""}, {"question": "   "}, {}])
def test_질문이_비면_422다(client, payload):
    assert client.post("/ask", json=payload).status_code == 422


def test_질문_앞뒤_공백은_제거된다(client):
    fake = FakeModel(Answer(content="답", matched_id="refund"))
    use(fake)

    client.post("/ask", json={"question": "  환불 되나요?  "})

    assert [m.content for m in fake.calls[0]["messages"]] == ["환불 되나요?"]


def test_요청량_초과면_429다(client):
    use(FakeModel(error=ModelRateLimitError(retry_after=30)))

    response = client.post("/ask", json={"question": "환불 되나요?"})

    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"


def test_모델에_닿지_못하면_503이다(client):
    use(FakeModel(error=ModelUnreachableError("연결 실패")))

    assert client.post("/ask", json={"question": "환불 되나요?"}).status_code == 503


def test_제공자_오류면_502다(client):
    use(FakeModel(error=ModelUpstreamError("overloaded")))

    assert client.post("/ask", json={"question": "환불 되나요?"}).status_code == 502


def test_설정_오류면_500이고_원인을_노출하지_않는다(client):
    use(FakeModel(error=ModelRequestError("api key sk-ant-verysecret is invalid")))

    response = client.post("/ask", json={"question": "환불 되나요?"})

    assert response.status_code == 500
    assert "sk-ant" not in response.text
