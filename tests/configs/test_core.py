from blue_chatbot.configs.core import CoreConfig


def test_effort를_빈_문자열로_주면_보내지_않는다는_뜻이_된다() -> None:
    # effort를 받지 않는 모델에 이 파라미터를 넘기면 400이 난다.
    config = CoreConfig(
        _env_file=None,
        database_url="mysql+pymysql://t:t@localhost:3306/t",
        effort="",
    )

    assert config.effort is None
