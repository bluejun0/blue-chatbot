from blue_chatbot.services.faq import FaqEntry
from blue_chatbot.services.prompt import build_prompt_system

FAQS = [
    FaqEntry(id="refund", question="환불 되나요?", answer="7일 이내 가능합니다."),
    FaqEntry(id="hours", question="운영 시간은?", answer="평일 09:00~18:00입니다."),
]


def test_모든_항목이_프롬프트에_포함된다() -> None:
    system = build_prompt_system(FAQS)

    for faq in FAQS:
        assert faq.id in system
        assert faq.question in system
        assert faq.answer in system


def test_같은_입력이면_같은_출력이다() -> None:
    assert build_prompt_system(FAQS) == build_prompt_system(FAQS)


def test_matched_id_규칙이_들어간다() -> None:
    assert "matched_id" in build_prompt_system(FAQS)


def test_항목_순서가_보존된다() -> None:
    system = build_prompt_system(FAQS)

    assert system.index("refund") < system.index("hours")


def test_빈_FAQ면_지시문만_남는다() -> None:
    system = build_prompt_system([])

    assert system
    assert "matched_id" in system
