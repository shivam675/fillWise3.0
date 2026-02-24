"""
Ollama HTTP client with circuit breaker and retry logic.

All communication with Ollama is over localhost HTTP.
No external network calls are made.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx
from ollama import AsyncClient, RequestError, ResponseError
import structlog

from app.config.settings import get_settings
from app.core.errors import ErrorCode, ServiceUnavailableError

_log = structlog.get_logger(__name__)


# ── Circuit Breaker ───────────────────────────────────────────────────── #


class CircuitState(StrEnum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing; reject calls immediately
    HALF_OPEN = "half_open" # Probe state; allow one call


@dataclass
class CircuitBreaker:
    """
    Simple time-based circuit breaker.

    States:
      CLOSED   → normal; failures increment counter.
      OPEN     → rejects all calls; transitions to HALF_OPEN after timeout.
      HALF_OPEN→ allows one test call; success → CLOSED, failure → OPEN.
    """

    threshold: int
    timeout_seconds: int
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.timeout_seconds:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.threshold:
            self._state = CircuitState.OPEN
            _log.warning(
                "circuit_opened",
                failures=self._failure_count,
                threshold=self.threshold,
            )

    def allow_request(self) -> bool:
        return self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)


# ── Response dataclass ────────────────────────────────────────────────── #


@dataclass
class OllamaResponse:
    content: str
    model: str
    prompt_eval_count: int
    eval_count: int
    done: bool


# ── Client ────────────────────────────────────────────────────────────── #


class OllamaClient:
    """
    Async Ollama API client.

    Only exposes two operations:
      - stream_completion: yields tokens for live streaming.
      - complete: returns full response.

    Both respect the circuit breaker and retry policy.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._circuit = CircuitBreaker(
            threshold=self._settings.ollama_circuit_breaker_threshold,
            timeout_seconds=self._settings.ollama_circuit_breaker_timeout_seconds,
        )
        self._base_url = str(self._settings.ollama_base_url).rstrip("/")
        self._client = AsyncClient(host=self._base_url)
        self._resolved_model: str | None = None

    def _make_payload(self, system: str, user: str, stream: bool) -> dict[str, Any]:
        return {
            "model": self._settings.ollama_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": stream,
            "options": {
                "temperature": self._settings.rewrite_temperature,
                "num_predict": self._settings.chunk_max_tokens,
            },
        }

    @staticmethod
    def _compose_generate_prompt(system_prompt: str, user_prompt: str) -> str:
        return f"System:\n{system_prompt}\n\nUser:\n{user_prompt}\n\nAssistant:\n"

    @staticmethod
    def _extract_chat_content(chat_response: Any) -> str:
        message = getattr(chat_response, "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(chat_response, dict):
            return str(chat_response.get("message", {}).get("content", ""))
        return ""

    async def _v1_chat_completion(self, system_prompt: str, user_prompt: str) -> str:
        model_name = await self._resolve_model_name()
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "temperature": self._settings.rewrite_temperature,
            "max_tokens": self._settings.chunk_max_tokens,
        }
        async with httpx.AsyncClient(timeout=self._settings.ollama_timeout_seconds) as client:
            resp = await client.post(f"{self._base_url}/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                return ""
            return str(choices[0].get("message", {}).get("content", ""))

    async def _resolve_model_name(self) -> str:
        if self._resolved_model:
            return self._resolved_model

        configured = self._settings.ollama_model
        try:
            list_response = await self._client.list()
            models = [m.model for m in getattr(list_response, "models", [])]
            if configured in models:
                self._resolved_model = configured
                return configured

            configured_base = configured.split(":")[0].lower()
            candidates = [m for m in models if configured_base in m.lower()]
            if candidates:
                best = sorted(candidates, key=len)[0]
                self._resolved_model = best
                _log.info("ollama_model_resolved", configured=configured, resolved=best)
                return best
        except Exception:
            pass

        self._resolved_model = configured
        return configured

    async def health_check(self) -> bool:
        """Return True if Ollama is reachable, model exists, and a generation endpoint is usable."""
        try:
            list_response = await self._client.list()
            models = [m.model for m in getattr(list_response, "models", [])]
            model_base = self._settings.ollama_model.split(":")[0]
            model_available = any(model_base in m for m in models)
            if not model_available:
                return False

            model_name = await self._resolve_model_name()

            try:
                await self._client.chat(
                    model=model_name,
                    messages=[{"role": "user", "content": "ping"}],
                    stream=False,
                    options={"num_predict": 1, "temperature": 0},
                )
                return True
            except ResponseError as exc:
                if getattr(exc, "status_code", None) == 404:
                    try:
                        await self._v1_chat_completion("You are concise.", "ping")
                        return True
                    except Exception:
                        return False
                return False
        except Exception:
            return False

    async def stream_completion(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[str]:
        """
        Stream tokens from Ollama.

        Yields:
            Individual token strings as they arrive.

        Raises:
            ServiceUnavailableError: If circuit is open or all retries fail.
        """
        if not self._circuit.allow_request():
            raise ServiceUnavailableError(
                ErrorCode.JOB_CIRCUIT_OPEN,
                "Ollama circuit breaker is open. Please wait before retrying.",
            )

        max_retries = self._settings.ollama_max_retries
        model_name = await self._resolve_model_name()

        for attempt in range(1, max_retries + 2):
            try:
                stream = await self._client.chat(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    stream=True,
                    options={
                        "temperature": self._settings.rewrite_temperature,
                        "num_predict": self._settings.chunk_max_tokens,
                    },
                )
                async for chunk in stream:
                    token = self._extract_chat_content(chunk)
                    if token:
                        yield token
                self._circuit.record_success()
                return
            except ResponseError as exc:
                if getattr(exc, "status_code", None) == 404:
                    _log.warning("ollama_chat_endpoint_missing_fallback_v1")
                    try:
                        text = await self._v1_chat_completion(system_prompt, user_prompt)
                        if text:
                            yield text
                        self._circuit.record_success()
                        return
                    except Exception as fallback_exc:
                        self._circuit.record_failure()
                        _log.warning(
                            "ollama_v1_fallback_failed",
                            attempt=attempt,
                            max_retries=max_retries,
                            error=str(fallback_exc),
                        )
                        if attempt > max_retries:
                            raise ServiceUnavailableError(
                                ErrorCode.JOB_OLLAMA_UNAVAILABLE,
                                f"Ollama unreachable after {max_retries} retries: {fallback_exc}",
                            ) from fallback_exc
                        await asyncio.sleep(2 ** (attempt - 1))
                        continue

                self._circuit.record_failure()
                _log.warning(
                    "ollama_request_failed",
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(exc),
                )
                if attempt > max_retries:
                    raise ServiceUnavailableError(
                        ErrorCode.JOB_OLLAMA_UNAVAILABLE,
                        f"Ollama unreachable after {max_retries} retries: {exc}",
                    ) from exc
                await asyncio.sleep(2 ** (attempt - 1))
            except (RequestError, httpx.HTTPError, httpx.TimeoutException) as exc:
                self._circuit.record_failure()
                _log.warning(
                    "ollama_request_failed",
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(exc),
                )
                if attempt > max_retries:
                    raise ServiceUnavailableError(
                        ErrorCode.JOB_OLLAMA_UNAVAILABLE,
                        f"Ollama unreachable after {max_retries} retries: {exc}",
                    ) from exc
                # Exponential back-off: 1s, 2s, 4s
                await asyncio.sleep(2 ** (attempt - 1))

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> OllamaResponse:
        """
        Non-streaming Ollama completion.

        Returns the full response after the model finishes.
        """
        if not self._circuit.allow_request():
            raise ServiceUnavailableError(
                ErrorCode.JOB_CIRCUIT_OPEN,
                "Ollama circuit breaker is open.",
            )

        max_retries = self._settings.ollama_max_retries
        model_name = await self._resolve_model_name()

        for attempt in range(1, max_retries + 2):
            try:
                response = await self._client.chat(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    stream=False,
                    options={
                        "temperature": self._settings.rewrite_temperature,
                        "num_predict": self._settings.chunk_max_tokens,
                    },
                )
                self._circuit.record_success()
                return OllamaResponse(
                    content=self._extract_chat_content(response),
                    model=getattr(response, "model", ""),
                    prompt_eval_count=getattr(response, "prompt_eval_count", 0),
                    eval_count=getattr(response, "eval_count", 0),
                    done=getattr(response, "done", True),
                )
            except ResponseError as exc:
                if getattr(exc, "status_code", None) == 404:
                    _log.warning("ollama_chat_endpoint_missing_fallback_v1")
                    try:
                        content = await self._v1_chat_completion(system_prompt, user_prompt)
                        self._circuit.record_success()
                        return OllamaResponse(
                            content=content,
                            model=model_name,
                            prompt_eval_count=0,
                            eval_count=0,
                            done=True,
                        )
                    except Exception as fallback_exc:
                        self._circuit.record_failure()
                        _log.warning(
                            "ollama_v1_fallback_failed",
                            attempt=attempt,
                            error=str(fallback_exc),
                        )
                        if attempt > max_retries:
                            raise ServiceUnavailableError(
                                ErrorCode.JOB_OLLAMA_UNAVAILABLE,
                                f"Ollama unreachable: {fallback_exc}",
                            ) from fallback_exc
                        await asyncio.sleep(2 ** (attempt - 1))
                        continue

                self._circuit.record_failure()
                _log.warning(
                    "ollama_complete_failed",
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt > max_retries:
                    raise ServiceUnavailableError(
                        ErrorCode.JOB_OLLAMA_UNAVAILABLE,
                        f"Ollama unreachable: {exc}",
                    ) from exc
                await asyncio.sleep(2 ** (attempt - 1))
            except (RequestError, httpx.HTTPError, httpx.TimeoutException) as exc:
                self._circuit.record_failure()
                _log.warning(
                    "ollama_complete_failed",
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt > max_retries:
                    raise ServiceUnavailableError(
                        ErrorCode.JOB_OLLAMA_UNAVAILABLE,
                        f"Ollama unreachable: {exc}",
                    ) from exc
                await asyncio.sleep(2 ** (attempt - 1))

        raise ServiceUnavailableError(  # unreachable, satisfies type checker
            ErrorCode.JOB_OLLAMA_UNAVAILABLE, "Exhausted retries"
        )
