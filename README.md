# blue-chatbot

FAQ 목록을 근거로 질문에 답하는 HTTP API.

FAQ에 근거가 없는 질문에는 답을 지어내지 않는다. 모델이 밝힌 근거를
서버가 실제 FAQ와 대조해, 통과하지 못한 응답은 고정 안내 문구로 바꾼다.

설계와 구현 계획은 `docs/superpowers/` 아래에 있다.

## 로컬 실행

```bash
uv sync
uv run pytest
uv run uvicorn blue_chatbot.main:app --reload
```

## Docker

```bash
docker compose up          # 8003 포트, 소스 마운트 + 자동 리로드
docker compose run --rm app pytest
```

가상환경은 이미지 안 `/opt/venv`에 있다. `/app`에 두면 compose의 소스
마운트에 가려져 패키지를 못 찾기 때문이다.

## 구조

```
src/blue_chatbot/
  main.py       앱 생성, 라우터 등록
  routes/       HTTP 라우트 (ask, health, dependencies)
  services/     비즈니스 로직 (faq, prompt, ask)
  configs/      설정 (core)
```

의존성 방향은 `routes -> services -> configs`. 역방향 참조는 없다.

## 설정

`src/blue_chatbot/configs/core.py`에 모여 있다. 환경변수나 `.env`로
덮어쓸 수 있다 (이름은 대소문자 무관).

| 이름 | 기본값 | 설명 |
|---|---|---|
| `FAQ_PATH` | `data/faq.yaml` | FAQ 파일 경로 |
| `CLAUDE_MODEL` | `claude-sonnet-5` | 사용할 모델 |
| `MAX_TOKENS` | `16000` | 응답 토큰 상한 |
| `EFFORT` | `low` | 추론 깊이. 빈 값이면 파라미터를 보내지 않는다 |
| `ANTHROPIC_API_KEY` | 없음 | Claude API 키 |

`ANTHROPIC_API_KEY`는 넣으면 그 값으로 클라이언트를 만들고, 비워 두면
Anthropic SDK가 환경변수와 `ant auth login` 프로필을 직접 읽는다.
`SecretStr`이라 로그나 `model_dump()`에 원문이 찍히지 않는다.

## 테스트

`uv run pytest`는 네트워크를 쓰지 않는다. 실제 API를 호출하는 테스트는
`smoke` 마커로 분리되어 기본 실행에서 제외된다.

```bash
uv run pytest -m smoke     # 실제 API 호출. 비용이 발생한다
```

## 엔드포인트

`POST /ask`

```bash
curl -s localhost:8003/ask -H 'content-type: application/json' \
  -d '{"question": "환불 되나요?"}'
```

```json
{"content": "구매일로부터 7일 이내...", "matched_id": "refund-policy"}
```

FAQ에 근거가 없으면 `matched_id: null`과 고정 안내 문구가 내려간다.

`GET /health` — FAQ 로딩 상태와 항목 수를 반환한다.

## FAQ 편집

`data/faq.yaml`을 수정하고 서버를 재시작한다. `id`는 파일 안에서 고유해야 하며,
중복이나 누락이 있으면 기동에 실패한다.
