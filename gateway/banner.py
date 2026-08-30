"""
Zanpakutō Banner — ASCII art and themed CLI output for Hermes Agent.

Displays the Aizen-themed banner on startup, with version info,
active integrations, and motivational quotes.

Usage:
    from gateway.banner import print_banner
    print_banner()  # Prints to stderr (won't pollute JSON output)
"""

from __future__ import annotations

import logging
import os
import random
import sys
from datetime import datetime

logger = logging.getLogger("hermes.banner")

# ANSI color codes
GOLD = "\033[38;2;212;164;71m"      # #D4A447 — Zanpakutō gold
DIM_GOLD = "\033[38;2;160;130;60m"  # Muted gold
PURPLE = "\033[38;2;124;107;240m"   # #7C6BF0 — Kyōka Suigetsu
TEAL = "\033[38;2;34;211;238m"      # #22D3EE — Hogyoku
DIM = "\033[38;2;100;100;110m"      # Muted gray
WHITE = "\033[38;2;232;230;227m"    # #E8E6E3
RED = "\033[38;2;239;68;68m"        # #EF4444
GREEN = "\033[38;2;34;197;94m"      # #22C55E
BOLD = "\033[1m"
RESET = "\033[0m"

# ============================================================================
# ASCII Art
# ============================================================================

BANNER_ART = f"""
{GOLD}    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║{BOLD}     ██╗  ██╗███████╗██████╗ ███╗   ███╗███████╗███████╗   {RESET}{GOLD}║
    ║{BOLD}     ██║  ██║██╔════╝██╔══██╗████╗ ████║██╔════╝██╔════╝   {RESET}{GOLD}║
    ║{BOLD}     ███████║█████╗  ██████╔╝██╔████╔██║█████╗  ███████╗   {RESET}{GOLD}║
    ║{BOLD}     ██╔══██║██╔══╝  ██╔══██╗██║╚██╔╝██║██╔══╝  ╚════██║  {RESET}{GOLD}║
    ║{BOLD}     ██║  ██║███████╗██║  ██║██║ ╚═╝ ██║███████╗███████║   {RESET}{GOLD}║
    ║{BOLD}     ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚══════╝   {RESET}{GOLD}║
    ║                                                           ║
    ║  {PURPLE}  ▄▀▀▀▄  ▀ ▀▄▄▀ ▀▀▀▄ ▄▀▀▀ ▄▀▀▀▄  Agent  ▄▀▀▀▄        {RESET}{GOLD}║
    ║  {PURPLE}  █▀▀▀█  █  ▄▀█ █▀▀▀ █  █ █   █  v1.0   ▀▄  █        {RESET}{GOLD}║
    ║  {PURPLE}  ▀   ▀  ▀▄▀  ▀ ▀▀▀▀ ▀  ▀ ▀▀▀▀▀         ▀▀▀▀        {RESET}{GOLD}║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝{RESET}
"""

BANNER_COMPACT = f"""{GOLD}
    ╭──────────────────────────────────────────╮
    │  {BOLD}H E R M E S{RESET}{GOLD}  ×  {PURPLE}A I Z E N{RESET}{GOLD}              │
    │  {DIM_GOLD}Zanpakutō Agent Framework{RESET}{GOLD}               │
    ╰──────────────────────────────────────────╯{RESET}
"""

BANNER_MINIMAL = f"{GOLD}⚔{RESET}  {BOLD}Hermes × Aizen{RESET}  {DIM}v1.0{RESET}"

# ============================================================================
# Aizen Quotes (Bleach)
# ============================================================================

QUOTES = [
    "Since when were you under the impression that you were not already using Aizen?",
    "Admiration is the emotion furthest from understanding.",
    "No one stands on the top of the world. Not you. Not me. Not even code.",
    "Fear is necessary for evolution.",
    "Laws exist only for those who cannot live without clinging to them.",
    "All creatures want to believe in something bigger than themselves.",
    "The betrayal you can see is trivial. What is truly frightening is the betrayal you don't see.",
    "Do not call it complicated. That is merely the excuse of the unimaginative.",
    "I alone do not carry sin. If there is a god who rules this world, he is not one I want to trust.",
    "Kyōka Suigetsu's complete hypnosis... has already begun.",
    "I will stand in heaven and put an end to the unbearable vacancy on the throne.",
    "No matter what may happen, as long as you are here, I will always be watching.",
]


def _get_quote() -> str:
    """Get a random Aizen quote."""
    return random.choice(QUOTES)


# ============================================================================
# Status Helpers
# ============================================================================

def _check_integration(name: str, check_fn) -> tuple[str, bool]:
    """Check if an integration is available."""
    try:
        result = check_fn()
        return (name, bool(result))
    except Exception:
        return (name, False)


def _get_integrations() -> list[tuple[str, bool]]:
    """Check all integrations."""
    integrations = []

    # Graph Engine
    try:
        from gateway.graph_engine import classify_intent_local
        integrations.append(("Graph Engine", True))
    except Exception:
        integrations.append(("Graph Engine", False))

    # Smart Context
    try:
        from gateway.smart_context import SmartContextBuilder
        integrations.append(("Smart Context", True))
    except Exception:
        integrations.append(("Smart Context", False))

    # CrewAI
    try:
        from gateway.crew_engine import CREWAI_AVAILABLE
        integrations.append(("CrewAI", CREWAI_AVAILABLE))
    except Exception:
        integrations.append(("CrewAI", False))

    # Daemon
    try:
        from gateway.daemon_runner import DaemonRunner
        integrations.append(("Daemon", True))
    except Exception:
        integrations.append(("Daemon", False))

    # Langfuse
    langfuse_key = os.environ.get("LANGFUSE_SECRET_KEY", "")
    integrations.append(("Langfuse", bool(langfuse_key)))

    # LiteLLM
    try:
        import litellm
        integrations.append(("LiteLLM", True))
    except Exception:
        integrations.append(("LiteLLM", False))

    # Response Cache
    try:
        from gateway.perf import ResponseCache
        integrations.append(("Cache", True))
    except Exception:
        integrations.append(("Cache", False))

    return integrations


# ============================================================================
# Banner Printer
# ============================================================================

def print_banner(
    compact: bool = False,
    minimal: bool = False,
    show_integrations: bool = True,
    show_quote: bool = True,
    file=None,
) -> None:
    """Print the Hermes × Aizen banner.

    Args:
        compact: Use compact banner (no big ASCII art)
        minimal: One-line banner only
        show_integrations: Show integration status checklist
        show_quote: Show random Aizen quote
        file: Output file (default: stderr)
    """
    out = file or sys.stderr

    # Check if terminal supports ANSI colors.
    if not hasattr(out, 'isatty') or not out.isatty():
        # No colors for piped output.
        _print_plain(out, compact, minimal, show_integrations, show_quote)
        return

    if minimal:
        print(BANNER_MINIMAL, file=out)
        return

    if compact:
        print(BANNER_COMPACT, file=out)
    else:
        print(BANNER_ART, file=out)

    # Integrations status line.
    if show_integrations:
        integrations = _get_integrations()
        parts = []
        for name, ok in integrations:
            icon = f"{GREEN}●{RESET}" if ok else f"{RED}○{RESET}"
            parts.append(f"  {icon} {DIM}{name}{RESET}")

        print(f"    {DIM}{'─' * 46}{RESET}", file=out)
        # Print in 2 columns.
        for i in range(0, len(parts), 2):
            left = parts[i]
            right = parts[i + 1] if i + 1 < len(parts) else ""
            print(f"  {left:45s}{right}", file=out)
        print(file=out)

    # Quote.
    if show_quote:
        quote = _get_quote()
        print(f"    {DIM}「{RESET}{DIM_GOLD}{quote}{RESET}{DIM}」{RESET}", file=out)
        print(file=out)

    # Timestamp.
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"    {DIM}{now}{RESET}", file=out)
    print(file=out)


def _print_plain(out, compact, minimal, show_integrations, show_quote):
    """Print banner without ANSI colors."""
    if minimal:
        print("⚔  Hermes × Aizen  v1.0", file=out)
        return

    print(file=out)
    print("  ╭──────────────────────────────────────────╮", file=out)
    print("  │  H E R M E S  ×  A I Z E N              │", file=out)
    print("  │  Zanpakutō Agent Framework               │", file=out)
    print("  ╰──────────────────────────────────────────╯", file=out)
    print(file=out)

    if show_integrations:
        try:
            integrations = _get_integrations()
            for name, ok in integrations:
                icon = "[+]" if ok else "[ ]"
                print(f"  {icon} {name}", file=out)
            print(file=out)
        except Exception:
            pass

    if show_quote:
        print(f"  「{_get_quote()}」", file=out)
        print(file=out)


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Hermes × Aizen Banner")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--minimal", action="store_true")
    parser.add_argument("--no-integrations", action="store_true")
    parser.add_argument("--no-quote", action="store_true")
    args = parser.parse_args()

    print_banner(
        compact=args.compact,
        minimal=args.minimal,
        show_integrations=not args.no_integrations,
        show_quote=not args.no_quote,
        file=sys.stdout,
    )
