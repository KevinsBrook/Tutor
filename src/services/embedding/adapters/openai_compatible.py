# -*- coding: utf-8 -*-
"""OpenAI-compatible embedding adapter for OpenAI, Azure, HuggingFace, LM Studio, etc."""

import asyncio
import logging
import os
from typing import Any, Dict

import httpx

from .base import BaseEmbeddingAdapter, EmbeddingRequest, EmbeddingResponse

logger = logging.getLogger(__name__)


class OpenAICompatibleEmbeddingAdapter(BaseEmbeddingAdapter):
    MODELS_INFO = {
        "text-embedding-3-large": {"default": 3072, "dimensions": [256, 512, 1024, 3072]},
        "text-embedding-3-small": {"default": 1536, "dimensions": [512, 1536]},
        "text-embedding-ada-002": 1536,
    }
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_version:
            headers["api-key"] = self.api_key
        else:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "input": request.texts,
            "model": request.model or self.model,
            "encoding_format": request.encoding_format or "float",
        }

        if request.dimensions or self.dimensions:
            payload["dimensions"] = request.dimensions or self.dimensions

        url = f"{self.base_url.rstrip('/')}/embeddings"
        if self.api_version:
            if "?" not in url:
                url += f"?api-version={self.api_version}"
            else:
                url += f"&api-version={self.api_version}"

        logger.debug(f"Sending embedding request to {url} with {len(request.texts)} texts")

        max_retries = int(os.getenv("EMBEDDING_MAX_RETRIES", "5"))
        retry_base_seconds = float(os.getenv("EMBEDDING_RETRY_BASE_SECONDS", "1.5"))

        async with httpx.AsyncClient(timeout=self.request_timeout) as client:
            data = None
            for attempt in range(max_retries + 1):
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code < 400:
                    data = response.json()
                    break

                logger.error(f"HTTP {response.status_code} response body: {response.text}")

                should_retry = (
                    response.status_code in self.RETRYABLE_STATUS_CODES and attempt < max_retries
                )
                if not should_retry:
                    response.raise_for_status()

                wait_seconds = retry_base_seconds * (2**attempt)
                logger.warning(
                    "Embedding request failed with retryable status %s (attempt %s/%s). "
                    "Retrying in %.1fs",
                    response.status_code,
                    attempt + 1,
                    max_retries + 1,
                    wait_seconds,
                )
                await asyncio.sleep(wait_seconds)

            if data is None:
                raise RuntimeError("Embedding request failed after retries")

        embeddings = [item["embedding"] for item in data["data"]]

        actual_dims = len(embeddings[0]) if embeddings else 0
        expected_dims = request.dimensions or self.dimensions

        if expected_dims and actual_dims != expected_dims:
            logger.warning(
                f"Dimension mismatch: expected {expected_dims}, got {actual_dims}. "
                f"Model '{data['model']}' may not support custom dimensions."
            )

        logger.info(
            f"Successfully generated {len(embeddings)} embeddings "
            f"(model: {data['model']}, dimensions: {actual_dims})"
        )

        return EmbeddingResponse(
            embeddings=embeddings,
            model=data["model"],
            dimensions=actual_dims,
            usage=data.get("usage", {}),
        )

    def get_model_info(self) -> Dict[str, Any]:
        model_info = self.MODELS_INFO.get(self.model, self.dimensions)

        if isinstance(model_info, dict):
            return {
                "model": self.model,
                "dimensions": model_info.get("default", self.dimensions),
                "supported_dimensions": model_info.get("dimensions", []),
                "supports_variable_dimensions": len(model_info.get("dimensions", [])) > 1,
                "provider": "openai_compatible",
            }
        else:
            return {
                "model": self.model,
                "dimensions": model_info or self.dimensions,
                "supports_variable_dimensions": False,
                "provider": "openai_compatible",
            }
