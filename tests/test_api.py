from types import SimpleNamespace

import anthropic
import pytest
from fastapi.testclient import TestClient

from blue_chatbot.main import app
from blue_chatbot.routes.dependencies import get_client, get_faq
from blue_chatbot.services.ask import Answer
from blue_chatbot.services.faq import FaqEntry

FAQS = [
    FaqEntry(id="refund", question="환불 되나요?", answer="7일 이내 가능합니다."),
]
FALLBACK = "질문에 알맞은 대답을 찾을 수 없습니다."


class FakeClient:
    def __init__(self, parsed=None, error=None, stop_reason="end_turn"):
        self.calls: list[dict] = []

        def parse(**kwargs):
            self.calls.append(kwargs)
            if error is not None:
                raise error
            return SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason)

        self.messages = SimpleNamespace(parse=parse)


@pytest.fixture
def client():
    app.dependency_overrides[get_faq] = lambda: FAQS
    yield TestClient(app)
    app.dependency_overrides.clear()


def use(fake):
    app.dependency_overrides[get_client] = lambda: fake


def test_health가_faq_수를_알려준다(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "faq_count": 1}


def test_정상_답변(client):
    use(FakeClient(Answer(content="7일 이내 가능합니다.", matched_id="refund")))

    response = client.post("/ask", json={"question": "환불 되나요?"})

    assert response.status_code == 200
    assert response.json() == {
        "content": "7일 이내 가능합니다.",
        "matched_id": "refund",
    }


def test_근거_없는_답변은_고정_문구로_내려간다(client):
    use(FakeClient(Answer(content="지어낸 답", matched_id="없는-id")))

    response = client.post("/ask", json={"question": "배송 문의"})

    assert response.status_code == 200
    assert response.json() == {"content": FALLBACK, "matched_id": None}


@pytest.mark.parametrize("payload", [{"question": ""}, {"question": "   "}, {}])
def test_질문이_비면_422다(client, payload):
    assert client.post("/ask", json=payload).status_code == 422


def test_질문_앞뒤_공백은_제거된다(client):
    fake = FakeClient(Answer(content="답", matched_id="refund"))
    use(fake)

    client.post("/ask", json={"question": "  환불 되나요?  "})

    assert fake.calls[0]["messages"] == [{"role": "user", "content": "환불 되나요?"}]


def test_rate_limit이면_429다(client):
    # SDK가 response.request까지 참조하므로 가짜에도 넣어준다.
    fake_response = type(
        "R",
        (),
        {"headers": {"retry-after": "30"}, "status_code": 429, "request": None},
    )()
    use(FakeClient(error=anthropic.RateLimitError("rate limited", response=fake_response, body=None)))

    response = client.post("/ask", json={"question": "환불 되나요?"})

    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"


def test_연결_오류면_503이다(client):
    use(FakeClient(error=anthropic.APIConnectionError(request=None)))

    assert client.post("/ask", json={"question": "환불 되나요?"}).status_code == 503


def test_인증_오류면_500이고_원인을_노출하지_않는다(client):
    fake_response = type("R", (), {"headers": {}, "status_code": 401, "request": None})()
    use(FakeClient(error=anthropic.AuthenticationError("bad key", response=fake_response, body=None)))

    response = client.post("/ask", json={"question": "환불 되나요?"})

    assert response.status_code == 500
    assert "key" not in response.text.lower()


def test_상류_5xx면_502다(client):
    fake_response = type("R", (), {"headers": {}, "status_code": 529, "request": None})()
    use(FakeClient(error=anthropic.APIStatusError("overloaded", response=fake_response, body=None)))

    assert client.post("/ask", json={"question": "환불 되나요?"}).status_code == 502
