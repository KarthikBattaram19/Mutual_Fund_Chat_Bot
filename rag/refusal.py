from __future__ import annotations

from dataclasses import dataclass

from rag.classifier import ClassificationResult, QueryIntent


EDUCATIONAL_URL = "https://www.amfiindia.com/investor-corner/knowledge-center"


@dataclass(frozen=True)
class RefusalResponse:
    type: str
    message: str
    educational_url: str = EDUCATIONAL_URL


class RefusalHandler:
    """Build user-safe refusal messages for blocked query classes."""

    def build(self, classification: ClassificationResult) -> RefusalResponse:
        if classification.intent == QueryIntent.PII_DETECTED:
            message = "I cannot process personal or account information. Please ask a factual question without PAN, Aadhaar, phone, email, OTP, or account details."
        elif classification.intent == QueryIntent.OUT_OF_SCOPE:
            schemes = ", ".join(classification.supported_schemes)
            message = f"I can answer only from the configured Groww corpus for these schemes: {schemes}."
        elif classification.intent == QueryIntent.PERFORMANCE:
            message = "I cannot quote or compare historical returns. Please refer to the scheme's Groww page for performance information."
        else:
            message = "I can only provide factual information about mutual fund schemes and cannot offer investment advice or recommendations."

        return RefusalResponse(type="refusal", message=message)
