from pathlib import Path

import pytest

from blue_chatbot.services.faq import FaqEntry, FaqError, load


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "faq.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_정상_파일을_순서대로_읽는다(tmp_path):
    path = write(tmp_path, """
- id: a
  question: 질문 A
  answer: 답변 A
- id: b
  question: 질문 B
  answer: 답변 B
""")

    entries = load(path)

    assert entries == [
        FaqEntry(id="a", question="질문 A", answer="답변 A"),
        FaqEntry(id="b", question="질문 B", answer="답변 B"),
    ]


def test_id가_중복되면_실패한다(tmp_path):
    path = write(tmp_path, """
- id: a
  question: 질문 1
  answer: 답변 1
- id: a
  question: 질문 2
  answer: 답변 2
""")

    with pytest.raises(FaqError, match="중복"):
        load(path)


def test_id가_없으면_실패한다(tmp_path):
    path = write(tmp_path, """
- question: 질문만 있다
  answer: 답변
""")

    with pytest.raises(FaqError, match="id"):
        load(path)


def test_answer가_없으면_실패한다(tmp_path):
    path = write(tmp_path, """
- id: a
  question: 질문
""")

    with pytest.raises(FaqError, match="answer"):
        load(path)


def test_빈_파일이면_실패한다(tmp_path):
    path = write(tmp_path, "")

    with pytest.raises(FaqError, match="비어"):
        load(path)


def test_최상위가_리스트가_아니면_실패한다(tmp_path):
    path = write(tmp_path, "id: a\nquestion: q\nanswer: a\n")

    with pytest.raises(FaqError, match="목록"):
        load(path)


def test_실제_샘플_파일이_로딩된다():
    entries = load(Path("data/faq.yaml"))

    assert len(entries) >= 1
    assert all(entry.id for entry in entries)
