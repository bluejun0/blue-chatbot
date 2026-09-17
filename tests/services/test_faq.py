from pathlib import Path

import pytest

from blue_chatbot.services.faq import FaqEntry, FaqError, by_domain, load, load_domains


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "faq.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_정상_파일을_순서대로_읽는다(tmp_path: Path) -> None:
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


def test_id가_중복되면_실패한다(tmp_path: Path) -> None:
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


def test_id가_없으면_실패한다(tmp_path: Path) -> None:
    path = write(tmp_path, """
- question: 질문만 있다
  answer: 답변
""")

    with pytest.raises(FaqError, match="id"):
        load(path)


def test_answer가_없으면_실패한다(tmp_path: Path) -> None:
    path = write(tmp_path, """
- id: a
  question: 질문
""")

    with pytest.raises(FaqError, match="answer"):
        load(path)


def test_빈_파일이면_실패한다(tmp_path: Path) -> None:
    path = write(tmp_path, "")

    with pytest.raises(FaqError, match="비어"):
        load(path)


def test_최상위가_리스트가_아니면_실패한다(tmp_path: Path) -> None:
    path = write(tmp_path, "id: a\nquestion: q\nanswer: a\n")

    with pytest.raises(FaqError, match="목록"):
        load(path)


def write_domain(dir: Path, domain: str, text: str) -> Path:
    path = dir / f"{domain}.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_파일_이름이_도메인이_된다(tmp_path: Path) -> None:
    write_domain(tmp_path, "workhub", "- id: a\n  question: 질문\n  answer: 답변\n")

    entries = load_domains(tmp_path)

    assert entries == [FaqEntry(id="a", question="질문", answer="답변", domain="workhub")]


def test_여러_도메인을_파일_이름_순서로_읽는다(tmp_path: Path) -> None:
    write_domain(tmp_path, "envhub", "- id: b\n  question: 질문 B\n  answer: 답변 B\n")
    write_domain(tmp_path, "workhub", "- id: a\n  question: 질문 A\n  answer: 답변 A\n")

    entries = load_domains(tmp_path)

    assert [(e.domain, e.id) for e in entries] == [("envhub", "b"), ("workhub", "a")]


def test_도메인이_달라도_id가_겹치면_실패한다(tmp_path: Path) -> None:
    write_domain(tmp_path, "envhub", "- id: a\n  question: 질문 B\n  answer: 답변 B\n")
    write_domain(tmp_path, "workhub", "- id: a\n  question: 질문 A\n  answer: 답변 A\n")

    with pytest.raises(FaqError, match="중복"):
        load_domains(tmp_path)


def test_파일이_하나도_없으면_실패한다(tmp_path: Path) -> None:
    with pytest.raises(FaqError, match="없습니다"):
        load_domains(tmp_path)


def test_도메인별로_묶는다() -> None:
    entries = [
        FaqEntry(id="a", question="질문 A", answer="답변 A", domain="workhub"),
        FaqEntry(id="b", question="질문 B", answer="답변 B", domain="envhub"),
        FaqEntry(id="c", question="질문 C", answer="답변 C", domain="workhub"),
    ]

    assert by_domain(entries) == {
        "workhub": [entries[0], entries[2]],
        "envhub": [entries[1]],
    }


def test_실제_샘플_파일이_로딩된다() -> None:
    entries = load_domains(Path("data/faq"))

    assert len(entries) >= 1
    assert all(entry.id for entry in entries)
    assert all(entry.domain for entry in entries)
