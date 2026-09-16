import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, StringConstraints

from blue_chatbot.routes.dependencies import get_faq, get_model
from blue_chatbot.services import ask
from blue_chatbot.services.faq import FaqEntry
from blue_chatbot.services.model import (
    Message,
    ModelClient,
    ModelFailed,
    ModelRateLimited,
    ModelUnreachable,
    ModelUpstreamError,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class AskRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


@router.post("/ask")
def post_ask(
    ask_request: AskRequest,
    entries: list[FaqEntry] = Depends(get_faq),
    model: ModelClient = Depends(get_model),
) -> ask.Answer:
    messages = [Message(role="user", content=ask_request.question)]
    try:
        return ask.answer(model, entries, messages)
    except ModelRateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="요청이 많습니다. 잠시 후 다시 시도해 주세요.",
            headers={"retry-after": str(exc.retry_after)},
        ) from exc
    except ModelUnreachable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="일시적으로 응답할 수 없습니다.",
        ) from exc
    except ModelUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="서버 오류입니다.",
        ) from exc
    except ModelFailed as exc:
        logger.error("모델 호출 실패", exc_info=exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) from exc
