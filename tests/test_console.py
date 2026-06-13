import io

from newsroom.console import configure_console


def test_configure_console_prevents_legacy_encoding_errors() -> None:
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")

    configure_console(stream)
    stream.write("batch size <= 6; original symbol: \u2264")
    stream.flush()

    assert b"original symbol: \\u2264" in buffer.getvalue()
