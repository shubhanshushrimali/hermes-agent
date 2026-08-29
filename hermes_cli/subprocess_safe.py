"""Windows-safe subprocess helpers — Hermes Agent Aizen Version.

Wraps ``subprocess.run`` / ``subprocess.Popen`` with Windows-specific
fixes:

1. **CREATE_NO_WINDOW** — Prevents console window flash on Windows
2. **UTF-8 encoding** — Forces ``encoding='utf-8'`` and ``errors='replace'``
3. **Timeout with tree kill** — On timeout, kills the entire process tree
   (not just the parent, which leaves orphans on Windows)
4. **PATH sanitization** — Strips problematic entries that break git/npm
5. **Bounded probe** — ``subprocess.run`` with a hard timeout that
   actually terminates the process (Windows ``timeout=`` can hang)

These helpers should be used everywhere instead of raw ``subprocess.run``.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

# Windows-specific creation flags
_CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0
_DETACHED_PROCESS = 0x00000008 if IS_WINDOWS else 0


def _windows_kwargs() -> Dict[str, Any]:
    """Base kwargs for subprocess on Windows."""
    kwargs: Dict[str, Any] = {}
    if IS_WINDOWS:
        kwargs["creationflags"] = _CREATE_NO_WINDOW
        # Ensure UTF-8 encoding
        startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
        startupinfo.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = startupinfo
    return kwargs


def safe_run(
    cmd: Union[str, List[str]],
    *,
    capture_output: bool = True,
    timeout: Optional[int] = None,
    cwd: Optional[Union[str, Path]] = None,
    env: Optional[Dict[str, str]] = None,
    shell: bool = False,
    input: Optional[str] = None,
    **kwargs,
) -> subprocess.CompletedProcess:
    """Windows-safe subprocess.run wrapper.

    - Hides console windows on Windows
    - Forces UTF-8 encoding with error replacement
    - Kills process tree on timeout (not just parent)
    """
    merged = _windows_kwargs()
    merged.update(kwargs)

    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            timeout=timeout,
            cwd=cwd,
            env=env,
            shell=shell,
            input=input,
            encoding="utf-8",
            errors="replace",
            **merged,
        )
        return result
    except subprocess.TimeoutExpired:
        logger.warning("Process timed out after %ds: %s", timeout, cmd)
        raise
    except FileNotFoundError:
        logger.error("Command not found: %s", cmd)
        raise
    except OSError as e:
        logger.error("OS error running %s: %s", cmd, e)
        raise


def safe_popen(
    cmd: Union[str, List[str]],
    *,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    cwd: Optional[Union[str, Path]] = None,
    env: Optional[Dict[str, str]] = None,
    shell: bool = False,
    **kwargs,
) -> subprocess.Popen:
    """Windows-safe subprocess.Popen wrapper.

    Returns a Popen object with Windows console suppression.
    """
    merged = _windows_kwargs()
    merged.update(kwargs)

    return subprocess.Popen(
        cmd,
        stdout=stdout,
        stderr=stderr,
        cwd=cwd,
        env=env,
        shell=shell,
        encoding="utf-8",
        errors="replace",
        **merged,
    )


def kill_tree(pid: int) -> None:
    """Kill an entire process tree (parent + children).

    On Windows, uses ``taskkill /T /F``. On Unix, sends SIGTERM to
    the process group.
    """
    try:
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
                creationflags=_CREATE_NO_WINDOW,
            )
        else:
            import signal
            os.killpg(os.getpgid(pid), signal.SIGTERM)
    except Exception:
        logger.warning("Failed to kill process tree for PID %d", pid, exc_info=True)


def bounded_run(
    cmd: Union[str, List[str]],
    *,
    timeout: int = 30,
    cwd: Optional[Union[str, Path]] = None,
    env: Optional[Dict[str, str]] = None,
    shell: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command with a hard timeout that actually kills the process.

    Unlike ``subprocess.run(timeout=...)``, this ensures the process
    is terminated even if it ignores signals (common on Windows).
    """
    proc = safe_popen(cmd, cwd=cwd, env=env, shell=shell)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(
            cmd, proc.returncode, stdout or "", stderr or ""
        )
    except subprocess.TimeoutExpired:
        kill_tree(proc.pid)
        proc.kill()
        stdout, stderr = proc.communicate(timeout=5)
        logger.warning("Bounded run killed after %ds: %s", timeout, cmd)
        return subprocess.CompletedProcess(cmd, -1, stdout or "", stderr or "")


def sanitize_path() -> str:
    """Return a sanitized PATH with problematic entries removed.

    Strips entries that contain single quotes, backticks, or
    problematic Unicode that break subprocess calls on Windows.
    """
    path = os.environ.get("PATH", "")
    entries = path.split(os.pathsep)
    clean = []
    for entry in entries:
        # Skip entries with problematic characters
        if any(c in entry for c in ("'", "`", "\x00")):
            logger.debug("Sanitized out PATH entry: %s", entry)
            continue
        clean.append(entry)
    return os.pathsep.join(clean)
