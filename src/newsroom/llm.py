"""Shared Claude API wrapper with exponential backoff on rate limits."""

import random
import time

import anthropic

MAX_RETRIES = 4
_BASE_DELAY = 2.0


_CALL_TIMEOUT = 60.0


def chat(
    client: anthropic.Anthropic,
    *,
    max_retries: int = MAX_RETRIES,
    **kwargs,
) -> anthropic.types.Message:
    """Call Claude with a timeout, retrying on rate limits and timeouts."""
    kwargs.setdefault("timeout", _CALL_TIMEOUT)
    for attempt in range(max_retries + 1):
        try:
            return client.messages.create(**kwargs)
        except (anthropic.APITimeoutError, anthropic.APIStatusError) as exc:
            if isinstance(exc, anthropic.APIStatusError) and exc.status_code not in (429, 529):
                raise
            if attempt == max_retries:
                raise
            delay = _BASE_DELAY * (2**attempt) + random.uniform(0, 1)
            print(f"     ⚠ Claude retry {attempt + 1}/{max_retries} in {delay:.1f}s ({type(exc).__name__})", flush=True)
            time.sleep(delay)
    raise RuntimeError("unreachable")  # satisfies type checkers
