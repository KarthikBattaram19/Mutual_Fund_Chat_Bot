from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ingestion.chunker import CorpusChunk
from rag.classifier import ClassificationResult, QueryClassifier, QueryIntent
from rag.formatter import AnswerResponse, ResponseFormatter
from rag.generator import GroqGenerationError, GroqGenerator
from rag.quota import GroqQuotaExceeded
from rag.refusal import RefusalHandler, RefusalResponse
from rag.retriever import ChromaRetriever, RetrievalError, RetrievalResult
from rag.validator import ResponseValidationError, ResponseValidator

logger = logging.getLogger(__name__)


class AskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class AnswerPayload(BaseModel):
    type: str
    answer: str
    source_url: str
    last_updated: str


class RefusalPayload(BaseModel):
    type: str
    message: str
    educational_url: str


class ErrorPayload(BaseModel):
    type: str
    message: str


class RetrieverProtocol(Protocol):
    def retrieve(self, query: str) -> RetrievalResult:
        ...


class GeneratorProtocol(Protocol):
    def generate(self, *, query: str, chunks: list[Any]) -> str:
        ...


@dataclass
class AskService:
    classifier: QueryClassifier = field(default_factory=QueryClassifier)
    retriever: RetrieverProtocol = field(default_factory=ChromaRetriever)
    generator: GeneratorProtocol = field(default_factory=GroqGenerator)
    validator: ResponseValidator = field(default_factory=ResponseValidator)
    formatter: ResponseFormatter = field(default_factory=ResponseFormatter)
    refusal_handler: RefusalHandler = field(default_factory=RefusalHandler)

    def ask(self, query: str) -> AnswerResponse | RefusalResponse:
        stripped_query = query.strip()
        if not stripped_query:
            raise ValueError("query cannot be empty")

        classification = self.classifier.classify(stripped_query)
        if classification.intent == QueryIntent.PERFORMANCE and len(classification.matched_schemes) == 1:
            return self._build_performance_link_response(classification.matched_schemes[0])
        if classification.intent != QueryIntent.FACTUAL:
            return self.refusal_handler.build(classification)

        retrieval_started = perf_counter()
        retrieval = self.retriever.retrieve(stripped_query)
        retrieval_seconds = perf_counter() - retrieval_started
        if not retrieval.ok:
            logger.info(
                "ask refusal=low_confidence retrieval_seconds=%.3f query_chars=%d",
                retrieval_seconds,
                len(stripped_query),
            )
            return RefusalResponse(
                type="refusal",
                message="I could not find this information in the configured Groww corpus.",
            )

        generation_started = perf_counter()
        generated = self.generator.generate(query=stripped_query, chunks=retrieval.chunks)
        generation_seconds = perf_counter() - generation_started
        context = "\n".join(chunk.content for chunk in retrieval.chunks)
        try:
            validated = self.validator.validate(generated, context=context)
        except ResponseValidationError:
            logger.info(
                "ask refusal=validation_failed retrieval_seconds=%.3f generation_seconds=%.3f query_chars=%d",
                retrieval_seconds,
                generation_seconds,
                len(stripped_query),
            )
            return self.refusal_handler.build(
                ClassificationResult(
                    QueryIntent.ADVISORY,
                    "Generated answer failed compliance validation",
                    classification.supported_schemes,
                )
            )
        logger.info(
            "ask answer retrieval_seconds=%.3f generation_seconds=%.3f query_chars=%d chunks=%d",
            retrieval_seconds,
            generation_seconds,
            len(stripped_query),
            len(retrieval.chunks),
        )
        return self.formatter.format_answer(validated, retrieval.chunks)

    def _build_performance_link_response(self, scheme: dict[str, Any]) -> AnswerResponse:
        link_only_chunk = CorpusChunk(
            chunk_id=f"{scheme['scheme_slug']}:performance_link",
            scheme_name=str(scheme["scheme_name"]),
            scheme_slug=str(scheme["scheme_slug"]),
            category=str(scheme["category"]),
            field="performance_link",
            content="Performance information is available on the scheme source page.",
            source_url=str(scheme["source_url"]),
            fetched_at=scheme.get("fetched_at"),
        )
        return self.formatter.format_answer(
            "I cannot quote historical return figures. Please refer to the Groww scheme page for performance information.",
            [link_only_chunk],
        )


router = APIRouter()
_ask_service: AskService | None = None


def get_ask_service() -> AskService:
    global _ask_service
    if _ask_service is None:
        _ask_service = AskService()
    return _ask_service


def set_ask_service(service: AskService | None) -> None:
    global _ask_service
    _ask_service = service


@router.post("/api/ask", response_model=AnswerPayload | RefusalPayload)
def ask(request: AskRequest) -> dict[str, Any]:
    started = perf_counter()
    try:
        response = get_ask_service().ask(request.query)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (GroqQuotaExceeded, GroqGenerationError) as exc:
        raise HTTPException(status_code=503, detail="Generation service is temporarily busy. Please try again later.") from exc
    except RetrievalError as exc:
        raise HTTPException(status_code=503, detail="The local vector store is not ready.") from exc
    except ResponseValidationError as exc:
        raise HTTPException(status_code=502, detail="Generated answer failed compliance validation.") from exc

    logger.info(
        "ask route total_seconds=%.3f type=%s query_chars=%d",
        perf_counter() - started,
        response.type,
        len(request.query.strip()),
    )
    return asdict(response)
