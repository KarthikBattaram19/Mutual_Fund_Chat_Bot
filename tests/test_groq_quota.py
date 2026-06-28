import pytest

from rag.quota import GroqQuotaExceeded, GroqQuotaGuard, GroqQuotaLimits, estimate_tokens


def test_quota_blocks_requests_per_minute() -> None:
    guard = GroqQuotaGuard(limits=GroqQuotaLimits(requests_per_minute=1))

    guard.check_and_record(estimated_tokens=1)
    with pytest.raises(GroqQuotaExceeded, match="minute"):
        guard.check_and_record(estimated_tokens=1)


def test_quota_blocks_requests_per_day() -> None:
    guard = GroqQuotaGuard(limits=GroqQuotaLimits(requests_per_minute=10, requests_per_day=1))

    guard.check_and_record(estimated_tokens=1)
    with pytest.raises(GroqQuotaExceeded, match="day"):
        guard.check_and_record(estimated_tokens=1)


def test_quota_blocks_tokens_per_minute() -> None:
    guard = GroqQuotaGuard(limits=GroqQuotaLimits(tokens_per_minute=10))

    with pytest.raises(GroqQuotaExceeded, match="token-per-minute"):
        guard.check_and_record(estimated_tokens=11)


def test_quota_blocks_tokens_per_day() -> None:
    guard = GroqQuotaGuard(limits=GroqQuotaLimits(tokens_per_minute=100, tokens_per_day=10))

    with pytest.raises(GroqQuotaExceeded, match="token-per-day"):
        guard.check_and_record(estimated_tokens=11)


def test_estimate_tokens_is_conservative_positive_count() -> None:
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2
