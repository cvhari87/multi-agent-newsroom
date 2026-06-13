from unittest.mock import Mock, patch

import anthropic
import pytest

from newsroom.llm import chat


def _timeout_error() -> anthropic.APITimeoutError:
    return anthropic.APITimeoutError(request=Mock())


def test_chat_honors_per_call_retry_budget() -> None:
    client = Mock()
    client.messages.create.side_effect = [_timeout_error(), _timeout_error()]

    with patch("newsroom.llm.time.sleep"), pytest.raises(anthropic.APITimeoutError):
        chat(client, model="test-model", max_retries=1, timeout=30.0)

    assert client.messages.create.call_count == 2
    assert client.messages.create.call_args.kwargs["timeout"] == 30.0
