"""아키텍처 경계가 유지되는지 확인한다.

제공자를 바꿀 때 고칠 파일이 하나로 유지되는지를 구조로 검사한다.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "blue_chatbot"
BOUNDARY = SRC / "llm" / "anthropic_llm.py"
IMPORTS_ANTHROPIC = re.compile(r"^\s*(?:import anthropic|from anthropic)", re.MULTILINE)


def test_경계_밖에서는_anthropic_SDK를_모른다() -> None:
    offenders = sorted(
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if path != BOUNDARY and IMPORTS_ANTHROPIC.search(path.read_text(encoding="utf-8"))
    )

    assert offenders == []
