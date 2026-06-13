"""Shared Claude API wrapper with exponential backoff on rate limits."""

import random
import time

import anthropic

MAX_RETRIES = 4
_BASE_DELAY = 2.0


_CALL_TIMEOUT = 60.0


def chat(client: anthropic.Anthropic, **kwargs) -> anthropic.types.Message:
    """Call client.messages.create with a 60s timeout, retrying on rate limits and timeouts."""
    kwargs.setdefault("timeout", _CALL_TIMEOUT)
    for attempt in range(MAX_RETRIES + 1):
        try:
            return client.messages.create(**kwargs)
        except anthropic.APITimeoutError:
            if attempt == MAX_RETRIES:
                raise
        except anthropic.APIStatusError as exc:
            if exc.status_code not in (429, 529) or attempt == MAX_RETRIES:
                raise
        delay = _BASE_DELAY * (2**attempt) + random.uniform(0, 1)
        time.sleep(delay)
    raise RuntimeError("unreachable")  # satisfies type checkers
