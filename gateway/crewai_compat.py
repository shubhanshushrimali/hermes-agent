"""
CrewAI Python 3.14 Compatibility Shim.

CrewAI 0.11.2 imports `langchain.agents.agent.RunnableAgent` which depends
on `langchain_core.memory.BaseMemory` — removed in langchain-core 0.4+.

This shim patches the import chain so CrewAI loads on Python 3.14 without
downgrading langchain. It:
1. Creates a stub `langchain_core.memory` module if missing
2. Creates a stub `langchain.schema` module if broken
3. Patches `langchain.agents.agent` imports

Import this BEFORE importing crewai:
    import gateway.crewai_compat  # noqa: F401  # patches imports
    from crewai import Agent, Crew, Task, Process
"""

from __future__ import annotations

import importlib
import logging
import sys
import types

logger = logging.getLogger("hermes.crewai_compat")

_patched = False


def _ensure_module(dotted_name: str, attrs: dict = None) -> types.ModuleType:
    """Create a stub module if it doesn't exist in sys.modules."""
    if dotted_name in sys.modules:
        return sys.modules[dotted_name]

    mod = types.ModuleType(dotted_name)
    if attrs:
        for k, v in attrs.items():
            setattr(mod, k, v)
    sys.modules[dotted_name] = mod

    # Ensure parent modules exist too.
    parts = dotted_name.rsplit(".", 1)
    if len(parts) == 2:
        parent_name, child_name = parts
        parent = _ensure_module(parent_name)
        setattr(parent, child_name, mod)

    return mod


def patch_crewai_imports() -> bool:
    """Patch broken import chain for CrewAI on Python 3.14+.

    Returns True if patching was needed and applied.
    """
    global _patched
    if _patched:
        return False

    _patched = True
    patched_anything = False

    # 1. Patch langchain_core.memory (removed in newer langchain-core)
    try:
        from langchain_core import memory  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        logger.debug("Patching langchain_core.memory stub")

        # Create a minimal BaseMemory stub.
        class BaseMemory:
            """Stub BaseMemory for compatibility."""
            pass

        _ensure_module("langchain_core.memory", {
            "BaseMemory": BaseMemory,
        })
        patched_anything = True

    # 2. Patch langchain.schema if broken
    try:
        from langchain.schema import RUN_KEY  # noqa: F401
    except (ImportError, ModuleNotFoundError, AttributeError):
        logger.debug("Patching langchain.schema stub")

        _ensure_module("langchain.schema", {
            "RUN_KEY": "__run",
        })
        patched_anything = True

    # 3. Patch langchain.callbacks.manager if missing StreamManagerMixin
    try:
        from langchain_core.callbacks.manager import BaseRunManager  # noqa: F401
    except (ImportError, AttributeError):
        logger.debug("Patching langchain callbacks stubs")

        class _StubManager:
            pass

        _ensure_module("langchain_core.callbacks", {
            "BaseRunManager": _StubManager,
        })
        patched_anything = True

    # 4. Ensure langchain.tools exists
    try:
        import langchain.tools  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        from typing import Any

        class BaseTool:
            """Stub BaseTool."""
            name: str = ""
            description: str = ""
            def _run(self, *args: Any, **kwargs: Any) -> Any:
                raise NotImplementedError

        _ensure_module("langchain.tools", {
            "BaseTool": BaseTool,
        })
        patched_anything = True

    if patched_anything:
        logger.info("CrewAI compatibility patches applied for Python %s", sys.version.split()[0])

    return patched_anything


# Auto-patch on import.
patch_crewai_imports()
