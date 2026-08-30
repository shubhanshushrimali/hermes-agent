"""Encoding guard utilities for Hermes Agent.

Safe decode/encode helpers that handle the messy reality of text encoding
across platforms, filesystems, and network boundaries. Prevents crashes
from malformed UTF-8, mixed encodings, and platform-specific filename
restrictions.

Usage:
    from gateway.encoding_guard import safe_decode, safe_encode, sanitize_filename

    text = safe_decode(raw_bytes)
    clean_name = sanitize_filename(user_input)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import unicodedata
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

# Characters illegal in filenames on Windows.
_WINDOWS_ILLEGAL_CHARS = frozenset('<>:"/\\|?*')

# Control characters (0x00-0x1F) plus DEL (0x7F).
_CONTROL_CHARS = frozenset(chr(i) for i in range(0x20)) | {chr(0x7F)}

# Windows reserved device names (case-insensitive).
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


# ---------------------------------------------------------------------------
# Decode / Encode
# ---------------------------------------------------------------------------


def safe_decode(
    data: Union[bytes, str],
    encoding: str = "utf-8",
    fallback: str = "latin-1",
) -> str:
    """Decode bytes to str, never raising on malformed input.

    Strategy:
    1. Try the requested encoding (default UTF-8).
    2. If that fails, try with ``errors='replace'`` to substitute
       un-decodable bytes with U+FFFD.
    3. If *that* somehow fails, fall back to latin-1 (which never
       raises because every byte maps to a codepoint).

    Already-decoded strings are returned unchanged.
    """
    if isinstance(data, str):
        return data

    try:
        return data.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        pass

    try:
        return data.decode(encoding, errors="replace")
    except (UnicodeDecodeError, LookupError):
        pass

    # latin-1 is a 1:1 byte→codepoint mapping — never fails.
    return data.decode(fallback, errors="replace")


def safe_encode(
    text: str,
    encoding: str = "utf-8",
    errors: str = "surrogateescape",
) -> bytes:
    """Encode str to bytes, using surrogateescape to round-trip OS paths.

    ``surrogateescape`` preserves bytes that couldn't be decoded during
    filename enumeration (common on Linux with mixed-encoding filenames)
    and writes them back as the original bytes.
    """
    try:
        return text.encode(encoding, errors=errors)
    except (UnicodeEncodeError, LookupError):
        return text.encode(encoding, errors="replace")


# ---------------------------------------------------------------------------
# Filename sanitization
# ---------------------------------------------------------------------------


def sanitize_filename(
    name: str,
    *,
    replacement: str = "_",
    max_length: int = 255,
    allow_dotfiles: bool = True,
) -> str:
    """Sanitize a string for use as a filename on any platform.

    - Removes control characters
    - Removes characters illegal on Windows (< > : " / \\ | ? *)
    - Strips leading/trailing whitespace and dots (Windows restriction)
    - Replaces Windows reserved names (CON, PRN, etc.)
    - Truncates to max_length (default 255, the common FS limit)
    - Normalizes Unicode to NFC form
    """
    if not name:
        return replacement or "unnamed"

    # Normalize Unicode (NFC = composed form, most compatible).
    name = unicodedata.normalize("NFC", name)

    # Remove control characters.
    name = "".join(c if c not in _CONTROL_CHARS else replacement for c in name)

    # Remove characters illegal on Windows (applied on all platforms
    # for maximum portability of generated filenames).
    name = "".join(c if c not in _WINDOWS_ILLEGAL_CHARS else replacement for c in name)

    # Collapse multiple consecutive replacements.
    if replacement:
        pattern = re.escape(replacement) + "+"
        name = re.sub(pattern, replacement, name)

    # Strip leading/trailing whitespace and dots.
    name = name.strip(". \t\n\r")

    # Check for Windows reserved names.
    stem = name.split(".")[0].upper()
    if stem in _WINDOWS_RESERVED:
        name = f"{replacement}{name}"

    # Truncate to max_length (preserve extension if possible).
    if len(name) > max_length:
        dot_idx = name.rfind(".")
        if dot_idx > 0:
            ext = name[dot_idx:]
            base_max = max_length - len(ext)
            if base_max > 0:
                name = name[:base_max] + ext
            else:
                name = name[:max_length]
        else:
            name = name[:max_length]

    # Handle dotfiles.
    if not allow_dotfiles and name.startswith("."):
        name = replacement + name[1:]

    return name or replacement or "unnamed"


# ---------------------------------------------------------------------------
# Line ending normalization
# ---------------------------------------------------------------------------


def normalize_line_endings(text: str, target: str = "\n") -> str:
    """Normalize all line endings to the target (default LF).

    Handles: CRLF (\\r\\n), CR (\\r), and mixed.
    """
    # First replace CRLF, then standalone CR.
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    if target != "\n":
        text = text.replace("\n", target)
    return text


# ---------------------------------------------------------------------------
# Safe JSON serialization
# ---------------------------------------------------------------------------


def safe_json_dumps(
    obj: Any,
    *,
    ensure_ascii: bool = False,
    indent: Optional[int] = None,
    default: Any = None,
) -> str:
    """JSON-serialize with safe handling of non-serializable types.

    Unlike ``json.dumps``, this never raises on:
    - ``bytes`` values (decoded to UTF-8 with replacement)
    - ``set`` values (converted to sorted list)
    - Arbitrary objects (converted to ``str(obj)``)
    - Non-BMP Unicode characters (preserved, not escaped)
    """

    def _safe_default(o: Any) -> Any:
        if default is not None:
            try:
                return default(o)
            except TypeError:
                pass
        if isinstance(o, bytes):
            return safe_decode(o)
        if isinstance(o, set):
            try:
                return sorted(o)
            except TypeError:
                return list(o)
        if isinstance(o, Exception):
            return f"{type(o).__name__}: {o}"
        # Last resort — str representation.
        return str(o)

    return json.dumps(
        obj,
        ensure_ascii=ensure_ascii,
        indent=indent,
        default=_safe_default,
    )


# ---------------------------------------------------------------------------
# Console encoding helpers
# ---------------------------------------------------------------------------


def get_safe_console_encoding() -> str:
    """Return a console encoding that supports Unicode.

    On Windows with legacy code pages (cp932, cp1252, etc.), returns
    'utf-8' so callers can set it explicitly. On modern terminals and
    POSIX systems, returns the detected encoding.
    """
    encoding = sys.stdout.encoding or sys.getdefaultencoding()

    # Known-safe encodings.
    safe = encoding.lower().replace("-", "").replace("_", "")
    if safe in ("utf8", "utf16", "utf32", "utf8sig"):
        return encoding

    # Legacy Windows code page — recommend UTF-8.
    if IS_WINDOWS:
        return "utf-8"

    return encoding


def set_windows_utf8_console() -> None:
    """Set the Windows console to UTF-8 mode (code page 65001).

    No-op on non-Windows platforms. Safe to call multiple times.
    """
    if not IS_WINDOWS:
        return

    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception as exc:
        logger.debug("Failed to set Windows console to UTF-8: %s", exc)
