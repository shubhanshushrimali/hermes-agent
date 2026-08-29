"""Unicode and encoding edge-case fixes — Hermes Agent Aizen Version.

Centralizes all encoding workarounds for cross-platform compatibility:

1. **UTF-8 stdio** — Force UTF-8 on Windows console (replaces hermes_bootstrap)
2. **Path encoding** — Handle non-ASCII paths on Windows
3. **JSON encoding** — Safe serialization of mixed-encoding data
4. **Terminal width** — Correct width detection with CJK characters
5. **Environment sanitization** — Strip non-UTF-8 env vars

Import this module early in the startup sequence.
"""

from __future__ import annotations

import codecs
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional, Union


def ensure_utf8_stdio() -> None:
    """Force UTF-8 encoding on stdin/stdout/stderr.

    On Windows, the console defaults to the system codepage (e.g., cp1252),
    which causes UnicodeEncodeError when printing emoji, CJK, or other
    non-ASCII characters. This function wraps the streams with UTF-8
    writers that replace unencodable characters instead of crashing.
    """
    if sys.platform != "win32":
        return

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if stream is None:
            continue
        if hasattr(stream, "encoding") and stream.encoding and stream.encoding.lower() != "utf-8":
            try:
                wrapped = codecs.getwriter("utf-8")(
                    stream.buffer, errors="replace"
                )
                wrapped.encoding = "utf-8"  # type: ignore[attr-defined]
                setattr(sys, stream_name, wrapped)
            except Exception:
                pass

    # Also fix stdin
    if sys.stdin and hasattr(sys.stdin, "encoding"):
        if sys.stdin.encoding and sys.stdin.encoding.lower() != "utf-8":
            try:
                sys.stdin = codecs.getreader("utf-8")(
                    sys.stdin.buffer, errors="replace"
                )
            except Exception:
                pass


def safe_path(path: Union[str, Path]) -> Path:
    """Normalize a path to handle non-ASCII and mixed separators on Windows.

    Returns a Path object with:
    - Forward slashes normalized to OS separator
    - Trailing whitespace stripped
    - UNC path support on Windows
    """
    p = str(path).strip()
    if sys.platform == "win32":
        # Handle UNC paths
        if p.startswith("//") or p.startswith("\\\\"):
            return Path(p)
        # Normalize separators
        p = p.replace("/", "\\")
    return Path(p)


def safe_json_dumps(data: Any, **kwargs) -> str:
    """JSON serialization that handles non-UTF-8 bytes and special floats.

    Falls back to string representation for unencodable objects instead
    of raising TypeError.
    """
    def default_handler(obj):
        if isinstance(obj, bytes):
            try:
                return obj.decode("utf-8")
            except UnicodeDecodeError:
                return obj.decode("latin-1")
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, set):
            return list(obj)
        return str(obj)

    return json.dumps(
        data,
        default=default_handler,
        ensure_ascii=False,
        **kwargs,
    )


def safe_json_loads(text: Union[str, bytes]) -> Any:
    """JSON deserialization that handles BOM and encoding issues."""
    if isinstance(text, bytes):
        # Strip UTF-8 BOM
        if text.startswith(b"\xef\xbb\xbf"):
            text = text[3:]
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError:
            text = text.decode("utf-8", errors="replace")
    return json.loads(text)


def cjk_width(text: str) -> int:
    """Calculate the display width of a string, accounting for CJK characters.

    CJK characters are double-width in monospace terminals. This gives
    the correct terminal column count for strings containing them.
    """
    try:
        import unicodedata
        width = 0
        for char in text:
            eaw = unicodedata.east_asian_width(char)
            if eaw in ("W", "F"):  # Wide, Fullwidth
                width += 2
            elif eaw == "A":  # Ambiguous — treat as single
                width += 1
            else:
                width += 1
        return width
    except Exception:
        return len(text)


def sanitize_env() -> dict:
    """Return a copy of os.environ with non-UTF-8 values replaced.

    Some Windows env vars contain bytes that can't be encoded as UTF-8,
    which breaks subprocess calls with ``env=`` parameter.
    """
    clean = {}
    for key, value in os.environ.items():
        try:
            key.encode("utf-8")
            value.encode("utf-8")
            clean[key] = value
        except (UnicodeEncodeError, UnicodeDecodeError):
            clean[key] = value.encode("utf-8", errors="replace").decode("utf-8")
    return clean


def safe_truncate(text: str, max_length: int, suffix: str = "…") -> str:
    """Truncate a string to max_length, respecting multi-byte character boundaries."""
    if len(text) <= max_length:
        return text
    # Truncate and ensure we don't cut in the middle of a surrogate pair
    truncated = text[: max_length - len(suffix)]
    # Remove trailing surrogates
    while truncated and ord(truncated[-1]) >= 0xD800 and ord(truncated[-1]) <= 0xDFFF:
        truncated = truncated[:-1]
    return truncated + suffix


# Auto-apply UTF-8 fix on import
ensure_utf8_stdio()
