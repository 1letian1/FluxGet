"""Automatic retry classification and exponential backoff."""

from __future__ import annotations

import httpx


class RetryPolicy:
    RETRYABLE_STATUS = {500, 502, 503, 504}

    @classmethod
    def is_retryable(cls, error: BaseException) -> bool:
        if isinstance(error, (httpx.TimeoutException, httpx.TransportError, ConnectionError, TimeoutError)):
            return True
        return isinstance(error, httpx.HTTPStatusError) and error.response.status_code in cls.RETRYABLE_STATUS

    @staticmethod
    def delay(retry_number: int) -> float:
        return float(min(2 ** max(0, retry_number), 30))
