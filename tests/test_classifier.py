from rag.classifier import QueryClassifier, QueryIntent


def test_classifier_allows_factual_query() -> None:
    result = QueryClassifier().classify("What is the expense ratio of HDFC Mid Cap Fund?")

    assert result.intent == QueryIntent.FACTUAL


def test_classifier_refuses_advisory_query_before_retrieval() -> None:
    result = QueryClassifier().classify("Should I invest in HDFC Mid Cap Fund?")

    assert result.intent == QueryIntent.ADVISORY


def test_classifier_refuses_which_fund_is_best_with_category_modifier() -> None:
    result = QueryClassifier().classify("Can you tell me which mid cap fund is best?")

    assert result.intent == QueryIntent.ADVISORY


def test_classifier_detects_performance_query() -> None:
    result = QueryClassifier().classify("What are the 1-year returns of HDFC Small Cap Fund?")

    assert result.intent == QueryIntent.PERFORMANCE


def test_classifier_detects_pii_query() -> None:
    result = QueryClassifier().classify("My PAN is ABCDE1234F, what fund should I buy?")

    assert result.intent == QueryIntent.PII_DETECTED


def test_classifier_detects_unsupported_hdfc_scheme() -> None:
    result = QueryClassifier().classify("What is the NAV of HDFC Balanced Advantage Fund?")

    assert result.intent == QueryIntent.OUT_OF_SCOPE
    assert "HDFC Mid Cap Fund - Direct Growth" in result.supported_schemes
