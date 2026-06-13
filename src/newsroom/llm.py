"""Shared Claude API wrapper with exponential backoff on rate limits."""

import random
import time

import anthropic

MAX_RETRIES = 4
_BASE_DELAY = 2.0


def chat(client: anthropic.Anthropic, **kwargs) -> anthropic.types.Message:
    """Call client.messages.create, retrying on 429/529 with exponential backoff."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            return client.messages.create(**kwargs)
        except anthropic.APIStatusError as exc:
            if exc.status_code not in (429, 529) or attempt == MAX_RETRIES:
                raise
            delay = _BASE_DELAY * (2**attempt) + random.uniform(0, 1)
            time.sleep(delay)
    raise RuntimeError("unreachable")  # satisfies type checkers
