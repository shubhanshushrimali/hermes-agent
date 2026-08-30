"""Windows subprocess compatibility helpers for Hermes Agent.

Provides safe subprocess creation on Windows that avoids console window
flashes, handles SIGTERM translation to taskkill, and properly escapes
paths with spaces.

On POSIX systems, all helpers are transparent pass-throughs.

Usage:
    from gateway.windows_compat import safe_subprocess_args, safe_kill

    proc = subprocess.Popen(cmd, **safe_subprocess_args())
    safe_kill(proc.pid)
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

# ---------------------------------------------------------------------------
# Windows-specific constants (defined conditionally to avoid import errors)
# ---------------------------------------------------------------------------

if IS_WINDOWS:
    import ctypes

    # https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008

    # STARTUPINFO flags
    _STARTF_USESHOWWINDOW = 0x00000001
    _SW_HIDE = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def safe_subprocess_args(
    *,
    hide_window: bool = True,
    detached: bool = False,
) -> Dict[str, Any]:
    """Return kwargs for subprocess.Popen/run that suppress console windows.

    On POSIX, returns an empty dict (no-op).
    On Windows, sets ``creationflags`` and ``startupinfo`` to prevent
    a visible console window from flashing during subprocess creation.

    Parameters
    ----------
    hide_window
        When True (default), sets CREATE_NO_WINDOW and STARTF_USESHOWWINDOW.
    detached
        When True, also sets DETACHED_PROCESS so the child survives parent exit.
    """
    if not IS_WINDOWS:
        return {}

    kwargs: Dict[str, Any] = {}

    flags = 0
    if hide_window:
        flags |= CREATE_NO_WINDOW
    if detached:
        flags |= DETACHED_PROCESS

    if flags:
        kwargs["creationflags"] = flags

    if hide_window:
        si = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        si.dwFlags |= _STARTF_USESHOWWINDOW
        si.wShowWindow = _SW_HIDE
        kwargs["startupinfo"] = si

    return kwargs


def safe_kill(pid: int, *, force: bool = False, tree: bool = True) -> bool:
    """Kill a process safely across platforms.

    On Windows, uses ``taskkill`` because:
    - Windows has no SIGTERM; ``os.kill(pid, signal.SIGTERM)`` maps to
      TerminateProcess which is equivalent to SIGKILL (no cleanup).
    - ``taskkill /T`` kills the entire process tree, which is usually
      what we want for shell commands that spawn children.

    On POSIX, sends SIGTERM (or SIGKILL if force=True).

    Returns True if the kill command succeeded (or process was already dead).
    """
    if not IS_WINDOWS:
        sig = signal.SIGKILL if force else signal.SIGTERM
        try:
            os.kill(pid, sig)
            return True
        except ProcessLookupError:
            return True  # already dead
        except OSError as exc:
            logger.warning("Failed to kill PID %d: %s", pid, exc)
            return False

    # Windows: use taskkill
    args = ["taskkill"]
    if force:
        args.append("/F")
    if tree:
        args.append("/T")
    args.extend(["/PID", str(pid)])

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=10,
            **safe_subprocess_args(),
        )
        if result.returncode == 0:
            return True
        # Return code 128 = process not found (already dead)
        if result.returncode == 128 or "not found" in result.stderr.lower():
            return True
        logger.warning(
            "taskkill PID %d returned %d: %s",
            pid,
            result.returncode,
            result.stderr.strip(),
        )
        return False
    except Exception as exc:
        logger.warning("taskkill PID %d failed: %s", pid, exc)
        return False


def safe_shell_command(cmd: str) -> List[str]:
    """Wrap a shell command string for safe execution on Windows.

    On Windows, wraps with ``cmd.exe /c`` to handle paths with spaces
    and special characters properly.

    On POSIX, returns ``['sh', '-c', cmd]``.
    """
    if IS_WINDOWS:
        return ["cmd.exe", "/c", cmd]
    return ["sh", "-c", cmd]


def escape_windows_path(path: str) -> str:
    """Quote a path for Windows if it contains spaces or special chars.

    On POSIX, returns the path unchanged.
    """
    if not IS_WINDOWS:
        return path
    # Already quoted
    if path.startswith('"') and path.endswith('"'):
        return path
    # Needs quoting
    if " " in path or "&" in path or "(" in path or ")" in path:
        return f'"{path}"'
    return path


def ensure_utf8_env(env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return an environment dict with UTF-8 encoding forced.

    On Windows, sets:
    - PYTHONIOENCODING=utf-8
    - Ensures the console code page is UTF-8 (65001) via environment

    On POSIX, ensures LANG and LC_ALL include UTF-8.
    """
    result = dict(env) if env else dict(os.environ)

    result["PYTHONIOENCODING"] = "utf-8"

    if IS_WINDOWS:
        # chcp 65001 equivalent via environment
        result.setdefault("PYTHONLEGACYWINDOWSSTDIO", "0")
    else:
        # Ensure UTF-8 locale on POSIX
        for key in ("LANG", "LC_ALL"):
            val = result.get(key, "")
            if val and "utf" not in val.lower():
                result[key] = "en_US.UTF-8"

    return result


def safe_popen(
    cmd: Union[str, List[str]],
    *,
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[str] = None,
    capture_output: bool = True,
    text: bool = True,
    timeout: Optional[float] = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """Run a subprocess with all Windows safety guards applied.

    Combines safe_subprocess_args, ensure_utf8_env, and proper
    encoding settings into a single call.
    """
    safe_env = ensure_utf8_env(env)
    safe_kwargs = safe_subprocess_args()
    safe_kwargs.update(kwargs)

    if isinstance(cmd, str):
        cmd = safe_shell_command(cmd)

    return subprocess.run(
        cmd,
        env=safe_env,
        cwd=cwd,
        capture_output=capture_output,
        text=text,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        **safe_kwargs,
    )
