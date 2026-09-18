# FAQ 질의응답 API 구현 계획 — 실행 완료

**상태**: 2026-09-11 실행 완료. 이 문서는 기록이며, **현재 설계의 기준은
`../specs/2026-09-10-faq-chatbot-design.md`다.**

원래 이 파일은 태스크 5개의 단계별 TDD 지시서(테스트 코드와 구현 코드를 그대로
담은 약 1000줄)였다. 실행이 끝났고 구현 과정에서 설계가 여러 군데 바뀌어,
낡은 지시서를 남겨두는 대신 실행 기록으로 대체한다.

## 실행 순서

| 태스크 | 결과 |
|---|---|
| 1. FAQ 로딩 | `services/faq.py` — 로딩 시점 검증, `FaqError` |
| 2. 프롬프트 조립 | `services/prompt.py` — 순수 함수 |
| 3. Claude 호출 + 근거 검증 | `services/ask.py` — 이 프로젝트의 핵심 |
| 4. HTTP 엔드포인트 | `routes/` — `/ask`, `/health`, 예외 매핑 |
| 5. 스모크 테스트 + README | `smoke` 마커로 기본 실행에서 제외 |

각 태스크는 실패하는 테스트 → 최소 구현 → 통과 확인 순으로 진행했다.

## 계획에서 바뀐 것

구현하면서 내린 판단들이다. 이유가 남을 가치가 있는 것만 적는다.

**응답 스키마에서 `answered`를 뺐다.** 계획은 `{answer, answered, matched_id}`
였는데, `answered`는 `matched_id is not None`으로 파생된다. 두 필드를 두면 서로
어긋나는 상태가 생길 수 있어 `{content, matched_id}`로 줄였다. 검증 규칙도
그만큼 단순해졌다.

**엔드포인트를 `/chat`에서 `/ask`로 바꿨다.** `/chat`은 여러 턴의 대화를
함의하는데 이 API는 stateless 단발성이다. 이름이 동작보다 많은 것을 약속하고
있었다. 나중에 진짜 멀티턴이 필요해지면 그때 `/chat`을 따로 만들면 된다.

**구조를 `routes / services / configs` 3계층으로 나눴다.** 계획은 평평한
모듈 4개였다. 파일이 늘면서 경계를 명시하는 편이 나아졌다.

**설정을 `configs/core.py`로 모았다.** 계획은 `os.environ.get`을 쓰는
방식이었다. `pydantic-settings`로 바꾸면서 `effort`를 `Literal`로 제한했고,
덕분에 오타가 첫 API 호출이 아니라 기동 시점에 걸린다.

**고정 안내 문구는 설정이 아니라 코드 상수로 뒀다.** 사용자에게 보이는 문구라
환경변수로 조용히 바뀌는 것보다 코드 리뷰를 거치는 편이 맞다고 판단했다.

**모델을 `claude-sonnet-5`로 낮췄다.** 비용 판단이며 `CLAUDE_MODEL`로 언제든
바꿀 수 있다.

**계획이 예상했던 두 함정 중 하나만 실제로 터졌다.**
`anthropic.RateLimitError`가 `response.request`까지 참조해 가짜 응답 객체를
보강해야 했다 — 계획대로 구현이 아니라 테스트를 고쳤다. 반대로
`output_config`와 `output_format`은 SDK가 알아서 병합해줘서(`messages.py:1090`)
계획에 준비해둔 대체 구현은 쓸 일이 없었다.

## 남은 일

- **프롬프트 실검증**: 스모크 테스트를 돌려야 1차 방어선이 확인된다.
  `ANTHROPIC_API_KEY` 또는 `ant auth login` 필요.
- **프롬프트 캐싱**: FAQ가 캐시 최소 크기를 넘으면 `cache_control` 추가.
- **FAQ 갱신 방식**: 현재는 재시작이 필요하다.
