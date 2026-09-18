# 유지보수 요청 검색 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 챗봇이 유지보수 요청을 벡터 검색 도구로 찾아 근거로 답하고, 임베딩 모델을 설정값으로 바꿔 끼우며, 모델을 같은 잣대로 비교할 수 있게 한다.

**Architecture:** 색인 작업이 원본 DB의 `requests`를 읽어 임베딩해 MariaDB 벡터 테이블(모델별로 하나)에 쌓는다. 질의 시 모델에게 `search_requests` 도구를 주고, 모델이 채운 파라미터로 우리 코드가 SQL을 만들어 top-k를 돌려준다. 근거 검증은 `(source, id)` 쌍으로 하며, 도구가 실제로 돌려준 것만 인용할 수 있다.

**Tech Stack:** Python 3.12, FastAPI, SQLModel/SQLAlchemy 2, Alembic, MariaDB 12.3 `VECTOR`, anthropic SDK 1.4 (`messages.parse` + `tools`), openai SDK (임베딩만), pytest, mypy strict

**Spec:** `docs/superpowers/specs/2026-09-18-requests-rag-design.md`

## Global Constraints

- 문서와 주석은 `docs/CONTRIBUTING.md`의 용어 규칙을 따른다. 조어를 쓰지 않는다
- 커밋 메시지는 `{type}: {한글 요약}`, 마침표 없음, 하나의 커밋에 하나의 논리적 변경
- AI 단독 작업 커밋에는 끝에 다음 두 줄을 붙인다:
  `🤖 Generated with [Claude Code](https://claude.com/claude-code)` / `Co-Authored-By: Claude <noreply@anthropic.com>`
- 코드 스타일: 공백은 한 칸. 세로 정렬용 연속 공백을 넣지 않는다
- `mypy --strict`를 통과해야 한다 (`uv run mypy`)
- 기본 `uv run pytest`는 네트워크를 쓰지 않는다. 실제 API를 호출하는 테스트는 `smoke` 마커
- 라이브러리와 DB 함수의 동작은 테스트하지 않는다. 우리가 만든 SQL·조건·변환만 테스트한다
- 모델은 정해진 파라미터의 값만 채운다. 모델이 쓴 문자열이 SQL 문장에 들어가지 않는다
- 계정, 비밀번호, 접속정보가 담긴 컬럼은 읽지도 저장하지도 않는다
- FAQ 응답은 이 작업으로 동작이 바뀌지 않아야 한다. 임베딩 키가 없으면 도구 없이 지금처럼 동작한다

---

## 준비: 이슈와 브랜치

CONTRIBUTING에 따라 이슈를 먼저 만들고 최신 main에서 브랜치를 딴다. 이슈 번호는 만들어진 뒤에 알 수 있으므로 아래 `{N}`을 그 번호로 바꾼다.

```bash
gh issue create --title "feat: 유지보수 요청 벡터 검색 도구" --body "$(cat <<'EOF'
## 목표

챗봇이 유지보수 요청을 벡터 검색으로 찾아 근거로 답한다. 임베딩 모델은 설정값으로 바꿀 수 있고, 여러 모델을 같은 질문 세트로 비교할 수 있다.

## 작업범위

- 원본 `requests`를 읽어 임베딩해 MariaDB 벡터 테이블에 쌓는 색인 작업
- 모델이 파라미터를 채우는 `search_requests` 도구와 도구 루프
- 근거 검증을 `(source, id)` 쌍으로 확장
- 임베딩 인터페이스와 OpenAI 구현, 모델별 벡터 테이블
- 모델 비교 스크립트와 질문 세트 형식

## 완료조건

- [ ] 색인 명령이 바뀐 요청만 다시 임베딩한다
- [ ] 임베딩 키가 없으면 FAQ만으로 지금처럼 동작한다
- [ ] 모델이 검색 결과에 없는 근거를 인용하면 안내 문구로 바뀐다
- [ ] `EMBEDDING_MODEL`만 바꿔 다른 임베딩 모델의 테이블을 본다
- [ ] 비교 스크립트가 모델별 재현율을 출력한다

설계: `docs/superpowers/specs/2026-09-18-requests-rag-design.md`
EOF
)"
git fetch origin main
git checkout -b issue/{N}-requests-search origin/main
```

---

## 파일 구조

```
src/blue_chatbot/
  configs/core.py                    수정  openai_api_key, embedding_model, search_top_k, source_database_url
  services/embedding.py              신규  Embedder 프로토콜, EmbeddingError, table_suffix()
  llm/openai_embedding.py            신규  OpenAIEmbedder. openai 패키지는 이 파일에서만 import
  llm/embedders.py                   신규  이름 → Embedder 구현 등록표, build_embedder()
  repositories/index_state.py        신규  index_state 테이블 모델과 저장소
  repositories/request_reader.py     신규  원본 DB의 requests를 읽는다
  repositories/request_vectors.py    신규  모델별 벡터 테이블 DDL·upsert·검색 SQL
  services/indexing.py               신규  index_requests(): 읽기 → 임베딩 → 저장 → 색인 위치 갱신
  services/search.py                 신규  Evidence, EvidenceLog, SearchSource, RequestSource, to_tool()
  services/llm.py                    수정  ToolSpec, generate(tools=...)
  llm/anthropic_llm.py               수정  도구 루프
  services/ask.py                    수정  matched_source, 근거 검증 확장
  services/prompt.py                 수정  도구 사용 안내
  services/conversation.py           수정  sources 주입
  routes/dependencies.py             수정  get_embedder(), get_sources()
  routes/ask.py                      수정  AskResponse.matched_source
  services/compare.py                신규  질문 세트 로딩, 재현율 계산
  cli.py                             신규  index / compare 명령
alembic/env.py                       수정  index_state 모델 등록
alembic/versions/c2f1a7d9e4b3_색인_위치.py  신규
data/eval/requests.yaml              신규  비교 질문 세트 (형식과 예시 1건)
docs/domain/requests-search.md       신규  검색 자료·근거·색인 위치 개념
docs/decision/iworks.md              수정  구현된 결정 제거
tests/services/test_embedding.py     신규
tests/llm/test_openai_embedding.py   신규
tests/repositories/test_index_state.py       신규
tests/repositories/test_request_reader.py    신규
tests/repositories/test_request_vectors.py   신규 (SQL 생성)
tests/repositories/test_request_vectors_mariadb.py  신규 (MariaDB 있을 때만)
tests/services/test_indexing.py      신규
tests/services/test_search.py        신규
tests/services/test_compare.py       신규
tests/fakes.py                       수정  FakeLLMClient.generate(tools=...), FakeEmbedder
tests/llm/test_anthropic_llm_client.py  수정  도구 루프
tests/services/test_ask.py           수정
tests/services/test_prompt.py        수정
tests/services/test_conversation.py  수정
tests/routes/test_api.py             수정
tests/configs/test_core.py           수정
tests/test_smoke.py                  수정  도구 왕복 1건
```

---

### Task 1: 설정과 의존성

**Files:**
- Modify: `src/blue_chatbot/configs/core.py`
- Modify: `pyproject.toml`
- Modify: `compose.yaml`
- Modify: `README.md`
- Test: `tests/configs/test_core.py`

**Interfaces:**
- Produces: `config.openai_api_key: SecretStr | None`, `config.embedding_model: str` (기본 `"openai-3-small"`), `config.search_top_k: int` (기본 `5`), `config.source_database_url: SecretStr | None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/configs/test_core.py` 끝에 추가:

```python
def test_임베딩_설정_기본값() -> None:
    config = CoreConfig(
        _env_file=None,
        database_url="mysql+pymysql://t:t@localhost:3306/t",
    )

    assert config.openai_api_key is None
    assert config.embedding_model == "openai-3-small"
    assert config.search_top_k == 5
    assert config.source_database_url is None


def test_임베딩_키와_원본_DB는_비밀값이다() -> None:
    config = CoreConfig(
        _env_file=None,
        database_url="mysql+pymysql://t:t@localhost:3306/t",
        openai_api_key="sk-test",
        source_database_url="mysql+pymysql://r:r@src:3306/slack_db",
    )

    assert "sk-test" not in repr(config)
    assert "slack_db" not in repr(config)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/configs/test_core.py -v`
Expected: FAIL — `openai_api_key` 속성 없음

- [ ] **Step 3: 설정 추가**

`src/blue_chatbot/configs/core.py`의 `# FAQ` 블록 뒤에 추가:

```python
    # 검색
    openai_api_key: SecretStr | None = None
    embedding_model: str = "openai-3-small"
    search_top_k: int = 5
    # 색인이 읽는 원본 데이터베이스. 비우면 색인 명령을 쓸 수 없다
    source_database_url: SecretStr | None = None
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/configs/test_core.py -v`
Expected: PASS

- [ ] **Step 5: openai 의존성 추가**

```bash
uv add openai
```

`pyproject.toml`의 `dependencies`에 `openai` 항목이 생기고 `uv.lock`이 갱신된다.

- [ ] **Step 6: compose와 README**

`compose.yaml`의 `app.environment`에 추가:

```yaml
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      EMBEDDING_MODEL: ${EMBEDDING_MODEL:-openai-3-small}
      SOURCE_DATABASE_URL: ${SOURCE_DATABASE_URL:-}
```

`README.md` 설정 표의 `DATABASE_URL` 행 아래에 추가:

```markdown
| `OPENAI_API_KEY` | 없음 | 임베딩 호출 키. 비우면 검색 도구 없이 FAQ만으로 답한다 |
| `EMBEDDING_MODEL` | `openai-3-small` | 임베딩 구현 이름. 검색이 볼 벡터 테이블도 이 값으로 정해진다 |
| `SEARCH_TOP_K` | `5` | 검색 도구가 돌려주는 최대 건수 |
| `SOURCE_DATABASE_URL` | 없음 | 색인이 읽는 원본 DB. 읽기 전용 계정을 쓴다 |
```

- [ ] **Step 7: 전체 검사와 커밋**

Run: `uv run pytest -q && uv run mypy`
Expected: 모두 통과

```bash
git add src/blue_chatbot/configs/core.py tests/configs/test_core.py pyproject.toml uv.lock compose.yaml README.md
git commit -F - <<'EOF'
feat: 임베딩과 원본 DB 설정을 추가한다

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 2: 임베딩 인터페이스와 OpenAI 구현

**Files:**
- Create: `src/blue_chatbot/services/embedding.py`
- Create: `src/blue_chatbot/llm/openai_embedding.py`
- Create: `src/blue_chatbot/llm/embedders.py`
- Test: `tests/services/test_embedding.py`, `tests/llm/test_openai_embedding.py`
- Modify: `tests/fakes.py` (FakeEmbedder 추가)

**Interfaces:**
- Produces:
  - `Embedder` 프로토콜: `name: str`, `dimension: int`, `embed(texts: list[str]) -> list[list[float]]`
  - `EmbeddingError(Exception)`
  - `table_suffix(name: str) -> str` — `"openai-3-small"` → `"openai_3_small"`
  - `OpenAIEmbedder(client, name, model, dimension)`
  - `build_embedder(name: str) -> Embedder` — 모르는 이름이면 `EmbeddingError`
  - `EMBEDDING_MODELS: dict[str, tuple[str, int]]`
  - 테스트용 `FakeEmbedder(dimension=4)` — 텍스트 길이로 결정적 벡터를 만들고 호출을 기록

- [ ] **Step 1: 실패하는 테스트 작성 — 인터페이스**

`tests/services/test_embedding.py`:

```python
"""임베딩 이름을 테이블 접미사로 바꾸는 규칙을 확인한다."""

import pytest

from blue_chatbot.services.embedding import table_suffix


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("openai-3-small", "openai_3_small"),
        ("BGE-M3", "bge_m3"),
        ("qwen3.0.6b", "qwen3_0_6b"),
        ("--dash--", "dash"),
    ],
)
def test_이름을_소문자_영숫자와_밑줄로_바꾼다(name: str, expected: str) -> None:
    assert table_suffix(name) == expected


def test_비면_실패한다() -> None:
    with pytest.raises(ValueError):
        table_suffix("---")
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/services/test_embedding.py -v`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: 인터페이스 구현**

`src/blue_chatbot/services/embedding.py`:

```python
"""임베딩 인터페이스. 색인과 검색은 어느 모델을 쓰는지 모른다."""

import re
from typing import Protocol


class EmbeddingError(Exception):
    """임베딩을 만들 수 없을 때 발생한다."""


class Embedder(Protocol):
    name: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def table_suffix(name: str) -> str:
    """임베딩 이름을 테이블 이름에 넣을 수 있는 형태로 바꾼다."""
    suffix = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not suffix:
        raise ValueError(f"테이블 이름으로 쓸 수 없는 임베딩 이름입니다: {name!r}")
    return suffix
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/services/test_embedding.py -v`
Expected: PASS

- [ ] **Step 5: 실패하는 테스트 작성 — OpenAI 구현과 등록표**

`tests/llm/test_openai_embedding.py`:

```python
"""OpenAI 응답을 입력 순서대로 정렬하고 SDK 예외를 번역하는지 확인한다."""

from types import SimpleNamespace
from typing import Any

import openai
import pytest

from blue_chatbot.llm.embedders import build_embedder
from blue_chatbot.llm.openai_embedding import OpenAIEmbedder
from blue_chatbot.services.embedding import EmbeddingError


def fake_sdk(items: list[tuple[int, list[float]]] | None = None, error: Exception | None = None) -> Any:
    calls: list[dict[str, Any]] = []

    def create(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        if error is not None:
            raise error
        data = [SimpleNamespace(index=i, embedding=v) for i, v in (items or [])]
        return SimpleNamespace(data=data)

    return SimpleNamespace(embeddings=SimpleNamespace(create=create), calls=calls)


def embedder(sdk: Any) -> OpenAIEmbedder:
    return OpenAIEmbedder(sdk, name="openai-3-small", model="text-embedding-3-small", dimension=3)


def test_응답을_입력_순서대로_정렬한다() -> None:
    sdk = fake_sdk([(1, [0.2, 0.2, 0.2]), (0, [0.1, 0.1, 0.1])])

    result = embedder(sdk).embed(["첫째", "둘째"])

    assert result == [[0.1, 0.1, 0.1], [0.2, 0.2, 0.2]]


def test_모델_이름을_요청에_넣는다() -> None:
    sdk = fake_sdk([(0, [0.0, 0.0, 0.0])])

    embedder(sdk).embed(["문장"])

    assert sdk.calls[0]["model"] == "text-embedding-3-small"
    assert sdk.calls[0]["input"] == ["문장"]


def test_SDK_예외를_번역한다() -> None:
    sdk = fake_sdk(error=openai.OpenAIError("실패"))

    with pytest.raises(EmbeddingError):
        embedder(sdk).embed(["문장"])


def test_이름과_차원을_노출한다() -> None:
    e = embedder(fake_sdk())

    assert (e.name, e.dimension) == ("openai-3-small", 3)


def test_모르는_이름이면_실패한다() -> None:
    with pytest.raises(EmbeddingError, match="알 수 없는"):
        build_embedder("없는-모델")


def test_등록된_이름은_그_이름과_차원을_가진다() -> None:
    e = build_embedder("openai-3-small")

    assert (e.name, e.dimension) == ("openai-3-small", 1536)
```

- [ ] **Step 6: 실패 확인**

Run: `uv run pytest tests/llm/test_openai_embedding.py -v`
Expected: FAIL — 모듈 없음

- [ ] **Step 7: OpenAI 구현**

`src/blue_chatbot/llm/openai_embedding.py`:

```python
"""Embedder의 OpenAI 구현. openai 패키지는 이 파일에서만 import한다."""

import openai

from blue_chatbot.services.embedding import EmbeddingError


class OpenAIEmbedder:
    def __init__(self, client: openai.OpenAI, *, name: str, model: str, dimension: int) -> None:
        self._client = client
        self._model = model
        self.name = name
        self.dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        """입력 순서와 같은 순서로 벡터를 돌려준다."""
        try:
            response = self._client.embeddings.create(model=self._model, input=texts)
        except openai.OpenAIError as exc:
            raise EmbeddingError(str(exc)) from exc
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
```

`src/blue_chatbot/llm/embedders.py`:

```python
"""임베딩 이름을 구현으로 잇는 등록표. 새 모델은 여기에 한 줄 추가한다."""

import openai

from blue_chatbot.configs.core import config
from blue_chatbot.llm.openai_embedding import OpenAIEmbedder
from blue_chatbot.services.embedding import Embedder, EmbeddingError

# 이름 → (OpenAI 모델, 차원). 이름은 그대로 벡터 테이블 접미사와 색인 위치의 키가 된다
EMBEDDING_MODELS: dict[str, tuple[str, int]] = {
    "openai-3-small": ("text-embedding-3-small", 1536),
    "openai-3-large": ("text-embedding-3-large", 3072),
}


def build_embedder(name: str) -> Embedder:
    if name not in EMBEDDING_MODELS:
        raise EmbeddingError(f"알 수 없는 임베딩 모델: {name}")
    model, dimension = EMBEDDING_MODELS[name]
    key = config.openai_api_key
    client = openai.OpenAI(api_key=key.get_secret_value() if key else None)
    return OpenAIEmbedder(client, name=name, model=model, dimension=dimension)
```

- [ ] **Step 8: 테스트용 가짜 임베더**

`tests/fakes.py` 끝에 추가:

```python
class FakeEmbedder:
    """텍스트 길이로 결정적 벡터를 만든다. 호출한 텍스트를 기록한다."""

    def __init__(self, name: str = "fake", dimension: int = 4, error: Exception | None = None) -> None:
        self.name = name
        self.dimension = dimension
        self._error = error
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self._error is not None:
            raise self._error
        return [[float(len(t))] * self.dimension for t in texts]
```

- [ ] **Step 9: 통과 확인**

Run: `uv run pytest tests/llm/test_openai_embedding.py tests/services/test_embedding.py -v`
Expected: PASS

주의: `build_embedder` 테스트는 `openai.OpenAI(api_key=None)`를 만든다. 최신 openai SDK는 키가 없어도 클라이언트 생성은 허용하고 호출 시점에 실패한다. 생성 시점에 실패하면 테스트에서 `monkeypatch.setattr(config, "openai_api_key", SecretStr("sk-test"))`를 먼저 한다.

- [ ] **Step 10: 전체 검사와 커밋**

Run: `uv run pytest -q && uv run mypy`

```bash
git add src/blue_chatbot/services/embedding.py src/blue_chatbot/llm/openai_embedding.py src/blue_chatbot/llm/embedders.py tests/services/test_embedding.py tests/llm/test_openai_embedding.py tests/fakes.py
git commit -F - <<'EOF'
feat: 임베딩 인터페이스와 OpenAI 구현

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 3: 색인 위치 테이블

**Files:**
- Create: `src/blue_chatbot/repositories/index_state.py`
- Create: `alembic/versions/c2f1a7d9e4b3_색인_위치.py`
- Modify: `alembic/env.py`
- Test: `tests/repositories/test_index_state.py`

**Interfaces:**
- Produces: `IndexState(SQLModel, table=True)` — `source: str`, `model: str`, `cursor: int`, `indexed_at: datetime | None`; `IndexStateRepository(engine).get(source, model) -> int` (없으면 0), `.set(source, model, cursor, indexed_at) -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/repositories/test_index_state.py`:

```python
"""자료·모델 쌍마다 색인 위치를 따로 보관하는지 확인한다."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlmodel import SQLModel

from blue_chatbot.repositories.index_state import IndexStateRepository
from blue_chatbot.support import utc_now


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def states(engine: Engine) -> IndexStateRepository:
    return IndexStateRepository(engine)


def test_없는_쌍은_0이다(states: IndexStateRepository) -> None:
    assert states.get("requests", "openai-3-small") == 0


def test_저장한_위치를_돌려준다(states: IndexStateRepository) -> None:
    states.set("requests", "openai-3-small", 1700000000, utc_now())

    assert states.get("requests", "openai-3-small") == 1700000000


def test_다시_저장하면_덮어쓴다(states: IndexStateRepository) -> None:
    states.set("requests", "openai-3-small", 1, utc_now())
    states.set("requests", "openai-3-small", 2, utc_now())

    assert states.get("requests", "openai-3-small") == 2


def test_모델이_다르면_따로_보관한다(states: IndexStateRepository) -> None:
    states.set("requests", "openai-3-small", 10, utc_now())
    states.set("requests", "bge-m3", 20, utc_now())

    assert states.get("requests", "openai-3-small") == 10
    assert states.get("requests", "bge-m3") == 20


def test_자료가_다르면_따로_보관한다(states: IndexStateRepository) -> None:
    states.set("requests", "openai-3-small", 10, utc_now())

    assert states.get("dti", "openai-3-small") == 0
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/repositories/test_index_state.py -v`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: 모델과 저장소 구현**

`src/blue_chatbot/repositories/index_state.py`:

```python
from datetime import datetime

from sqlalchemy import Engine
from sqlmodel import Field, Session, SQLModel


class IndexState(SQLModel, table=True):
    """자료·모델 쌍이 마지막으로 처리한 원본 변경 시각."""

    __tablename__ = "index_state"

    source: str = Field(primary_key=True, max_length=40)
    model: str = Field(primary_key=True, max_length=40)
    cursor: int = Field(default=0, sa_column_kwargs={"comment": "마지막으로 처리한 원본 변경 시각(unixtime)"})
    indexed_at: datetime | None = None


class IndexStateRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get(self, source: str, model: str) -> int:
        """없으면 0. 처음부터 읽는다는 뜻이다."""
        with Session(self._engine) as session:
            state = session.get(IndexState, (source, model))
            return state.cursor if state else 0

    def set(self, source: str, model: str, cursor: int, indexed_at: datetime) -> None:
        with Session(self._engine) as session:
            session.merge(IndexState(source=source, model=model, cursor=cursor, indexed_at=indexed_at))
            session.commit()
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/repositories/test_index_state.py -v`
Expected: PASS

- [ ] **Step 5: 마이그레이션**

`alembic/env.py`의 모델 import 줄 아래에 추가:

```python
from blue_chatbot.repositories import index_state as _index_state  # noqa: F401
```

`alembic/versions/c2f1a7d9e4b3_색인_위치.py`:

```python
"""색인 위치

Revision ID: c2f1a7d9e4b3
Revises: ab1f3fc8139a
Create Date: 2026-09-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'c2f1a7d9e4b3'
down_revision: Union[str, Sequence[str], None] = 'ab1f3fc8139a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('index_state',
    sa.Column('source', sqlmodel.sql.sqltypes.AutoString(length=40), nullable=False),
    sa.Column('model', sqlmodel.sql.sqltypes.AutoString(length=40), nullable=False),
    sa.Column('cursor', sa.Integer(), nullable=False, comment='마지막으로 처리한 원본 변경 시각(unixtime)'),
    sa.Column('indexed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('source', 'model')
    )


def downgrade() -> None:
    op.drop_table('index_state')
```

- [ ] **Step 6: 마이그레이션 확인**

compose의 MariaDB가 떠 있을 때:

Run: `DATABASE_URL=mysql+pymysql://admin:1234@127.0.0.1:3308/blue_chatbot uv run alembic upgrade head`
Expected: `Running upgrade ab1f3fc8139a -> c2f1a7d9e4b3`

- [ ] **Step 7: 전체 검사와 커밋**

Run: `uv run pytest -q && uv run mypy`

```bash
git add src/blue_chatbot/repositories/index_state.py alembic/env.py alembic/versions/c2f1a7d9e4b3_색인_위치.py tests/repositories/test_index_state.py
git commit -F - <<'EOF'
feat: 자료·모델별 색인 위치 테이블

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 4: 원본 요청 읽기

**Files:**
- Create: `src/blue_chatbot/repositories/request_reader.py`
- Test: `tests/repositories/test_request_reader.py`

**Interfaces:**
- Produces: `SourceRequest` (frozen dataclass: `id: str`, `title: str`, `body: str | None`, `status: str`, `team: str`, `board: str`, `archived: bool`, `date: date | None`, `updated: int`), `RequestReader(engine).changed_since(cursor: int) -> list[SourceRequest]` — `updated > cursor`, `updated, id` 순

읽는 컬럼은 `id, title, body, status, team, board, archived, date, updated`만이다. 그 외 컬럼은 읽지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/repositories/test_request_reader.py`:

```python
"""마지막 색인 이후 바뀐 요청만 순서대로 읽는지 확인한다."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text

from blue_chatbot.repositories.request_reader import RequestReader

SCHEMA = """
CREATE TABLE requests (
  id VARCHAR(32) PRIMARY KEY,
  title VARCHAR(500) NOT NULL DEFAULT '',
  body TEXT,
  status VARCHAR(60) NOT NULL DEFAULT '',
  team VARCHAR(60) NOT NULL DEFAULT '',
  board VARCHAR(40) NOT NULL DEFAULT '',
  archived INTEGER NOT NULL DEFAULT 0,
  date DATE,
  updated INTEGER NOT NULL DEFAULT 0
)
"""


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(SCHEMA))
        conn.execute(
            text(
                "INSERT INTO requests (id, title, body, status, team, board, archived, date, updated) VALUES "
                "('R1', '첫째', '본문1', '완료', '블루소프트', '블루소프트', 1, '2026-01-01', 100), "
                "('R2', '둘째', NULL, '보류', '시스템개발', '블루소프트', 0, NULL, 200), "
                "('R3', '셋째', '본문3', '진행중', '', '와이오즈', 0, '2026-02-01', 200)"
            )
        )
    yield engine
    engine.dispose()


def test_커서_이후만_읽는다(engine: Engine) -> None:
    rows = RequestReader(engine).changed_since(100)

    assert [r.id for r in rows] == ["R2", "R3"]


def test_커서가_0이면_전부_읽는다(engine: Engine) -> None:
    assert len(RequestReader(engine).changed_since(0)) == 3


def test_변경_시각_같으면_id_순이다(engine: Engine) -> None:
    rows = RequestReader(engine).changed_since(150)

    assert [r.id for r in rows] == ["R2", "R3"]


def test_컬럼을_모델에_맞게_옮긴다(engine: Engine) -> None:
    first = RequestReader(engine).changed_since(0)[0]

    assert first.id == "R1"
    assert first.title == "첫째"
    assert first.body == "본문1"
    assert first.status == "완료"
    assert first.archived is True
    assert str(first.date) == "2026-01-01"
    assert first.updated == 100


def test_없으면_빈_목록이다(engine: Engine) -> None:
    assert RequestReader(engine).changed_since(999) == []
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/repositories/test_request_reader.py -v`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: 구현**

`src/blue_chatbot/repositories/request_reader.py`:

```python
"""원본 데이터베이스의 유지보수 요청을 읽는다. 읽기만 하며 아래 컬럼만 본다."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Engine, text


@dataclass(frozen=True)
class SourceRequest:
    id: str
    title: str
    body: str | None
    status: str
    team: str
    board: str
    archived: bool
    date: date | None
    updated: int


_SELECT = text(
    "SELECT id, title, body, status, team, board, archived, date, updated "
    "FROM requests WHERE updated > :cursor ORDER BY updated, id"
)


class RequestReader:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def changed_since(self, cursor: int) -> list[SourceRequest]:
        """마지막 색인 시각 이후 바뀐 요청. 변경 시각, id 순이다."""
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT, {"cursor": cursor}).mappings().all()
        return [
            SourceRequest(
                id=row["id"],
                title=row["title"],
                body=row["body"],
                status=row["status"],
                team=row["team"],
                board=row["board"],
                archived=bool(row["archived"]),
                date=_as_date(row["date"]),
                updated=int(row["updated"]),
            )
            for row in rows
        ]


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/repositories/test_request_reader.py -v`
Expected: PASS

- [ ] **Step 5: 전체 검사와 커밋**

Run: `uv run pytest -q && uv run mypy`

```bash
git add src/blue_chatbot/repositories/request_reader.py tests/repositories/test_request_reader.py
git commit -F - <<'EOF'
feat: 원본 DB에서 바뀐 유지보수 요청을 읽는다

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 5: 모델별 벡터 테이블 저장소

**Files:**
- Create: `src/blue_chatbot/repositories/request_vectors.py`
- Test: `tests/repositories/test_request_vectors.py` (SQL 생성, DB 없음)
- Test: `tests/repositories/test_request_vectors_mariadb.py` (MariaDB 있을 때만)

**Interfaces:**
- Consumes: `table_suffix()` (Task 2), `SourceRequest` (Task 4)
- Produces:
  - `RequestVector` (frozen dataclass): `request_id, title, body, status, team, board, archived, req_date, source_updated, embedded_at, embedding: list[float]`
  - `RequestHit` (frozen dataclass): `request_id, title, body, status, team, req_date, distance: float`
  - `SearchFilters` (frozen dataclass): `status: str | None = None`, `team: str | None = None`, `include_archived: bool = False`
  - `table_name(model_name: str) -> str` — `"request_vectors__" + table_suffix(model_name)`
  - `create_table_sql(table: str, dimension: int) -> str`
  - `search_sql(table: str, filters: SearchFilters) -> str` — 채워진 조건만 `WHERE`에 붙는다
  - `RequestVectorRepository(engine, model_name)`: `.table: str`, `.ensure_table(dimension)`, `.upsert(rows: list[RequestVector])`, `.search(embedding: list[float], filters: SearchFilters, limit: int) -> list[RequestHit]`

- [ ] **Step 1: 실패하는 테스트 작성 — SQL 생성**

`tests/repositories/test_request_vectors.py`:

```python
"""모델별 테이블 이름과 조건절 조합을 확인한다. DB는 쓰지 않는다."""

from blue_chatbot.repositories.request_vectors import (
    SearchFilters,
    create_table_sql,
    search_sql,
    table_name,
)


def test_테이블_이름은_모델_이름에서_온다() -> None:
    assert table_name("openai-3-small") == "request_vectors__openai_3_small"


def test_생성문에_차원과_벡터_인덱스가_들어간다() -> None:
    sql = create_table_sql("request_vectors__x", 1536)

    assert "CREATE TABLE IF NOT EXISTS request_vectors__x" in sql
    assert "VECTOR(1536)" in sql
    assert "VECTOR INDEX" in sql


def test_기본_조건은_보관_제외만이다() -> None:
    sql = search_sql("t", SearchFilters())

    assert "WHERE archived = 0" in sql
    assert "status" not in sql.split("WHERE")[1]
    assert "team" not in sql.split("WHERE")[1]


def test_보관_포함이면_보관_조건이_빠진다() -> None:
    sql = search_sql("t", SearchFilters(include_archived=True))

    assert "archived" not in sql.split("FROM")[1]


def test_상태와_팀은_채운_것만_붙는다() -> None:
    sql = search_sql("t", SearchFilters(status="보류"))

    assert "status = :status" in sql
    assert "team" not in sql.split("WHERE")[1]


def test_조건은_전부_바인딩_파라미터다() -> None:
    sql = search_sql("t", SearchFilters(status="보류", team="블루소프트"))

    assert "보류" not in sql
    assert "블루소프트" not in sql
    assert ":status" in sql and ":team" in sql


def test_거리순_정렬과_제한이_있다() -> None:
    sql = search_sql("t", SearchFilters())

    assert "VEC_DISTANCE_COSINE(embedding, VEC_FromText(:query))" in sql
    assert "ORDER BY distance" in sql
    assert "LIMIT :limit" in sql
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/repositories/test_request_vectors.py -v`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: 구현**

`src/blue_chatbot/repositories/request_vectors.py`:

```python
"""모델별 유지보수 요청 벡터 테이블. 테이블 이름은 임베딩 이름에서 온다."""

import json
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import Engine, text

from blue_chatbot.services.embedding import table_suffix


@dataclass(frozen=True)
class RequestVector:
    request_id: str
    title: str
    body: str | None
    status: str
    team: str
    board: str
    archived: bool
    req_date: date | None
    source_updated: int
    embedded_at: datetime
    embedding: list[float]


@dataclass(frozen=True)
class RequestHit:
    request_id: str
    title: str
    body: str | None
    status: str
    team: str
    req_date: date | None
    distance: float


@dataclass(frozen=True)
class SearchFilters:
    status: str | None = None
    team: str | None = None
    include_archived: bool = False


def table_name(model_name: str) -> str:
    return f"request_vectors__{table_suffix(model_name)}"


def create_table_sql(table: str, dimension: int) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
  request_id VARCHAR(32) NOT NULL PRIMARY KEY,
  title VARCHAR(500) NOT NULL,
  body MEDIUMTEXT NULL,
  status VARCHAR(60) NOT NULL DEFAULT '',
  team VARCHAR(60) NOT NULL DEFAULT '',
  board VARCHAR(40) NOT NULL DEFAULT '',
  archived TINYINT(1) NOT NULL DEFAULT 0,
  req_date DATE NULL,
  source_updated INT UNSIGNED NOT NULL,
  embedded_at DATETIME NOT NULL,
  embedding VECTOR({dimension}) NOT NULL,
  VECTOR INDEX (embedding),
  INDEX idx_archived (archived),
  INDEX idx_status (status)
)
"""


def upsert_sql(table: str) -> str:
    return f"""
INSERT INTO {table}
  (request_id, title, body, status, team, board, archived, req_date, source_updated, embedded_at, embedding)
VALUES
  (:request_id, :title, :body, :status, :team, :board, :archived, :req_date, :source_updated, :embedded_at,
   VEC_FromText(:embedding))
ON DUPLICATE KEY UPDATE
  title = VALUES(title), body = VALUES(body), status = VALUES(status), team = VALUES(team),
  board = VALUES(board), archived = VALUES(archived), req_date = VALUES(req_date),
  source_updated = VALUES(source_updated), embedded_at = VALUES(embedded_at), embedding = VALUES(embedding)
"""


def search_sql(table: str, filters: SearchFilters) -> str:
    """채워진 조건만 WHERE에 붙인다. 값은 전부 바인딩 파라미터다."""
    conditions: list[str] = []
    if not filters.include_archived:
        conditions.append("archived = 0")
    if filters.status is not None:
        conditions.append("status = :status")
    if filters.team is not None:
        conditions.append("team = :team")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return f"""
SELECT request_id, title, body, status, team, req_date,
       VEC_DISTANCE_COSINE(embedding, VEC_FromText(:query)) AS distance
FROM {table}
{where}
ORDER BY distance
LIMIT :limit
"""


class RequestVectorRepository:
    def __init__(self, engine: Engine, model_name: str) -> None:
        self._engine = engine
        self.table = table_name(model_name)

    def ensure_table(self, dimension: int) -> None:
        with self._engine.begin() as conn:
            conn.execute(text(create_table_sql(self.table, dimension)))

    def upsert(self, rows: list[RequestVector]) -> None:
        if not rows:
            return
        params = [
            {
                "request_id": r.request_id,
                "title": r.title,
                "body": r.body,
                "status": r.status,
                "team": r.team,
                "board": r.board,
                "archived": int(r.archived),
                "req_date": r.req_date,
                "source_updated": r.source_updated,
                "embedded_at": r.embedded_at,
                "embedding": json.dumps(r.embedding),
            }
            for r in rows
        ]
        with self._engine.begin() as conn:
            conn.execute(text(upsert_sql(self.table)), params)

    def search(self, embedding: list[float], filters: SearchFilters, limit: int) -> list[RequestHit]:
        params: dict[str, object] = {"query": json.dumps(embedding), "limit": limit}
        if filters.status is not None:
            params["status"] = filters.status
        if filters.team is not None:
            params["team"] = filters.team
        with self._engine.connect() as conn:
            rows = conn.execute(text(search_sql(self.table, filters)), params).mappings().all()
        return [
            RequestHit(
                request_id=row["request_id"],
                title=row["title"],
                body=row["body"],
                status=row["status"],
                team=row["team"],
                req_date=row["req_date"],
                distance=float(row["distance"]),
            )
            for row in rows
        ]
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/repositories/test_request_vectors.py -v`
Expected: PASS

- [ ] **Step 5: MariaDB 통합 테스트**

우리가 만든 DDL·upsert·검색 SQL이 실제 MariaDB에서 실행되는지 확인한다. `DATABASE_URL`이 MariaDB를 가리킬 때만 돌고, 아니면 건너뛴다. CI는 MariaDB를 띄우므로 CI에서 돈다.

`tests/repositories/test_request_vectors_mariadb.py`:

```python
"""벡터 테이블 SQL이 실제 MariaDB에서 실행되는지 확인한다. MariaDB가 없으면 건너뛴다."""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import Engine, create_engine, text

from blue_chatbot.configs.core import config
from blue_chatbot.repositories.request_vectors import (
    RequestVector,
    RequestVectorRepository,
    SearchFilters,
)
from blue_chatbot.support import utc_now

MODEL = "test-probe"


def mariadb_engine() -> Engine | None:
    try:
        engine = create_engine(config.database_url.get_secret_value())
        with engine.connect() as conn:
            version = conn.execute(text("SELECT VERSION()")).scalar_one()
        return engine if "MariaDB" in str(version) else None
    except Exception:
        return None


@pytest.fixture
def vectors() -> Iterator[RequestVectorRepository]:
    engine = mariadb_engine()
    if engine is None:
        pytest.skip("DATABASE_URL이 MariaDB를 가리키지 않는다")
    repo = RequestVectorRepository(engine, MODEL)
    repo.ensure_table(3)
    yield repo
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {repo.table}"))
    engine.dispose()


def vector(request_id: str, embedding: list[float], *, status: str = "완료", archived: bool = False) -> RequestVector:
    return RequestVector(
        request_id=request_id, title=f"제목 {request_id}", body="본문", status=status, team="블루소프트",
        board="블루소프트", archived=archived, req_date=date(2026, 1, 1), source_updated=1,
        embedded_at=utc_now(), embedding=embedding,
    )


def test_저장하고_가까운_순으로_찾는다(vectors: RequestVectorRepository) -> None:
    vectors.upsert([vector("R1", [1.0, 0.0, 0.0]), vector("R2", [0.0, 1.0, 0.0])])

    hits = vectors.search([1.0, 0.0, 0.0], SearchFilters(), limit=2)

    assert [h.request_id for h in hits] == ["R1", "R2"]
    assert hits[0].distance < hits[1].distance


def test_다시_저장하면_덮어쓴다(vectors: RequestVectorRepository) -> None:
    vectors.upsert([vector("R1", [1.0, 0.0, 0.0], status="보류")])
    vectors.upsert([vector("R1", [1.0, 0.0, 0.0], status="완료")])

    hits = vectors.search([1.0, 0.0, 0.0], SearchFilters(), limit=5)

    assert [(h.request_id, h.status) for h in hits] == [("R1", "완료")]


def test_보관된_것은_기본으로_빠진다(vectors: RequestVectorRepository) -> None:
    vectors.upsert([vector("R1", [1.0, 0.0, 0.0], archived=True), vector("R2", [0.0, 1.0, 0.0])])

    assert [h.request_id for h in vectors.search([1.0, 0.0, 0.0], SearchFilters(), limit=5)] == ["R2"]


def test_상태로_거른다(vectors: RequestVectorRepository) -> None:
    vectors.upsert([vector("R1", [1.0, 0.0, 0.0], status="보류"), vector("R2", [0.9, 0.1, 0.0], status="완료")])

    hits = vectors.search([1.0, 0.0, 0.0], SearchFilters(status="완료"), limit=5)

    assert [h.request_id for h in hits] == ["R2"]
```

- [ ] **Step 6: 통합 테스트 확인**

로컬 compose MariaDB로:

Run: `DATABASE_URL=mysql+pymysql://admin:1234@127.0.0.1:3308/blue_chatbot uv run pytest tests/repositories/test_request_vectors_mariadb.py -v`
Expected: 4 passed

`DATABASE_URL` 없이: `uv run pytest tests/repositories/test_request_vectors_mariadb.py -v` → 4 skipped

- [ ] **Step 7: 전체 검사와 커밋**

Run: `uv run pytest -q && uv run mypy`

```bash
git add src/blue_chatbot/repositories/request_vectors.py tests/repositories/test_request_vectors.py tests/repositories/test_request_vectors_mariadb.py
git commit -F - <<'EOF'
feat: 모델별 유지보수 요청 벡터 테이블 저장소

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 6: 색인 작업

**Files:**
- Create: `src/blue_chatbot/services/indexing.py`
- Test: `tests/services/test_indexing.py`

**Interfaces:**
- Consumes: `Embedder` (Task 2), `IndexStateRepository` (Task 3), `RequestReader`, `SourceRequest` (Task 4), `RequestVectorRepository`, `RequestVector` (Task 5)
- Produces:
  - `SOURCE_REQUESTS = "requests"`
  - `embedding_text(request: SourceRequest) -> str` — 제목과 본문 앞 2000자
  - `index_requests(reader, embedder, vectors, state, *, batch_size=100, now=utc_now) -> int` — 처리 건수

색인 위치는 전부 저장한 뒤 한 번만 옮긴다. 중간에 실패하면 위치가 그대로라 다음 실행이 같은 지점부터 다시 한다. upsert는 다시 실행해도 결과가 같다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/services/test_indexing.py`:

```python
"""바뀐 요청만 임베딩해 저장하고, 실패하면 색인 위치를 옮기지 않는지 확인한다."""

from datetime import date, datetime

import pytest

from blue_chatbot.repositories.request_reader import SourceRequest
from blue_chatbot.repositories.request_vectors import RequestVector
from blue_chatbot.services.embedding import EmbeddingError
from blue_chatbot.services.indexing import embedding_text, index_requests
from blue_chatbot.support import utc_now
from tests.fakes import FakeEmbedder


class FakeReader:
    def __init__(self, rows: list[SourceRequest]) -> None:
        self._rows = rows
        self.cursors: list[int] = []

    def changed_since(self, cursor: int) -> list[SourceRequest]:
        self.cursors.append(cursor)
        return [r for r in self._rows if r.updated > cursor]


class FakeVectors:
    def __init__(self) -> None:
        self.dimension: int | None = None
        self.saved: list[RequestVector] = []

    def ensure_table(self, dimension: int) -> None:
        self.dimension = dimension

    def upsert(self, rows: list[RequestVector]) -> None:
        self.saved.extend(rows)


class FakeState:
    def __init__(self, cursor: int = 0) -> None:
        self.cursor = cursor
        self.sets: list[tuple[str, str, int, datetime]] = []

    def get(self, source: str, model: str) -> int:
        return self.cursor

    def set(self, source: str, model: str, cursor: int, indexed_at: datetime) -> None:
        self.cursor = cursor
        self.sets.append((source, model, cursor, indexed_at))


def request(id: str, updated: int, *, title: str = "제목", body: str | None = "본문") -> SourceRequest:
    return SourceRequest(
        id=id, title=title, body=body, status="완료", team="블루소프트", board="블루소프트",
        archived=False, date=date(2026, 1, 1), updated=updated,
    )


def test_제목과_본문을_합쳐_임베딩_문장을_만든다() -> None:
    assert embedding_text(request("R1", 1, title="제목", body="본문")) == "제목\n\n본문"


def test_본문이_없으면_제목만이다() -> None:
    assert embedding_text(request("R1", 1, title="제목", body=None)) == "제목"


def test_본문은_앞_2000자만_쓴다() -> None:
    text = embedding_text(request("R1", 1, body="가" * 3000))

    assert len(text) == len("제목\n\n") + 2000


def test_커서_이후_요청만_저장하고_커서를_최대_변경시각으로_옮긴다() -> None:
    reader = FakeReader([request("R1", 100), request("R2", 200), request("R3", 300)])
    vectors, state, embedder = FakeVectors(), FakeState(cursor=100), FakeEmbedder()

    count = index_requests(reader, embedder, vectors, state)

    assert count == 2
    assert [v.request_id for v in vectors.saved] == ["R2", "R3"]
    assert state.cursor == 300
    assert state.sets[0][:2] == ("requests", "fake")


def test_테이블을_임베딩_차원으로_준비한다() -> None:
    vectors = FakeVectors()

    index_requests(FakeReader([]), FakeEmbedder(dimension=7), vectors, FakeState())

    assert vectors.dimension == 7


def test_바뀐_것이_없으면_0이고_커서를_건드리지_않는다() -> None:
    state = FakeState(cursor=50)

    assert index_requests(FakeReader([]), FakeEmbedder(), FakeVectors(), state) == 0
    assert state.sets == []


def test_배치_크기만큼_나눠_임베딩한다() -> None:
    reader = FakeReader([request(f"R{i}", i) for i in range(1, 6)])
    embedder = FakeEmbedder()

    index_requests(reader, embedder, FakeVectors(), FakeState(), batch_size=2)

    assert [len(call) for call in embedder.calls] == [2, 2, 1]


def test_임베딩이_실패하면_커서를_옮기지_않는다() -> None:
    reader = FakeReader([request("R1", 100)])
    state = FakeState(cursor=0)

    with pytest.raises(EmbeddingError):
        index_requests(reader, FakeEmbedder(error=EmbeddingError("실패")), FakeVectors(), state)

    assert state.cursor == 0


def test_저장한_행에_원본_값과_벡터가_들어간다() -> None:
    vectors = FakeVectors()
    now = utc_now()

    index_requests(FakeReader([request("R1", 100)]), FakeEmbedder(dimension=4), vectors, FakeState(), now=lambda: now)

    saved = vectors.saved[0]
    assert (saved.request_id, saved.status, saved.source_updated, saved.embedded_at) == ("R1", "완료", 100, now)
    assert len(saved.embedding) == 4
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/services/test_indexing.py -v`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: 구현**

`src/blue_chatbot/services/indexing.py`:

```python
"""원본에서 바뀐 요청을 읽어 임베딩해 벡터 테이블에 쌓는다."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from blue_chatbot.repositories.request_reader import SourceRequest
from blue_chatbot.repositories.request_vectors import RequestVector
from blue_chatbot.services.embedding import Embedder
from blue_chatbot.support import utc_now

SOURCE_REQUESTS = "requests"
BODY_LIMIT = 2000


class RequestSource(Protocol):
    def changed_since(self, cursor: int) -> list[SourceRequest]: ...


class VectorStore(Protocol):
    def ensure_table(self, dimension: int) -> None: ...
    def upsert(self, rows: list[RequestVector]) -> None: ...


class StateStore(Protocol):
    def get(self, source: str, model: str) -> int: ...
    def set(self, source: str, model: str, cursor: int, indexed_at: datetime) -> None: ...


def embedding_text(request: SourceRequest) -> str:
    """임베딩할 문장. 제목과 본문 앞부분을 합친다."""
    if not request.body:
        return request.title
    return f"{request.title}\n\n{request.body[:BODY_LIMIT]}"


def index_requests(
    reader: RequestSource,
    embedder: Embedder,
    vectors: VectorStore,
    state: StateStore,
    *,
    batch_size: int = 100,
    now: Callable[[], datetime] = utc_now,
) -> int:
    """바뀐 요청을 임베딩해 저장하고 처리 건수를 돌려준다.

    색인 위치는 전부 저장한 뒤 한 번만 옮긴다. 중간에 실패하면 위치가 그대로라 다음 실행이
    같은 지점부터 다시 한다.
    """
    vectors.ensure_table(embedder.dimension)
    cursor = state.get(SOURCE_REQUESTS, embedder.name)
    changed = reader.changed_since(cursor)
    if not changed:
        return 0

    for start in range(0, len(changed), batch_size):
        batch = changed[start : start + batch_size]
        embeddings = embedder.embed([embedding_text(r) for r in batch])
        embedded_at = now()
        vectors.upsert([_to_vector(r, e, embedded_at) for r, e in zip(batch, embeddings, strict=True)])

    state.set(SOURCE_REQUESTS, embedder.name, max(r.updated for r in changed), now())
    return len(changed)


def _to_vector(request: SourceRequest, embedding: list[float], embedded_at: datetime) -> RequestVector:
    return RequestVector(
        request_id=request.id,
        title=request.title,
        body=request.body,
        status=request.status,
        team=request.team,
        board=request.board,
        archived=request.archived,
        req_date=request.date,
        source_updated=request.updated,
        embedded_at=embedded_at,
        embedding=embedding,
    )
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/services/test_indexing.py -v`
Expected: PASS

- [ ] **Step 5: 전체 검사와 커밋**

Run: `uv run pytest -q && uv run mypy`

```bash
git add src/blue_chatbot/services/indexing.py tests/services/test_indexing.py
git commit -F - <<'EOF'
feat: 바뀐 요청만 임베딩해 쌓는 색인 작업

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 7: 검색 자료와 도구 변환

**Files:**
- Create: `src/blue_chatbot/services/search.py`
- Modify: `src/blue_chatbot/services/llm.py` (`ToolSpec` 추가만. `generate` 변경은 Task 8)
- Test: `tests/services/test_search.py`

**Interfaces:**
- Consumes: `Embedder`, `EmbeddingError` (Task 2), `RequestVectorRepository`, `RequestHit`, `SearchFilters` (Task 5)
- Produces (`services/llm.py`):
  - `ToolSpec` (frozen dataclass): `name: str`, `description: str`, `input_schema: dict[str, Any]`, `run: Callable[[dict[str, Any]], str]`
- Produces (`services/search.py`):
  - `Evidence` (frozen dataclass): `source: str`, `id: str`, `title: str`, `content: str`
  - `EvidenceLog`: `.record(items: list[Evidence])`, `.contains(source: str, id: str) -> bool`
  - `SearchSource` 프로토콜: `name: str`, `description: str`, `input_schema() -> dict[str, Any]`, `search(raw_input: dict[str, Any]) -> list[Evidence]` (잘못된 입력이면 `ValueError`)
  - `REQUEST_STATUSES: tuple[str, ...]`, `REQUEST_TEAMS: tuple[str, ...]`
  - `RequestSearchParams(BaseModel)`: `query: str`, `status: Literal[...] | None`, `team: Literal[...] | None`, `include_archived: bool = False`, `limit: int = 5`
  - `RequestSource(vectors: RequestVectorRepository, embedder: Embedder, top_k: int)`
  - `to_tool(source: SearchSource, log: EvidenceLog) -> ToolSpec` — 검색 후 `log.record`, 모델에게 줄 문자열로 바꿈. `ValueError`·`EmbeddingError`는 문자열로 돌려준다
  - `build_sources(engine, embedder, top_k) -> list[SearchSource]`

상태·팀 허용 값은 전수조사에서 확인한 실제 값이다. 이 값은 `data/faq/workhub.yaml`의 `workhub-status-list`, `workhub-team-list`와 같아야 한다.

- [ ] **Step 1: `ToolSpec` 정의**

`src/blue_chatbot/services/llm.py`의 `T = TypeVar(...)` 앞에 추가:

```python
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    """모델에게 주는 도구 하나. run은 모델이 채운 입력을 받아 모델에게 돌려줄 문자열을 만든다."""

    name: str
    description: str
    input_schema: dict[str, Any]
    run: Callable[[dict[str, Any]], str]
```

(`from typing import Protocol, TypeVar` 줄은 `from typing import Any, Protocol, TypeVar`로 합친다.)

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/services/test_search.py`:

```python
"""파라미터 검증, 검색 결과의 근거 기록, 모델에게 주는 문자열 형식을 확인한다."""

from datetime import date
from typing import Any

import pytest

from blue_chatbot.repositories.request_vectors import RequestHit, SearchFilters
from blue_chatbot.services.embedding import EmbeddingError
from blue_chatbot.services.search import (
    REQUEST_STATUSES,
    Evidence,
    EvidenceLog,
    RequestSearchParams,
    RequestSource,
    to_tool,
)
from tests.fakes import FakeEmbedder


class FakeVectors:
    def __init__(self, hits: list[RequestHit] | None = None) -> None:
        self._hits = hits or []
        self.calls: list[tuple[list[float], SearchFilters, int]] = []

    def search(self, embedding: list[float], filters: SearchFilters, limit: int) -> list[RequestHit]:
        self.calls.append((embedding, filters, limit))
        return self._hits[:limit]


def hit(request_id: str, title: str = "제목", body: str | None = "본문") -> RequestHit:
    return RequestHit(
        request_id=request_id, title=title, body=body, status="보류", team="블루소프트",
        req_date=date(2026, 3, 1), distance=0.1,
    )


def source(vectors: FakeVectors, top_k: int = 5) -> RequestSource:
    return RequestSource(vectors, FakeEmbedder(), top_k)  # type: ignore[arg-type]


# --- 파라미터 ---------------------------------------------------------------


def test_허용된_상태만_받는다() -> None:
    assert RequestSearchParams(query="q", status="보류").status == "보류"
    with pytest.raises(ValueError):
        RequestSearchParams(query="q", status="보류 중")


def test_질문은_비면_안_된다() -> None:
    with pytest.raises(ValueError):
        RequestSearchParams(query="  ")


def test_입력_스키마에_상태_목록이_들어간다() -> None:
    schema = source(FakeVectors()).input_schema()

    assert schema["properties"]["status"]["enum"] == list(REQUEST_STATUSES)
    assert schema["required"] == ["query"]
    assert schema["additionalProperties"] is False


# --- RequestSource.search --------------------------------------------------


def test_질문을_임베딩해_검색한다() -> None:
    vectors = FakeVectors([hit("R1")])

    found = source(vectors).search({"query": "성적 오류"})

    assert [e.id for e in found] == ["R1"]
    assert vectors.calls[0][1] == SearchFilters()


def test_채운_조건을_필터로_넘긴다() -> None:
    vectors = FakeVectors()

    source(vectors).search({"query": "q", "status": "보류", "team": "블루소프트", "include_archived": True})

    assert vectors.calls[0][1] == SearchFilters(status="보류", team="블루소프트", include_archived=True)


def test_limit은_top_k를_넘지_못한다() -> None:
    vectors = FakeVectors()

    source(vectors, top_k=3).search({"query": "q", "limit": 50})

    assert vectors.calls[0][2] == 3


def test_결과를_근거로_바꾼다() -> None:
    found = source(FakeVectors([hit("R1", title="성적 오류", body="점수가 안 보임")])).search({"query": "q"})

    assert found[0].source == "requests"
    assert found[0].id == "R1"
    assert found[0].title == "성적 오류"
    assert "점수가 안 보임" in found[0].content
    assert "보류" in found[0].content


def test_잘못된_입력이면_ValueError다() -> None:
    with pytest.raises(ValueError):
        source(FakeVectors()).search({"query": "q", "status": "없는상태"})


# --- to_tool -----------------------------------------------------------------


def test_도구는_소스의_이름과_스키마를_쓴다() -> None:
    s = source(FakeVectors())

    tool = to_tool(s, EvidenceLog())

    assert tool.name == "search_requests"
    assert tool.input_schema == s.input_schema()
    assert s.description in tool.description


def test_도구를_실행하면_근거가_기록된다() -> None:
    log = EvidenceLog()
    tool = to_tool(source(FakeVectors([hit("R1"), hit("R2")])), log)

    tool.run({"query": "q"})

    assert log.contains("requests", "R1")
    assert log.contains("requests", "R2")
    assert not log.contains("requests", "R3")
    assert not log.contains("faq", "R1")


def test_도구_결과_문자열에_id와_제목이_들어간다() -> None:
    tool = to_tool(source(FakeVectors([hit("R1", title="성적 오류")])), EvidenceLog())

    text = tool.run({"query": "q"})

    assert "[requests:R1]" in text
    assert "성적 오류" in text


def test_결과가_없으면_그렇다고_말한다() -> None:
    text = to_tool(source(FakeVectors()), EvidenceLog()).run({"query": "q"})

    assert "없" in text


def test_잘못된_입력은_문자열로_돌려준다() -> None:
    text = to_tool(source(FakeVectors()), EvidenceLog()).run({"query": "q", "status": "없는상태"})

    assert "status" in text


def test_임베딩_실패도_문자열로_돌려준다() -> None:
    s = RequestSource(FakeVectors(), FakeEmbedder(error=EmbeddingError("연결 실패")), 5)  # type: ignore[arg-type]

    text = to_tool(s, EvidenceLog()).run({"query": "q"})

    assert "검색" in text and "실패" in text
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/services/test_search.py -v`
Expected: FAIL — 모듈 없음

- [ ] **Step 4: 구현**

`src/blue_chatbot/services/search.py`:

```python
"""검색 자료와 근거. 자료마다 이름·설명·검색 함수가 있고 그대로 도구가 된다."""

from dataclasses import dataclass
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from sqlalchemy import Engine

from blue_chatbot.repositories.request_vectors import (
    RequestHit,
    RequestVectorRepository,
    SearchFilters,
)
from blue_chatbot.services.embedding import Embedder, EmbeddingError
from blue_chatbot.services.llm import ToolSpec


@dataclass(frozen=True)
class Evidence:
    source: str
    id: str
    title: str
    content: str


class EvidenceLog:
    """이번 답변에서 도구가 실제로 돌려준 근거. 모델은 여기 있는 것만 인용할 수 있다."""

    def __init__(self) -> None:
        self._items: set[tuple[str, str]] = set()

    def record(self, items: list[Evidence]) -> None:
        self._items.update((e.source, e.id) for e in items)

    def contains(self, source: str, id: str) -> bool:
        return (source, id) in self._items


class SearchSource(Protocol):
    name: str
    description: str

    def input_schema(self) -> dict[str, Any]: ...
    def search(self, raw_input: dict[str, Any]) -> list[Evidence]: ...


# 업무현황판이 실제로 쓰는 값. data/faq/workhub.yaml의 목록과 같아야 한다
REQUEST_STATUSES: tuple[str, ...] = (
    "등록", "시작 전", "공수산정요청", "진행중", "보류",
    "확인요청(개발서버반영)", "확인요청(검토완료)", "확인요청(운영서버반영)",
    "운영배포요청", "재확인필요", "처리불가", "완료",
)
REQUEST_TEAMS: tuple[str, ...] = ("블루소프트", "시스템개발", "달빛소프트", "미지정", "W > B", "B > W")

RequestStatus = Literal[
    "등록", "시작 전", "공수산정요청", "진행중", "보류",
    "확인요청(개발서버반영)", "확인요청(검토완료)", "확인요청(운영서버반영)",
    "운영배포요청", "재확인필요", "처리불가", "완료",
]
RequestTeam = Literal["블루소프트", "시스템개발", "달빛소프트", "미지정", "W > B", "B > W"]


class RequestSearchParams(BaseModel):
    """모델이 채우는 값. 이 밖의 것은 받지 않는다."""

    model_config = ConfigDict(extra="forbid")

    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        description="찾을 내용을 문장으로 적는다"
    )
    status: RequestStatus | None = Field(default=None, description="요청 상태로 거른다")
    team: RequestTeam | None = Field(default=None, description="개발담당팀으로 거른다")
    include_archived: bool = Field(default=False, description="보관된 요청도 포함한다")
    limit: int = Field(default=5, ge=1, description="돌려줄 최대 건수")


class RequestSource:
    name = "search_requests"
    description = (
        "blue-iWorks 업무현황판의 유지보수 요청 이력을 뜻이 가까운 순으로 찾는다. "
        "전에 비슷한 요청이 있었는지, 어떤 요청이 어떤 상태인지 물을 때 쓴다. "
        "건수를 세는 질문에는 답하지 못한다."
    )

    def __init__(self, vectors: RequestVectorRepository, embedder: Embedder, top_k: int) -> None:
        self._vectors = vectors
        self._embedder = embedder
        self._top_k = top_k

    def input_schema(self) -> dict[str, Any]:
        schema = RequestSearchParams.model_json_schema()
        # anyOf로 표현된 선택 필드를 enum 하나로 펴서 모델이 읽기 쉽게 한다
        for name, literal in (("status", REQUEST_STATUSES), ("team", REQUEST_TEAMS)):
            schema["properties"][name] = {
                "type": "string",
                "enum": list(literal),
                "description": RequestSearchParams.model_fields[name].description,
            }
        schema["required"] = ["query"]
        schema["additionalProperties"] = False
        schema.pop("title", None)
        return schema

    def search(self, raw_input: dict[str, Any]) -> list[Evidence]:
        try:
            params = RequestSearchParams.model_validate(raw_input)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        embedding = self._embedder.embed([params.query])[0]
        filters = SearchFilters(status=params.status, team=params.team, include_archived=params.include_archived)
        hits = self._vectors.search(embedding, filters, min(params.limit, self._top_k))
        return [_to_evidence(h) for h in hits]


def _to_evidence(hit: RequestHit) -> Evidence:
    lines = [f"상태: {hit.status}", f"팀: {hit.team or '미지정'}"]
    if hit.req_date is not None:
        lines.append(f"요청일: {hit.req_date.isoformat()}")
    if hit.body:
        lines.append(hit.body[:500])
    return Evidence(source="requests", id=hit.request_id, title=hit.title, content="\n".join(lines))


def to_tool(source: SearchSource, log: EvidenceLog) -> ToolSpec:
    """검색 자료를 도구로 바꾼다. 결과는 근거 기록에 남기고 모델에게는 문자열로 준다."""

    def run(raw_input: dict[str, Any]) -> str:
        try:
            found = source.search(raw_input)
        except ValueError as exc:
            return f"입력이 잘못되었습니다: {exc}"
        except EmbeddingError as exc:
            return f"검색에 실패했습니다: {exc}"
        log.record(found)
        if not found:
            return "조건에 맞는 결과가 없습니다."
        return "\n\n".join(f"[{e.source}:{e.id}] {e.title}\n{e.content}" for e in found)

    return ToolSpec(
        name=source.name,
        description=f"{source.description} 결과를 근거로 쓰면 matched_source에 '{source.name.removeprefix('search_')}', "
        f"matched_id에 대괄호 안의 id를 적는다.",
        input_schema=source.input_schema(),
        run=run,
    )


def build_sources(engine: Engine, embedder: Embedder, top_k: int) -> list[SearchSource]:
    """등록된 검색 자료. 자료를 하나 더 붙이면 여기에 한 줄 추가한다."""
    return [
        RequestSource(RequestVectorRepository(engine, embedder.name), embedder, top_k),
    ]
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/services/test_search.py -v`
Expected: PASS

`input_schema()`가 만드는 형태가 테스트와 다르면 `RequestSearchParams.model_json_schema()` 출력을 찍어 보고 `status`/`team` 항목만 위 코드처럼 덮어쓴다. 다른 필드는 pydantic 출력을 그대로 둔다.

- [ ] **Step 6: 전체 검사와 커밋**

Run: `uv run pytest -q && uv run mypy`

```bash
git add src/blue_chatbot/services/search.py src/blue_chatbot/services/llm.py tests/services/test_search.py
git commit -F - <<'EOF'
feat: 유지보수 요청 검색 자료와 도구 변환

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 8: LLM 클라이언트 도구 루프

**Files:**
- Modify: `src/blue_chatbot/services/llm.py` (`generate`에 `tools` 파라미터)
- Modify: `src/blue_chatbot/llm/anthropic_llm.py`
- Modify: `tests/fakes.py` (`FakeLLMClient.generate`에 `tools`)
- Test: `tests/llm/test_anthropic_llm_client.py`

**Interfaces:**
- Consumes: `ToolSpec` (Task 7)
- Produces: `LLMClient.generate(*, system, messages, output_format, tools: Sequence[ToolSpec] = ()) -> T | None`

동작: `messages.parse`를 부르고 `stop_reason`이 `tool_use`면 도구를 실행해 결과를 붙이고 다시 부른다. 최대 `MAX_TOOL_ROUNDS`(5)번. `refusal`이면 `None`. 모르는 도구나 실행 중 예외는 `is_error` 결과로 모델에게 알린다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/llm/test_anthropic_llm_client.py`의 `fake_sdk`를 여러 응답을 순서대로 돌려주도록 바꾸고 도구 테스트를 추가한다.

`fake_sdk` 함수를 다음으로 교체:

```python
def fake_sdk(
    *,
    parsed: Reply | None = None,
    error: Exception | None = None,
    stop_reason: str = "end_turn",
    replies: list[SimpleNamespace] | None = None,
) -> Any:
    """messages.parse만 흉내내는 가짜 Anthropic SDK 클라이언트.

    replies를 주면 호출마다 순서대로 돌려준다. 없으면 parsed/stop_reason으로 한 번의 응답을 만든다.
    """
    calls: list[dict[str, Any]] = []
    queue = list(replies or [])

    def parse(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        if error is not None:
            raise error
        if queue:
            return queue.pop(0)
        return SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason, content=[])

    return SimpleNamespace(messages=SimpleNamespace(parse=parse), calls=calls)
```

파일 끝에 추가:

```python
# --- 도구 루프 -------------------------------------------------------------

from blue_chatbot.services.llm import ToolSpec  # noqa: E402


def tool_use_reply(tool_use_id: str, name: str, tool_input: dict[str, Any]) -> SimpleNamespace:
    block = SimpleNamespace(type="tool_use", id=tool_use_id, name=name, input=tool_input)
    return SimpleNamespace(parsed_output=None, stop_reason="tool_use", content=[block])


def final_reply(reply: Reply) -> SimpleNamespace:
    return SimpleNamespace(parsed_output=reply, stop_reason="end_turn", content=[])


def echo_tool(calls: list[dict[str, Any]], result: str = "결과") -> ToolSpec:
    def run(raw_input: dict[str, Any]) -> str:
        calls.append(raw_input)
        return result

    return ToolSpec(name="search_requests", description="설명", input_schema={"type": "object"}, run=run)


def generate_with(sdk: Any, tools: list[ToolSpec]) -> Reply | None:
    return AnthropicLLMClient(sdk).generate(
        system="지시", messages=[Message(role="user", content="질문")], output_format=Reply, tools=tools
    )


def test_도구가_없으면_tools를_보내지_않는다() -> None:
    sdk = fake_sdk(parsed=Reply(content="답"))

    call(AnthropicLLMClient(sdk))

    assert isinstance(sdk.calls[0]["tools"], anthropic.Omit)


def test_도구_정의를_SDK_형식으로_보낸다() -> None:
    sdk = fake_sdk(parsed=Reply(content="답"))
    tool = echo_tool([])

    generate_with(sdk, [tool])

    assert sdk.calls[0]["tools"] == [
        {"name": "search_requests", "description": "설명", "input_schema": {"type": "object"}}
    ]


def test_tool_use면_도구를_실행하고_결과를_붙여_다시_부른다() -> None:
    tool_calls: list[dict[str, Any]] = []
    sdk = fake_sdk(replies=[
        tool_use_reply("tu_1", "search_requests", {"query": "성적"}),
        final_reply(Reply(content="근거 있는 답")),
    ])

    result = generate_with(sdk, [echo_tool(tool_calls, "검색 결과")])

    assert result == Reply(content="근거 있는 답")
    assert tool_calls == [{"query": "성적"}]
    second = sdk.calls[1]["messages"]
    assert second[-2]["role"] == "assistant"
    assert second[-1] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "tu_1", "content": "검색 결과"}],
    }


def test_모르는_도구는_오류_결과로_알린다() -> None:
    sdk = fake_sdk(replies=[
        tool_use_reply("tu_1", "없는_도구", {}),
        final_reply(Reply(content="답")),
    ])

    generate_with(sdk, [echo_tool([])])

    result_block = sdk.calls[1]["messages"][-1]["content"][0]
    assert result_block["is_error"] is True
    assert "없는_도구" in result_block["content"]


def test_도구가_예외를_내면_오류_결과로_알린다() -> None:
    def broken(raw_input: dict[str, Any]) -> str:
        raise RuntimeError("터짐")

    tool = ToolSpec(name="search_requests", description="", input_schema={"type": "object"}, run=broken)
    sdk = fake_sdk(replies=[
        tool_use_reply("tu_1", "search_requests", {}),
        final_reply(Reply(content="답")),
    ])

    generate_with(sdk, [tool])

    result_block = sdk.calls[1]["messages"][-1]["content"][0]
    assert result_block["is_error"] is True
    assert "터짐" in result_block["content"]


def test_도구_호출이_한도를_넘으면_None이다(caplog: pytest.LogCaptureFixture) -> None:
    sdk = fake_sdk(replies=[tool_use_reply(f"tu_{i}", "search_requests", {}) for i in range(10)])

    assert generate_with(sdk, [echo_tool([])]) is None
    assert len(sdk.calls) == 5
    assert "한도" in caplog.text


def test_도구_턴에서_refusal이면_None이다() -> None:
    sdk = fake_sdk(replies=[SimpleNamespace(parsed_output=None, stop_reason="refusal", content=[])])

    assert generate_with(sdk, [echo_tool([])]) is None
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/llm/test_anthropic_llm_client.py -v`
Expected: 새 테스트 FAIL — `generate()`가 `tools`를 받지 않음

- [ ] **Step 3: 프로토콜과 가짜 갱신**

`src/blue_chatbot/services/llm.py`의 `LLMClient.generate`:

```python
class LLMClient(Protocol):
    """LLM 클라이언트"""

    def generate(
        self,
        *,
        system: str,
        messages: list[Message],
        output_format: type[T],
        tools: Sequence[ToolSpec] = (),
    ) -> T | None:
        ...
```

`from collections.abc import Callable` 줄을 `from collections.abc import Callable, Sequence`로 바꾼다.

`tests/fakes.py`의 `FakeLLMClient.generate`:

```python
    def generate(
        self,
        *,
        system: str,
        messages: list[Message],
        output_format: type[T],
        tools: Sequence[ToolSpec] = (),
    ) -> T | None:
        self.calls.append(
            {"system": system, "messages": messages, "output_format": output_format, "tools": list(tools)}
        )
        if self._error is not None:
            raise self._error
        return cast(T | None, self._result)
```

import에 `from collections.abc import Sequence`와 `from blue_chatbot.services.llm import ToolSpec`을 추가한다.

- [ ] **Step 4: Anthropic 구현**

`src/blue_chatbot/llm/anthropic_llm.py`를 다음으로 바꾼다:

```python
"""LLMClient의 Anthropic 구현. anthropic 패키지는 이 파일에서만 import한다."""

import logging
from collections.abc import Sequence
from typing import Any, TypeVar, cast

import anthropic
from anthropic.types import MessageParam, OutputConfigParam, ToolParam, ToolResultBlockParam
from pydantic import BaseModel

from blue_chatbot.messages import Message
from blue_chatbot.configs.core import config
from blue_chatbot.services.llm import (
    LLMClientRequestError,
    LLMClientRateLimitError,
    LLMClientUnreachableError,
    LLMClientVendorError,
    ToolSpec,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# 한 답변에서 도구를 부를 수 있는 최대 횟수. 넘으면 답을 만들지 않는다
MAX_TOOL_ROUNDS = 5


def _output_config() -> OutputConfigParam | anthropic.Omit:
    if not config.effort:
        return anthropic.omit
    return {"effort": config.effort}


def _tool_params(tools: Sequence[ToolSpec]) -> list[ToolParam] | anthropic.Omit:
    if not tools:
        return anthropic.omit
    return [
        ToolParam(name=t.name, description=t.description, input_schema=t.input_schema) for t in tools
    ]


class AnthropicLLMClient:
    def __init__(self, client: anthropic.Anthropic):
        self._client = client

    def generate(
        self,
        *,
        system: str,
        messages: list[Message],
        output_format: type[T],
        tools: Sequence[ToolSpec] = (),
    ) -> T | None:
        """직렬화된 응답을 반환한다. 직렬화에 실패하면 None을 반환한다.

        모델이 도구를 부르면 실행해 결과를 붙이고 다시 부른다.
        """
        params: list[MessageParam] = [MessageParam(role=m.role, content=m.content) for m in messages]
        by_name = {t.name: t for t in tools}

        for _ in range(MAX_TOOL_ROUNDS):
            message = self._parse(system, params, output_format, tools)
            if message.stop_reason == "refusal":
                return None
            if message.stop_reason != "tool_use":
                break
            params.append(MessageParam(role="assistant", content=_as_params(message.content)))
            params.append(MessageParam(role="user", content=_run_tools(message.content, by_name)))
        else:
            logger.warning("도구 호출 한도 %d회를 넘었다", MAX_TOOL_ROUNDS)
            return None

        if message.parsed_output is None:
            logger.warning("구조화 출력 파싱 실패 (stop_reason=%s)", message.stop_reason)
            return None

        return cast(T, message.parsed_output)

    def _parse(
        self, system: str, params: list[MessageParam], output_format: type[T], tools: Sequence[ToolSpec]
    ) -> Any:
        try:
            return self._client.messages.parse(
                model=config.claude_model,
                max_tokens=config.max_tokens,
                output_config=_output_config(),
                system=system,
                messages=params,
                tools=_tool_params(tools),
                output_format=output_format,
            )
        except anthropic.RateLimitError as exc:
            retry_after = int(exc.response.headers.get("retry-after", "60"))
            raise LLMClientRateLimitError(retry_after) from exc
        except (anthropic.APIConnectionError, anthropic.APITimeoutError) as exc:
            raise LLMClientUnreachableError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMClientVendorError(str(exc)) from exc
            raise LLMClientRequestError(str(exc)) from exc


def _as_params(content: Sequence[Any]) -> Any:
    """응답 블록을 다음 요청의 assistant 내용으로 그대로 넘긴다."""
    return [block.model_dump(exclude_none=True) if hasattr(block, "model_dump") else block for block in content]


def _run_tools(content: Sequence[Any], by_name: dict[str, ToolSpec]) -> list[ToolResultBlockParam]:
    results: list[ToolResultBlockParam] = []
    for block in content:
        if getattr(block, "type", None) != "tool_use":
            continue
        tool = by_name.get(block.name)
        if tool is None:
            results.append(_tool_error(block.id, f"알 수 없는 도구: {block.name}"))
            continue
        try:
            text = tool.run(dict(block.input))
        except Exception as exc:  # 도구 실패는 모델에게 알리고 답변은 계속한다
            logger.warning("도구 %s 실행 실패", block.name, exc_info=exc)
            results.append(_tool_error(block.id, f"도구 실행 실패: {exc}"))
            continue
        results.append(ToolResultBlockParam(type="tool_result", tool_use_id=block.id, content=text))
    return results


def _tool_error(tool_use_id: str, text: str) -> ToolResultBlockParam:
    return ToolResultBlockParam(type="tool_result", tool_use_id=tool_use_id, content=text, is_error=True)


def build_from_config() -> AnthropicLLMClient:
    """Claude SDK 클라이언트를 생성한다"""
    key = config.anthropic_api_key
    return AnthropicLLMClient(
        anthropic.Anthropic(api_key=key.get_secret_value() if key else None)
    )
```

가짜 SDK의 `tool_use` 블록은 `SimpleNamespace`라 `model_dump`가 없다. `_as_params`가 그 경우 블록을 그대로 넘기는 이유다. 실제 SDK 블록은 pydantic 모델이라 `model_dump`가 있다.

- [ ] **Step 5: 기존 테스트 갱신**

`test_호출_파라미터가_설정을_따른다`에 한 줄 추가:

```python
    assert isinstance(kwargs["tools"], anthropic.Omit)
```

- [ ] **Step 6: 통과 확인**

Run: `uv run pytest tests/llm/test_anthropic_llm_client.py -v`
Expected: PASS

mypy가 `MessageParam(role="assistant", content=...)`의 `content` 형식을 거부하면 `_as_params`의 반환을 `cast(list[ContentBlockParam], ...)`로 바꾸고 `from anthropic.types import ContentBlockParam`을 추가한다.

- [ ] **Step 7: 전체 검사와 커밋**

Run: `uv run pytest -q && uv run mypy`

```bash
git add src/blue_chatbot/services/llm.py src/blue_chatbot/llm/anthropic_llm.py tests/fakes.py tests/llm/test_anthropic_llm_client.py
git commit -F - <<'EOF'
feat: LLM 클라이언트가 도구를 실행하고 결과를 붙여 다시 묻는다

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 9: 답변 서비스의 근거 검증 확장

**Files:**
- Modify: `src/blue_chatbot/services/ask.py`
- Modify: `src/blue_chatbot/services/prompt.py`
- Test: `tests/services/test_ask.py`, `tests/services/test_prompt.py`

**Interfaces:**
- Consumes: `SearchSource`, `EvidenceLog`, `to_tool` (Task 7), `LLMClient.generate(tools=...)` (Task 8)
- Produces:
  - `LLMAnswer`: `content: str`, `matched_id: str | None = None`, `matched_source: str | None = None`
  - `answer(llm_client, faqs, messages, sources: Sequence[SearchSource] = ()) -> LLMAnswer` — `sources`에 기본값이 있어 기존 호출부가 그대로 동작한다
  - `_validate_answer(raw, faqs, log: EvidenceLog) -> LLMAnswer`
  - `FAQ_SOURCE = "faq"`

검증 규칙: `matched_id`가 없으면 안내 문구. `matched_source`가 없거나 `"faq"`면 FAQ id 집합에서 확인하고 `matched_source="faq"`로 채운다. 그 외 자료면 `log.contains(source, id)`로 확인한다. 통과하지 못하면 안내 문구.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/services/test_ask.py`를 다음으로 바꾼다:

```python
"""FAQ와 검색 근거로 답을 만들고 근거 없는 답을 걸러내는지 확인한다."""

from typing import Any

from blue_chatbot.messages import Message
from blue_chatbot.repositories.conversation import ConversationMessage
from blue_chatbot.support import utc_now
from blue_chatbot.services.ask import LLMAnswer, _validate_answer, answer
from blue_chatbot.services.faq import FaqEntry
from blue_chatbot.services.llm import LLMClient
from blue_chatbot.services.search import Evidence, EvidenceLog
from tests.fakes import FakeLLMClient

FAQS = [
    FaqEntry(id="refund", question="환불 되나요?", answer="7일 이내 가능합니다."),
]
FALLBACK = "질문에 알맞은 대답을 찾을 수 없습니다."


class FakeSource:
    name = "search_requests"
    description = "요청 검색"

    def __init__(self, found: list[Evidence] | None = None) -> None:
        self._found = found or []
        self.inputs: list[dict[str, Any]] = []

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}

    def search(self, raw_input: dict[str, Any]) -> list[Evidence]:
        self.inputs.append(raw_input)
        return self._found


def stored(role: str, content: str) -> ConversationMessage:
    return ConversationMessage(conversation_id=1, role=role, content=content, created_at=utc_now())


def ask(client: FakeLLMClient, question: str = "환불 되나요?", sources: list[FakeSource] | None = None) -> LLMAnswer:
    return answer(client, FAQS, [stored("user", question)], sources or [])


def logged(*items: tuple[str, str]) -> EvidenceLog:
    log = EvidenceLog()
    log.record([Evidence(source=s, id=i, title="", content="") for s, i in items])
    return log


def test_가짜가_LLMClient_프로토콜을_만족한다() -> None:
    client: LLMClient = FakeLLMClient(None)

    assert client.generate(system="", messages=[], output_format=LLMAnswer) is None


# --- _validate_answer: 근거 검증 규칙 -------------------------------------


def test_실재하는_FAQ_id면_통과하고_source를_faq로_채운다() -> None:
    raw = LLMAnswer(content="7일 이내 가능합니다.", matched_id="refund")

    result = _validate_answer(raw, FAQS, EvidenceLog())

    assert result.content == raw.content
    assert (result.matched_source, result.matched_id) == ("faq", "refund")


def test_source를_faq로_적어도_통과한다() -> None:
    raw = LLMAnswer(content="답", matched_id="refund", matched_source="faq")

    assert _validate_answer(raw, FAQS, EvidenceLog()).matched_id == "refund"


def test_matched_id가_없으면_거부한다() -> None:
    raw = LLMAnswer(content="아마 가능할 겁니다.", matched_id=None)

    assert _validate_answer(raw, FAQS, EvidenceLog()).content == FALLBACK


def test_존재하지_않는_FAQ_id면_거부한다() -> None:
    raw = LLMAnswer(content="그럴듯한 답", matched_id="지어낸-id")

    result = _validate_answer(raw, FAQS, EvidenceLog())

    assert result.content == FALLBACK
    assert result.matched_id is None
    assert result.matched_source is None


def test_도구가_돌려준_근거면_통과한다() -> None:
    raw = LLMAnswer(content="전에 같은 요청이 있었습니다.", matched_id="R1", matched_source="requests")

    result = _validate_answer(raw, FAQS, logged(("requests", "R1")))

    assert (result.matched_source, result.matched_id) == ("requests", "R1")


def test_도구가_돌려주지_않은_id면_거부한다() -> None:
    raw = LLMAnswer(content="지어낸 답", matched_id="R9", matched_source="requests")

    assert _validate_answer(raw, FAQS, logged(("requests", "R1"))).content == FALLBACK


def test_source가_다르면_id가_같아도_거부한다() -> None:
    raw = LLMAnswer(content="답", matched_id="refund", matched_source="requests")

    assert _validate_answer(raw, FAQS, EvidenceLog()).content == FALLBACK


# --- answer ------------------------------------------------------------------


def test_검증을_통과한_응답을_그대로_돌려준다() -> None:
    parsed = LLMAnswer(content="7일 이내 가능합니다.", matched_id="refund")

    assert ask(FakeLLMClient(parsed)).content == parsed.content


def test_지어낸_matched_id는_고정_문구로_바뀐다() -> None:
    parsed = LLMAnswer(content="지어낸 답", matched_id="없는-id")

    assert ask(FakeLLMClient(parsed), "배송 문의").content == FALLBACK


def test_모델이_쓸_만한_출력을_못_주면_고정_문구를_돌려준다() -> None:
    assert ask(FakeLLMClient(None)).content == FALLBACK


def test_FAQ를_시스템_프롬프트로_넘긴다() -> None:
    client = FakeLLMClient(LLMAnswer(content="답", matched_id="refund"))

    ask(client)

    assert "refund" in client.calls[0]["system"]


def test_검색_자료를_도구로_넘긴다() -> None:
    client = FakeLLMClient(LLMAnswer(content="답", matched_id="refund"))

    ask(client, sources=[FakeSource()])

    tools = client.calls[0]["tools"]
    assert [t.name for t in tools] == ["search_requests"]


def test_자료가_없으면_도구를_넘기지_않는다() -> None:
    client = FakeLLMClient(LLMAnswer(content="답", matched_id="refund"))

    ask(client)

    assert client.calls[0]["tools"] == []


def test_도구가_돌려준_근거를_인용하면_통과한다() -> None:
    client = FakeLLMClient(LLMAnswer(content="전에 있었습니다.", matched_id="R1", matched_source="requests"))
    source = FakeSource([Evidence(source="requests", id="R1", title="성적 오류", content="")])

    # 가짜 클라이언트는 도구를 실행하지 않으므로 직접 실행해 근거를 기록한다
    def generate_and_run(**kwargs: Any) -> LLMAnswer:
        kwargs["tools"][0].run({"query": "성적"})
        return LLMAnswer(content="전에 있었습니다.", matched_id="R1", matched_source="requests")

    client.generate = generate_and_run  # type: ignore[method-assign]

    result = answer(client, FAQS, [stored("user", "성적 오류 전에도 있었나요?")], [source])

    assert (result.matched_source, result.matched_id) == ("requests", "R1")


def test_메시지_목록과_출력_형식을_그대로_넘긴다() -> None:
    client = FakeLLMClient(LLMAnswer(content="답", matched_id="refund"))
    messages = [
        stored("user", "환불 되나요?"),
        stored("assistant", "7일 이내 가능합니다."),
        stored("user", "배송은요?"),
    ]

    answer(client, FAQS, messages)

    assert client.calls[0]["messages"] == [
        Message(role="user", content="환불 되나요?"),
        Message(role="assistant", content="7일 이내 가능합니다."),
        Message(role="user", content="배송은요?"),
    ]
    assert client.calls[0]["output_format"] is LLMAnswer
```

`tests/services/test_prompt.py` 끝에 추가:

```python
def test_근거_출처_규칙이_들어간다() -> None:
    system = build_prompt_system(FAQS)

    assert "matched_source" in system
    assert "faq" in system
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/services/test_ask.py tests/services/test_prompt.py -v`
Expected: FAIL — `answer()` 인자 수, `matched_source` 없음

- [ ] **Step 3: 구현**

`src/blue_chatbot/services/ask.py`를 다음으로 바꾼다:

```python
from collections.abc import Sequence

from pydantic import BaseModel

from blue_chatbot.messages import Message
from blue_chatbot.repositories.conversation import ConversationMessage
from blue_chatbot.services.faq import FaqEntry
from blue_chatbot.services.llm import LLMClient
from blue_chatbot.services.prompt import build_prompt_system
from blue_chatbot.services.search import EvidenceLog, SearchSource, to_tool

FAQ_SOURCE = "faq"


class LLMAnswer(BaseModel):
    """LLM이 반환하는 구조화 출력."""

    content: str
    matched_id: str | None = None
    matched_source: str | None = None


def answer(
    llm_client: LLMClient,
    faqs: list[FaqEntry],
    messages: list[ConversationMessage],
    sources: Sequence[SearchSource] = (),
) -> LLMAnswer:
    """FAQ와 검색 자료를 근거로 답한다. 근거가 없으면 고정 문구로 대체한다."""
    log = EvidenceLog()
    raw = llm_client.generate(
        system=build_prompt_system(faqs),
        messages=_to_llm_messages(messages),
        output_format=LLMAnswer,
        tools=[to_tool(source, log) for source in sources],
    )
    if raw is None:
        return _fallback()
    return _validate_answer(raw, faqs, log)


def _to_llm_messages(messages: list[ConversationMessage]) -> list[Message]:
    # role은 DB에 문자열로 있고, Message가 Literal로 검증한다.
    return [Message.model_validate(m, from_attributes=True) for m in messages]


def _fallback() -> LLMAnswer:
    return LLMAnswer(content="질문에 알맞은 대답을 찾을 수 없습니다.", matched_id=None, matched_source=None)


def _validate_answer(raw: LLMAnswer, faqs: list[FaqEntry], log: EvidenceLog) -> LLMAnswer:
    """근거가 실제로 있는 것인지 확인한다. FAQ는 전체 id에서, 그 외 자료는 도구가 돌려준 것에서 본다."""
    if raw.matched_id is None:
        return _fallback()
    source = raw.matched_source or FAQ_SOURCE
    if source == FAQ_SOURCE:
        if raw.matched_id not in {entry.id for entry in faqs}:
            return _fallback()
        return raw.model_copy(update={"matched_source": FAQ_SOURCE})
    if not log.contains(source, raw.matched_id):
        return _fallback()
    return raw
```

`src/blue_chatbot/services/prompt.py`의 `INSTRUCTIONS` 규칙 부분을 다음으로 바꾼다:

```python
규칙:
1. 질문에 답할 근거가 FAQ에 있으면 근거로 삼은 항목의 id를 matched_id에, matched_source에 faq를 적으세요.
2. FAQ에 없고 검색 도구가 있으면 도구로 찾아보세요. 도구 결과를 근거로 쓰면 결과의 대괄호 안 출처와 id를 matched_source와 matched_id에 그대로 적으세요.
3. 어디에도 근거가 없으면 matched_id와 matched_source를 비워 두세요. 이때 답을 지어내지 마세요.
4. 인용한 근거의 내용만 재구성하세요. 원문에 없는 사실을 덧붙이지 마세요.
5. 답변은 한국어 존댓말로, 간결하게 작성하세요.
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/services/test_ask.py tests/services/test_prompt.py -v`
Expected: PASS

`sources`에 기본값이 있어 `ConversationService`와 smoke 테스트의 기존 호출은 그대로 동작한다.

- [ ] **Step 5: 전체 검사와 커밋**

Run: `uv run pytest -q && uv run mypy`
Expected: 모두 통과

```bash
git add src/blue_chatbot/services/ask.py src/blue_chatbot/services/prompt.py tests/services/test_ask.py tests/services/test_prompt.py
git commit -F - <<'EOF'
feat: 답변 근거를 출처와 id 쌍으로 검증한다

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 10: 대화 서비스·의존성·응답 연결

**Files:**
- Modify: `src/blue_chatbot/services/conversation.py`
- Modify: `src/blue_chatbot/routes/dependencies.py`
- Modify: `src/blue_chatbot/routes/ask.py`
- Test: `tests/services/test_conversation.py`, `tests/routes/test_api.py`

**Interfaces:**
- Consumes: `answer(llm_client, faqs, messages, sources)` (Task 9), `build_embedder` (Task 2), `build_sources` (Task 7)
- Produces:
  - `ConversationService(conversation_repository, message_repository, llm_client, faqs, sources, expires_after, now=utc_now)`
  - `dependencies.get_embedder() -> Embedder | None` — `openai_api_key`가 없으면 `None`
  - `dependencies.get_sources(embedder=Depends(get_embedder)) -> list[SearchSource]` — 임베더가 없으면 `[]`
  - `AskResponse`: `content`, `matched_id`, `matched_source`

- [ ] **Step 1: 실패하는 테스트 갱신**

`tests/services/test_conversation.py`의 `service` fixture:

```python
@pytest.fixture
def service(engine: Engine, llm_client: FakeLLMClient, clock: FakeClock) -> ConversationService:
    return ConversationService(
        ConversationRepository(engine),
        ConversationMessageRepository(engine),
        llm_client,
        FAQS,
        [],
        EXPIRES_AFTER,
        now=clock,
    )
```

`tests/routes/test_api.py`의 `Harness.service`:

```python
    def service(self) -> ConversationService:
        return ConversationService(
            ConversationRepository(self.engine),
            ConversationMessageRepository(self.engine),
            self.llm_client,
            FAQS,
            [],
            EXPIRES_AFTER,
            now=self.clock,
        )
```

`tests/routes/test_api.py`의 응답 본문 단언 두 곳:

```python
    assert response.json() == {"content": "7일 이내 가능합니다.", "matched_id": "refund", "matched_source": "faq"}
```

```python
    assert response.json() == {"content": FALLBACK, "matched_id": None, "matched_source": None}
```

`tests/routes/test_api.py` 끝에 추가:

```python
def test_임베딩_키가_없으면_검색_자료가_비어_있다(monkeypatch: pytest.MonkeyPatch) -> None:
    from blue_chatbot.configs.core import config
    from blue_chatbot.routes.dependencies import get_embedder, get_sources

    monkeypatch.setattr(config, "openai_api_key", None)

    assert get_embedder() is None
    assert get_sources(None) == []
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/services/test_conversation.py tests/routes/test_api.py -v`
Expected: FAIL — `ConversationService` 인자 수

- [ ] **Step 3: 대화 서비스**

`src/blue_chatbot/services/conversation.py`:

- import에 `from collections.abc import Callable, Sequence`와 `from blue_chatbot.services.search import SearchSource` 추가
- 생성자에 `sources: Sequence[SearchSource],`를 `faqs` 바로 뒤에 추가하고 `self._sources = sources` 저장
- `send_message`의 호출을 `ask.answer(self._llm_client, self._faqs, [*stored, question], self._sources)`로 바꾼다

- [ ] **Step 4: 의존성**

`src/blue_chatbot/routes/dependencies.py`:

```python
from blue_chatbot.llm.embedders import build_embedder
from blue_chatbot.services.embedding import Embedder
from blue_chatbot.services.search import SearchSource, build_sources

_embedder: Embedder | None = None


def get_embedder() -> Embedder | None:
    """임베딩 키가 없으면 None. 그러면 검색 도구 없이 FAQ만으로 답한다."""
    global _embedder
    if config.openai_api_key is None:
        return None
    if _embedder is None:
        _embedder = build_embedder(config.embedding_model)
    return _embedder


def get_sources(embedder: Embedder | None = Depends(get_embedder)) -> list[SearchSource]:
    if embedder is None:
        return []
    return build_sources(db.engine, embedder, config.search_top_k)
```

`get_conversation_service`에 `sources: list[SearchSource] = Depends(get_sources),`를 추가하고 `ConversationService(..., faqs, sources, config.conversation_expires_after)`로 넘긴다.

- [ ] **Step 5: 응답**

`src/blue_chatbot/routes/ask.py`:

```python
class AskResponse(BaseModel):
    content: str
    matched_id: str | None
    matched_source: str | None
```

```python
    return AskResponse(
        content=answer.content, matched_id=answer.matched_id, matched_source=answer.matched_source
    )
```

- [ ] **Step 6: 통과 확인**

Run: `uv run pytest -q && uv run mypy`
Expected: 모두 통과

- [ ] **Step 7: 커밋**

```bash
git add src/blue_chatbot/services/conversation.py src/blue_chatbot/routes/dependencies.py src/blue_chatbot/routes/ask.py tests/services/test_conversation.py tests/routes/test_api.py
git commit -F - <<'EOF'
feat: 검색 자료를 대화 서비스에 주입하고 응답에 근거 출처를 담는다

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 11: 색인 명령

**Files:**
- Create: `src/blue_chatbot/cli.py`
- Test: `tests/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `build_embedder` (Task 2), `IndexStateRepository` (Task 3), `RequestReader` (Task 4), `RequestVectorRepository` (Task 5), `index_requests` (Task 6)
- Produces: `python -m blue_chatbot.cli index [--model NAME]`, `build_parser() -> argparse.ArgumentParser`, `run_index(model: str | None) -> int`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_cli.py`:

```python
"""명령 인자를 읽고 색인 함수에 올바른 구성으로 넘기는지 확인한다."""

from typing import Any

import pytest

from blue_chatbot import cli


def test_index_명령을_파싱한다() -> None:
    args = cli.build_parser().parse_args(["index"])

    assert args.command == "index"
    assert args.model is None


def test_index_명령은_모델을_받는다() -> None:
    args = cli.build_parser().parse_args(["index", "--model", "openai-3-large"])

    assert args.model == "openai-3-large"


def test_원본_DB가_없으면_실패한다(monkeypatch: pytest.MonkeyPatch) -> None:
    from blue_chatbot.configs.core import config

    monkeypatch.setattr(config, "source_database_url", None)

    with pytest.raises(SystemExit, match="SOURCE_DATABASE_URL"):
        cli.run_index(None)


def test_모델을_주지_않으면_설정값을_쓴다(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import SecretStr

    from blue_chatbot.configs.core import config

    monkeypatch.setattr(config, "source_database_url", SecretStr("sqlite://"))
    monkeypatch.setattr(config, "embedding_model", "openai-3-small")
    seen: dict[str, Any] = {}

    def fake_build(name: str) -> Any:
        seen["model"] = name
        raise RuntimeError("여기까지만")

    monkeypatch.setattr(cli, "build_embedder", fake_build)

    with pytest.raises(RuntimeError):
        cli.run_index(None)

    assert seen["model"] == "openai-3-small"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: 구현**

`src/blue_chatbot/cli.py`:

```python
"""운영 명령. 색인과 모델 비교를 여기서 실행한다.

  python -m blue_chatbot.cli index [--model NAME]
"""

import argparse
import logging
import sys

from sqlalchemy import create_engine

from blue_chatbot.configs.core import config
from blue_chatbot.llm.embedders import build_embedder
from blue_chatbot.repositories import db
from blue_chatbot.repositories.index_state import IndexStateRepository
from blue_chatbot.repositories.request_reader import RequestReader
from blue_chatbot.repositories.request_vectors import RequestVectorRepository
from blue_chatbot.services.indexing import index_requests

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="blue_chatbot")
    commands = parser.add_subparsers(dest="command", required=True)

    index = commands.add_parser("index", help="바뀐 유지보수 요청을 임베딩해 쌓는다")
    index.add_argument("--model", default=None, help="임베딩 이름. 비우면 EMBEDDING_MODEL")

    return parser


def run_index(model: str | None) -> int:
    if config.source_database_url is None:
        raise SystemExit("SOURCE_DATABASE_URL이 없습니다. 색인이 읽을 원본 DB를 지정하세요.")
    embedder = build_embedder(model or config.embedding_model)
    source_engine = create_engine(config.source_database_url.get_secret_value(), pool_pre_ping=True)
    try:
        count = index_requests(
            RequestReader(source_engine),
            embedder,
            RequestVectorRepository(db.engine, embedder.name),
            IndexStateRepository(db.engine),
        )
    finally:
        source_engine.dispose()
    logger.info("%s 모델로 요청 %d건을 색인했다", embedder.name, count)
    return count


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args(argv)
    if args.command == "index":
        run_index(args.model)


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: README**

`README.md`의 `## 엔드포인트` 앞에 절을 추가:

```markdown
## 색인

유지보수 요청을 임베딩해 벡터 테이블에 쌓는다. `SOURCE_DATABASE_URL`이 가리키는 원본에서
마지막 색인 이후 바뀐 것만 읽는다. 처음 실행은 전체를 읽는다.

```bash
uv run python -m blue_chatbot.cli index                       # EMBEDDING_MODEL로
uv run python -m blue_chatbot.cli index --model openai-3-large  # 다른 모델 테이블에 병행 색인
```

모델마다 벡터 테이블이 따로 있어(`request_vectors__{모델}`) 여러 모델을 나란히 쌓을 수 있다.
검색이 어느 테이블을 보는지는 `EMBEDDING_MODEL`이 정한다.
```

- [ ] **Step 6: 전체 검사와 커밋**

Run: `uv run pytest -q && uv run mypy`

```bash
git add src/blue_chatbot/cli.py tests/test_cli.py README.md
git commit -F - <<'EOF'
feat: 유지보수 요청 색인 명령

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 12: 모델 비교

**Files:**
- Create: `src/blue_chatbot/services/compare.py`
- Create: `data/eval/requests.yaml`
- Modify: `src/blue_chatbot/cli.py` (`compare` 명령)
- Test: `tests/services/test_compare.py`, `tests/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `SearchSource` (Task 7), `build_embedder` (Task 2), `RequestVectorRepository` (Task 5), `RequestSource` (Task 7)
- Produces:
  - `EvalCase` (frozen dataclass): `question: str`, `expected: tuple[str, ...]`
  - `load_cases(path: Path) -> list[EvalCase]` — 비거나 형식이 틀리면 `ValueError`
  - `hit(found_ids: list[str], expected: tuple[str, ...]) -> bool` — 하나라도 겹치면 참
  - `recall_at_k(hits: list[bool]) -> float`
  - `evaluate(source: SearchSource, cases: list[EvalCase], k: int) -> float`
  - `python -m blue_chatbot.cli compare --models A B [--k 5] [--cases data/eval/requests.yaml]`

질문 세트는 실제 요청에서 손으로 고른다. 이 작업에서는 형식과 예시 1건만 넣고, 실제 항목은 별도로 채운다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/services/test_compare.py`:

```python
"""질문 세트를 읽고 재현율을 계산하는 규칙을 확인한다."""

from pathlib import Path
from typing import Any

import pytest

from blue_chatbot.services.compare import EvalCase, evaluate, hit, load_cases, recall_at_k
from blue_chatbot.services.search import Evidence


class FakeSource:
    name = "search_requests"
    description = ""

    def __init__(self, answers: dict[str, list[str]]) -> None:
        self._answers = answers
        self.inputs: list[dict[str, Any]] = []

    def input_schema(self) -> dict[str, Any]:
        return {}

    def search(self, raw_input: dict[str, Any]) -> list[Evidence]:
        self.inputs.append(raw_input)
        ids = self._answers.get(raw_input["query"], [])
        return [Evidence(source="requests", id=i, title="", content="") for i in ids]


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cases.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_질문_세트를_읽는다(tmp_path: Path) -> None:
    path = write(tmp_path, "- question: 성적 오류\n  expected: [R1, R2]\n- question: 출석\n  expected: [R3]\n")

    assert load_cases(path) == [
        EvalCase(question="성적 오류", expected=("R1", "R2")),
        EvalCase(question="출석", expected=("R3",)),
    ]


def test_비면_실패한다(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_cases(write(tmp_path, ""))


def test_정답이_없는_항목은_실패한다(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_cases(write(tmp_path, "- question: 질문만\n"))


@pytest.mark.parametrize(
    ("found", "expected", "result"),
    [
        (["R1", "R2"], ("R2",), True),
        (["R1"], ("R2", "R3"), False),
        ([], ("R1",), False),
    ],
)
def test_하나라도_겹치면_맞은_것이다(found: list[str], expected: tuple[str, ...], result: bool) -> None:
    assert hit(found, expected) is result


def test_재현율은_맞은_비율이다() -> None:
    assert recall_at_k([True, False, True, True]) == 0.75


def test_질문이_없으면_재현율은_0이다() -> None:
    assert recall_at_k([]) == 0.0


def test_소스에_k를_넘겨_재현율을_잰다() -> None:
    source = FakeSource({"성적 오류": ["R1"], "출석": ["R9"]})
    cases = [EvalCase("성적 오류", ("R1",)), EvalCase("출석", ("R3",))]

    result = evaluate(source, cases, k=5)

    assert result == 0.5
    assert source.inputs[0] == {"query": "성적 오류", "limit": 5, "include_archived": True}
```

`tests/test_cli.py` 끝에 추가:

```python
def test_compare_명령을_파싱한다() -> None:
    args = cli.build_parser().parse_args(["compare", "--models", "openai-3-small", "bge-m3", "--k", "3"])

    assert args.command == "compare"
    assert args.models == ["openai-3-small", "bge-m3"]
    assert args.k == 3
    assert str(args.cases) == "data/eval/requests.yaml"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/services/test_compare.py tests/test_cli.py -v`
Expected: FAIL

- [ ] **Step 3: 구현**

`src/blue_chatbot/services/compare.py`:

```python
"""임베딩 모델을 같은 질문 세트로 비교한다. 운영 코드가 아니라 비교용 도구다."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from blue_chatbot.services.search import SearchSource


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected: tuple[str, ...]


def load_cases(path: Path) -> list[EvalCase]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"질문 세트가 비어 있거나 목록이 아닙니다: {path}")
    cases: list[EvalCase] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or not item.get("question") or not item.get("expected"):
            raise ValueError(f"{index}번째 항목에 question과 expected가 있어야 합니다: {item!r}")
        cases.append(EvalCase(question=str(item["question"]), expected=tuple(str(x) for x in item["expected"])))
    return cases


def hit(found_ids: list[str], expected: tuple[str, ...]) -> bool:
    """정답 중 하나라도 결과에 있으면 맞은 것이다. 순위는 보지 않는다."""
    return bool(set(found_ids) & set(expected))


def recall_at_k(hits: list[bool]) -> float:
    if not hits:
        return 0.0
    return sum(hits) / len(hits)


def evaluate(source: SearchSource, cases: list[EvalCase], k: int) -> float:
    """보관된 요청도 포함해 찾는다. 비교는 검색 품질만 보기 때문이다."""
    hits = [
        hit([e.id for e in source.search({"query": case.question, "limit": k, "include_archived": True})], case.expected)
        for case in cases
    ]
    return recall_at_k(hits)
```

`data/eval/requests.yaml`:

```yaml
# 임베딩 모델 비교용 질문 세트. 실제 요청에서 고른 질문과, 그 질문에 나와야 하는 요청 id를 적는다.
# 기준선이 잡지 못하는 세 경우를 꼭 넣는다: 조사·어미가 다른 같은 단어, 다른 말로 쓴 같은 뜻, 오타.
# expected는 requests.id 값이다.
- question: 성적 입력 오류 전에도 있었나요?
  expected: [예시-실제-id로-바꾼다]
```

`src/blue_chatbot/cli.py`에 추가:

```python
from pathlib import Path

from blue_chatbot.services.compare import evaluate, load_cases
from blue_chatbot.services.search import RequestSource
```

`build_parser`에:

```python
    compare = commands.add_parser("compare", help="임베딩 모델별 재현율을 잰다")
    compare.add_argument("--models", nargs="+", required=True, help="비교할 임베딩 이름들")
    compare.add_argument("--k", type=int, default=5)
    compare.add_argument("--cases", type=Path, default=Path("data/eval/requests.yaml"))
```

함수 추가:

```python
def run_compare(models: list[str], k: int, cases_path: Path) -> dict[str, float]:
    cases = load_cases(cases_path)
    results: dict[str, float] = {}
    for name in models:
        embedder = build_embedder(name)
        source = RequestSource(RequestVectorRepository(db.engine, embedder.name), embedder, top_k=k)
        results[name] = evaluate(source, cases, k)
    return results
```

`main`에:

```python
    elif args.command == "compare":
        for name, recall in run_compare(args.models, args.k, args.cases).items():
            print(f"{name:<24}재현율@{args.k} = {recall:.2f}")
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/services/test_compare.py tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: README**

`## 색인` 절 뒤에 추가:

```markdown
## 모델 비교

`data/eval/requests.yaml`의 질문마다 검색해 정답 요청이 상위 k에 들어오는 비율을 모델별로 낸다.
비교할 모델은 먼저 각각 색인해 두어야 한다.

```bash
uv run python -m blue_chatbot.cli compare --models openai-3-small openai-3-large --k 5
```
```

- [ ] **Step 6: 전체 검사와 커밋**

Run: `uv run pytest -q && uv run mypy`

```bash
git add src/blue_chatbot/services/compare.py src/blue_chatbot/cli.py data/eval/requests.yaml tests/services/test_compare.py tests/test_cli.py README.md
git commit -F - <<'EOF'
feat: 임베딩 모델을 같은 질문 세트로 비교하는 명령

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 13: 문서와 실제 호출 확인

**Files:**
- Create: `docs/domain/requests-search.md`
- Modify: `docs/decision/iworks.md`
- Modify: `tests/test_smoke.py`

- [ ] **Step 1: 도메인 문서**

`docs/domain/requests-search.md`:

```markdown
# 유지보수 요청 검색

## 개념

- **검색 자료(SearchSource)**: 이름, 설명, 입력 스키마, 검색 함수를 가진 단위. 그대로 모델의 도구가 된다.
  등록 목록은 `services/search.py`의 `build_sources()`다
- **근거(Evidence)**: 자료 이름 `source`와 그 자료 안의 `id`의 쌍. 답변은 근거 하나를 `matched_source`,
  `matched_id`로 가리킨다
- **근거 기록(EvidenceLog)**: 한 답변에서 도구가 실제로 돌려준 근거의 집합. 모델은 여기 있는 것과
  FAQ만 인용할 수 있다
- **임베딩(Embedder)**: 이름과 차원을 가지며 문장을 벡터로 바꾼다. 어느 구현을 쓰는지는 `EMBEDDING_MODEL`
  설정이 정한다
- **색인 위치(index_state)**: 자료·모델 쌍이 마지막으로 처리한 원본 변경 시각

## 데이터 모델

- `request_vectors__{모델}`: 임베딩 모델마다 하나. 차원은 그 모델의 차원이다.
  `request_id`는 원본 `requests.id`, `source_updated`는 원본의 변경 시각이다
- `index_state(source, model, cursor, indexed_at)`

## 불변식

- 모델은 `search_requests`의 정해진 파라미터 값만 채운다. 모델이 쓴 문자열은 SQL에 들어가지 않는다
- `status`, `team`은 허용 목록 밖의 값이면 거부한다. 목록은 `data/faq/workhub.yaml`과 같다
- 답변의 `(matched_source, matched_id)`는 FAQ의 id이거나 이번 답변에서 도구가 돌려준 근거여야 한다.
  아니면 안내 문구로 바뀐다
- 색인 위치는 그 실행의 모든 요청을 저장한 뒤 한 번만 옮긴다. 중간에 실패하면 옮기지 않는다
- 임베딩 키가 없으면 검색 도구가 없고 FAQ만으로 답한다
```

- [ ] **Step 2: 결정 문서 정리**

`docs/decision/iworks.md`에서 이번 작업으로 구현된 결정을 지운다. CONTRIBUTING에 따라 지운 내용은 메인테이너가 `history` 브랜치에 옮긴다.

`## 정보 안내` 절의 세 항목과 `## 벡터 저장소` 절 전체를 지운다. 대신 `## 정보 안내` 아래에 남길 것만 둔다:

```markdown
## 정보 안내

- 검색 대상 문서에 포털 문서를 추가한다. FAQ 형식이 아닌 문서도 넣는다. 유지보수 요청 검색은 구현됐고,
  포털 문서는 아직이다
```

`## 벡터 저장소` 절은 삭제한다 (Qdrant 결정은 MariaDB로 바뀌어 구현됐다).

- [ ] **Step 3: 실제 도구 왕복 확인 (smoke)**

`tests/test_smoke.py` 끝에 추가. 실제 Claude API를 부르므로 `smoke` 마커다. 임베딩은 부르지 않도록 가짜 자료를 쓴다.

```python
from typing import Any

from blue_chatbot.services.search import Evidence


class StubSource:
    name = "search_requests"
    description = "유지보수 요청 이력을 찾는다. 전에 비슷한 요청이 있었는지 물을 때 쓴다."

    def __init__(self) -> None:
        self.inputs: list[dict[str, Any]] = []

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "찾을 내용"}},
            "required": ["query"],
            "additionalProperties": False,
        }

    def search(self, raw_input: dict[str, Any]) -> list[Evidence]:
        self.inputs.append(raw_input)
        return [Evidence(source="requests", id="R-STUB-1", title="성적 입력 오류", content="상태: 완료\n점수가 저장되지 않던 문제를 고쳤다")]


@pytest.mark.smoke
def test_FAQ에_없는_질문은_도구를_부르고_그_근거를_인용한다(model: LLMClient, faqs: list[FaqEntry]) -> None:
    source = StubSource()
    question = ConversationMessage(
        conversation_id=0, role="user", content="성적 입력 오류가 전에도 있었나요?", created_at=utc_now()
    )

    result = answer(model, faqs, [question], [source])

    assert source.inputs, "모델이 검색 도구를 부르지 않았다"
    assert (result.matched_source, result.matched_id) == ("requests", "R-STUB-1")
```

- [ ] **Step 4: smoke 실행**

Run: `uv run pytest -m smoke tests/test_smoke.py -v`
Expected: 3 passed. 비용이 발생한다. 실패하면 `services/prompt.py`의 규칙 문구와 `to_tool()`의 설명 문구를 다듬는다.

- [ ] **Step 5: 전체 검사와 커밋**

Run: `uv run pytest -q && uv run mypy`

```bash
git add docs/domain/requests-search.md docs/decision/iworks.md tests/test_smoke.py
git commit -F - <<'EOF'
docs: 유지보수 요청 검색 개념과 불변식을 기록하고 구현된 결정을 지운다

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

## 마무리

- 브랜치를 푸시하고 PR을 만든다. 제목은 이슈 제목 그대로, 본문에 작업요약·주요변경사항·테스트 결과·`Closes #{N}`
- PR 본문 끝에 `🤖 Generated with [Claude Code](https://claude.com/claude-code)`
- 코드 수정이 있으므로 Claude 리뷰를 받은 뒤 머지한다
- `docs/decision/iworks.md`에서 지운 내용은 메인테이너가 `history` 브랜치에 직접 커밋한다

## 이 계획이 정하지 않은 것

- **실제 질문 세트.** `data/eval/requests.yaml`은 형식과 예시만 있다. 실제 요청 id로 20~50건을 채우는 일은 데이터를 보며 손으로 한다
- **색인 실행 주기.** 크론 등록은 배포 위치가 정해진 뒤에 한다
- **운영에서 `SOURCE_DATABASE_URL`이 가리킬 곳.** 읽기 전용 계정을 쓴다는 것만 정해져 있다
- **응답 스트리밍 중 도구 호출 구간 표시.** 스트리밍 자체가 아직 구현되지 않았다
