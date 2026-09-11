FROM python:3.12-slim

RUN pip install --no-cache-dir uv==0.12.1

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# 의존성 모듈 설치
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

EXPOSE 8003

CMD ["uvicorn", "blue_chatbot.main:app", "--host", "0.0.0.0", "--port", "8003"]
