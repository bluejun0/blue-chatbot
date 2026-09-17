from datetime import datetime, timedelta

from blue_chatbot.support import utc_now


class FakeClock:
    """now()가 돌려줄 시각을 테스트가 직접 민다."""

    def __init__(self) -> None:
        self.current = utc_now()

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta
