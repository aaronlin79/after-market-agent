"""Thin OpenAI Responses API wrapper for structured cluster summaries."""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from backend.app.core.config import Settings, get_settings

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class OpenAIResponsesClient:
    """Centralized OpenAI client wrapper."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI summarization.")
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise RuntimeError("The openai package is required for OpenAI summarization.") from exc

        timeout_seconds = max(float(self.settings.openai_timeout_seconds), 1.0)
        max_retries = max(int(self.settings.openai_max_retries), 0)
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        logger.info(
            "Initializing OpenAIResponsesClient model=%s has_api_key=%s timeout_seconds=%s max_retries=%s",
            self.settings.openai_model_summary,
            bool(self.settings.openai_api_key),
            self.timeout_seconds,
            self.max_retries,
        )
        self.client = OpenAI(
            api_key=self.settings.openai_api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    def parse_structured_output(
        self,
        *,
        instructions: str,
        input_text: str,
        response_model: type[T],
    ) -> tuple[T, str]:
        """Generate and parse a structured response using the Responses API."""

        logger.info(
            "Submitting OpenAI structured summary request model=%s input_chars=%s",
            self.settings.openai_model_summary,
            len(input_text),
        )
        response = self.client.responses.parse(
            model=self.settings.openai_model_summary,
            input=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": input_text},
            ],
            text_format=response_model,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ValueError("OpenAI returned no parsed structured output.")
        logger.info(
            "OpenAI structured summary request completed model=%s parsed_output=%s",
            self.settings.openai_model_summary,
            response_model.__name__,
        )
        return parsed, self.settings.openai_model_summary
