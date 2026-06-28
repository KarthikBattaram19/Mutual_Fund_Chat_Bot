import pytest

from rag.validator import ResponseValidationError, ResponseValidator


def test_validator_accepts_short_grounded_fact() -> None:
    answer = ResponseValidator().validate(
        "The expense ratio is 0.75%.",
        context="Expense ratio: 0.75%",
    )

    assert answer == "The expense ratio is 0.75%."


def test_validator_blocks_advisory_language() -> None:
    with pytest.raises(ResponseValidationError, match="advisory"):
        ResponseValidator().validate(
            "You should invest in this fund.",
            context="Expense ratio: 0.75%",
        )


def test_validator_blocks_more_than_three_sentences() -> None:
    with pytest.raises(ResponseValidationError, match="sentence"):
        ResponseValidator().validate(
            "One. Two. Three. Four.",
            context="One Two Three Four",
        )


def test_validator_blocks_return_content() -> None:
    with pytest.raises(ResponseValidationError, match="performance"):
        ResponseValidator().validate(
            "The 1-year return is 12%.",
            context="NAV: Rs 100",
        )


def test_validator_blocks_ungrounded_answer() -> None:
    with pytest.raises(ResponseValidationError, match="grounded"):
        ResponseValidator().validate(
            "The benchmark is NIFTY 50 TRI.",
            context="Expense ratio: 0.75%",
        )
