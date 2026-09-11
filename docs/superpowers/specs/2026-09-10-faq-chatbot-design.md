# blue-chatbot 설계 — FAQ 질의응답 API

작성일: 2026-09-10 · 최종 갱신: 2026-09-11 (구현 완료 후 실제 코드에 맞춰 갱신)

## 1. 목적과 범위

사내 매뉴얼 FAQ를 근거로 질문에 답하는 HTTP API를 만든다. Claude API에 FAQ를
시스템 프롬프트로 주입하고, 응답을 구조화된 JSON으로 받아 **FAQ에 근거가 없는
질문에 답을 지어내지 않는 것**을 서버가 검증할 수 있게 한다.

**범위 안**: FastAPI HTTP API, FAQ 파일 로딩, 프롬프트 조립, Claude 호출, 응답 검증, 테스트.

**범위 밖 (지금 하지 않는다)**:
- 프론트엔드 / 웹 채팅 UI
- 대화 맥락 유지 (세션, 히스토리) — 매 요청 독립
- 임베딩 검색 / 벡터 저장소 (RAG)
- FAQ 후보 사전 필터링 — FAQ가 수백 개로 커지기 전엔 불필요
- 엔드포인트 인증 — 사내/로컬 사용을 전제로 하므로 두지 않는다. 외부 노출 시 재검토 필요
- 스트리밍 응답 — 답변이 짧고 UI가 없어 이득이 없다

## 2. 확정된 요구사항

| 항목 | 결정 |
|---|---|
| 답변 방식 | LLM + FAQ 프롬프트 주입 (검색/임베딩 없음) |
| 인터페이스 | HTTP API만 |
| 대화 맥락 | Stateless — 요청 1건 = 질문 1개, 답변 1개 |
| FAQ 데이터 | 저장소 내 YAML 파일 |
| 언어 | Python 3.12 + FastAPI |
| 응답 형식 | 구조화 출력 |

## 3. 핵심 설계 결정: 근거 없는 답변 방지

이 프로젝트에서 유일하게 어려운 부분이다. 나머지는 배관 작업이다.

FAQ를 프롬프트에 넣고 자유 텍스트로 답하게 두면, FAQ에 없는 질문에도 모델이
그럴듯하게 답한다. 프롬프트에 "모르면 모른다고 하라"고 써도 그건 희망사항일 뿐,
서버가 위반 여부를 알 수 없다.

**해결책**: 응답을 구조화하여 모델이 *근거로 삼은 FAQ 항목*을 함께 반환하게 한다.

```json
{"content": "...", "matched_id": "lunch-time" | null}
```

`matched_id`가 근거의 유무와 정체를 동시에 나타낸다. 별도의 `answered` 불리언을
두지 않는 이유는 `matched_id is not None`으로 파생되기 때문이다 — 두 필드가
어긋나는 상태를 애초에 만들지 않는다.

서버는 응답을 받은 뒤 다음을 검증한다 (`services/ask.py`).

1. `stop_reason == "refusal"` → 고정 안내 문구로 대체
2. `parsed_output is None` (스키마 검증 실패) → 경고 로그 + 고정 안내 문구
3. `matched_id`가 `None` → 근거를 밝히지 않았다. 고정 안내 문구
4. `matched_id`가 로딩된 FAQ에 없는 id → 모델이 지어냈다. 고정 안내 문구

**보장하는 것과 보장하지 않는 것**을 분명히 해둔다. 보장되는 것은 *근거를 밝히지
않은 답변은 클라이언트에 도달하지 않는다*는 것이다. 보장되지 않는 것은 답변 문장이
인용한 FAQ 항목에 충실한지다. 모델이 `matched_id`로 실재하는 항목을 가리키면서 그
항목에 없는 내용을 덧붙이면 위 규칙은 통과한다. 이는 "표현이 달라도 자연스럽게
답한다"는 이점을 얻는 대가다.

이 여지를 0으로 만들려면 `faq[matched_id].answer`를 그대로 반환하면 된다. 다만
그러면 LLM은 사실상 분류기가 되고, 자연스러운 답변이라는 채택 이유를 포기하게 된다.
**지금은 자유 표현을 택하고, 프롬프트 규칙으로 완화한다.**

## 4. 모듈 구조

```
src/blue_chatbot/
  main.py            앱 생성, lifespan(FAQ 1회 로딩), 라우터 등록
  routes/
    ask.py           POST /ask — 요청 검증, 예외 -> HTTP 상태 매핑
    health.py        GET /health
    dependencies.py  get_faq, get_client (테스트가 교체하는 지점)
  services/
    faq.py           FAQ YAML 로딩 + 검증
    prompt.py        FAQ -> 시스템 프롬프트 (순수 함수)
    ask.py           Claude 호출 + 근거 검증
  configs/
    core.py          CoreConfig (pydantic-settings)
data/faq.yaml
tests/
```

의존 방향은 `routes -> services -> configs`. 역방향 참조는 없다.

- `faq.load(path) -> list[FaqEntry]` — 순수. `FaqEntry`는 `frozen=True`라 로딩 후 불변이다.
- `prompt.build_prompt_system(faqs) -> str` — 순수. 같은 입력이면 같은 출력 (캐시 전제).
- `ask.answer(client, faqs, question) -> Answer` — Anthropic 클라이언트를 **인자로 받는다.**
- `ask._validate_answer(raw, faq) -> Answer` — 순수. 3장의 근거 검증 규칙.

FAQ는 기동 시 1회 로딩해 `app.state.faq`에 둔다. 요청마다 파일을 읽지 않는다.
대신 FAQ를 수정하면 재시작이 필요하다 — 이게 걸리면 리로드 엔드포인트나 mtime
체크를 붙인다.

## 5. 데이터 형식

`data/faq.yaml`:

```yaml
- id: lunch-time
  question: 점심 시간이 어떻게 되나요?
  answer: 11시 50분 부터 13시까지 입니다.
```

`id`는 필수이며 파일 내에서 고유해야 한다. 로딩 시점에 검증하고, 위반하면
기동을 실패시킨다 (런타임에 조용히 틀리는 것보다 낫다).

`id`는 사람이 읽을 수 있게 짓는다 (`lunch-time`, `annual-leave-request`).
모델이 의미를 보고 고르기 쉽고, 로그에서도 바로 읽힌다.

## 6. API 계약

**`POST /ask`**

```json
// 요청
{"question": "점심 몇 시부터예요?"}

// 응답 200
{"content": "11시 50분부터 13시까지입니다.", "matched_id": "lunch-time"}

// FAQ에 없는 질문
{"content": "질문에 알맞은 대답을 찾을 수 없습니다.", "matched_id": null}
```

`question`은 `Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]`
이다. 앞뒤 공백을 걷어낸 뒤 길이를 보므로 공백뿐인 질문은 422로 거부된다.

**`GET /health`** — `{"status": "ok", "faq_count": 6}`. FAQ 로딩 여부까지 확인된다.

## 7. Claude 호출 세부

- 모델: `claude-sonnet-5` (`CoreConfig.claude_model`)
- `max_tokens`: 16000
- `output_config.effort`: `"low"` — 짧고 단순한 작업이라 낮은 effort로 충분하다.
  `Literal`로 제한해 오타가 기동 시점에 걸린다.
- thinking: 명시하지 않는다. `{"type": "disabled"}`는 응답에 내부 태그가 새는 등
  알려진 문제가 있어 쓰지 않는다.
- 구조화 출력: `client.messages.parse(..., output_format=Answer)`.
  SDK가 `output_config`에 `format`을 병합하므로 `effort`와 함께 써도 안전하다.
- 클라이언트 생성: 인자 없는 `anthropic.Anthropic()`. 키를 코드에 넣지 않는다.

프롬프트에 명시할 규칙 (`services/prompt.py`의 `INSTRUCTIONS`):
- 근거가 있으면 그 항목의 id를 `matched_id`에 정확히 적을 것
- 근거가 없으면 `matched_id`를 비우고 답을 지어내지 말 것
- 인용한 항목의 내용만 재구성하고 원문에 없는 사실을 덧붙이지 말 것

서버측 refusal fallback(`fallbacks` 파라미터)은 **의도적으로 쓰지 않는다.** FAQ
응답에서 정책 거부가 발생할 경로가 사실상 없고, 발생하더라도 고정 안내 문구로
내려가면 충분하다.

**프롬프트 캐싱은 아직 켜지 않았다.** 캐시 최소 크기(모델별 512~4096 토큰) 미만이면
조용히 동작하지 않는데, 현재 FAQ 분량으로는 미달이다. 구조는 준비되어 있다 —
시스템 프롬프트가 순수 함수라 매 요청 동일하고, 타임스탬프 같은 변동값이 없다.
FAQ가 충분히 커지면 `cache_control`만 붙이면 된다.

## 8. 에러 처리

`routes/ask.py`가 상류 예외를 HTTP 상태로 매핑한다. 상태 코드는 `fastapi.status`
상수를 쓴다.

| 상황 | 처리 |
|---|---|
| `RateLimitError` | 429 + `retry-after` 헤더 전달 |
| `APIConnectionError` / `APITimeoutError` | 503 |
| `APIStatusError` 5xx | 502 |
| `AuthenticationError` | 500 + 서버 로그에만 원인 기록 (클라이언트에 노출 안 함) |
| `stop_reason == "refusal"` | 고정 안내 문구 (200) |
| 구조화 출력 파싱 실패 | 경고 로그 + 고정 안내 문구 (200) |
| 근거 검증 실패 | 고정 안내 문구 (200) |

브로드 `except`로 뭉뚱그리지 않는다. 재시도 가능한 오류(429/5xx/네트워크)와
불가능한 오류(400/인증)를 구분해야 클라이언트가 올바르게 대응할 수 있다.

## 9. 테스트 (39개, 네트워크 없이 실행)

| 파일 | 개수 | 대상 |
|---|---|---|
| `test_faq.py` | 7 | 로딩, id 중복·누락, 빈 파일, 잘못된 최상위 타입 |
| `test_prompt.py` | 5 | 항목 포함, 결정성, 순서 보존 |
| `test_ask.py` | 8 | **근거 검증 규칙**, refusal, 파싱 실패, 호출 파라미터 |
| `test_api.py` | 11 | 엔드포인트 계약, 422, 429/503/500/502, 인증 원인 비노출 |
| `test_core.py` | 8 | 기본값, 환경변수 덮어쓰기, `effort` 오타 거부 |

`services`는 가짜 클라이언트로, `routes`는 `TestClient` + `dependency_overrides`로
테스트한다. 실제 API를 호출하는 스모크 테스트 2개는 `smoke` 마커로 기본 실행에서
제외된다 (`uv run pytest -m smoke`).

**미검증 항목**: 프롬프트가 실제 모델에서 의도대로 작동하는지는 아직 확인되지
않았다. 39개가 검증하는 것은 "모델이 지어내도 서버가 걸러낸다"는 2차 방어선이다.
1차 방어선(모델이 애초에 지어내지 않는다)은 스모크 테스트를 돌려야 확인된다.
실패하면 `prompt.py`의 `INSTRUCTIONS`를 강화한다 — `ask.py`의 검증 규칙이 아니다.

## 10. 의존성과 실행

`uv` + Python 3.12. 시스템 기본 `python3`는 3.9(EOL)이므로 쓰지 않는다.

- `anthropic`, `fastapi`, `uvicorn`, `pyyaml`, `pydantic-settings`
- dev: `pytest`, `httpx` (TestClient용)

`anthropic` 1.x는 `httpx2`를 쓰고 TestClient는 `httpx`를 쓴다. 별개 패키지라
공존한다.

진입점은 `blue_chatbot.main:app`. Docker 이미지는 가상환경을 `/opt/venv`에 두어
compose의 소스 마운트에 가려지지 않게 한다.
