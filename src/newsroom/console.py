"""Console setup that keeps logging from crashing pipeline runs."""

import sys
from typing import TextIO


def configure_console(*streams: TextIO) -> None:
    """Replace unencodable log characters instead of raising UnicodeEncodeError."""
    targets = streams or (sys.stdout, sys.stderr)
    for stream in targets:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")
