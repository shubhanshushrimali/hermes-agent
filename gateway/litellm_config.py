"""
LiteLLM Configuration for Hermes Agent — Model Routing & Cost Control.

Provides a unified API for 140+ LLM providers. Routes tasks to the
optimal model based on intent: free local models for simple tasks,
cloud models for complex reasoning.

Usage:
    from gateway.litellm_config import get_completion, configure_litellm

    configure_litellm()  # Call once at startup

    # Route by intent — auto-picks the best model:
    response = get_completion(
        intent="code",
        messages=[{"role": "user", "content": "Fix the auth bug"}],
    )

    # Or specify a model directly:
    response = get_completion(
        model="anthropic/claude-sonnet-4-20250514",
        messages=[...],
    )
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hermes.litellm")

try:
    import litellm
    from litellm import completion, acompletion

    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logger.info("LiteLLM not installed — model routing disabled. pip install litellm")

# Try importing Langfuse callback for auto-tracing.
try:
    from langfuse.decorators import observe

    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

    def observe(*a, **kw):
        def w(fn): return fn
        if a and callable(a[0]): return a[0]
        return w


# ============================================================================
# Model Routing Table
# ============================================================================

# Intent → model mapping. Override via HERMES_MODEL_ROUTES env var (JSON).
DEFAULT_MODEL_ROUTES: Dict[str, str] = {
    # --- FREE (local Ollama) ---
    "classify": "ollama/llama3.2:3b",
    "simple":   "ollama/llama3.2:3b",
    "explain":  "ollama/llama3.2:3b",
    "research": "ollama/llama3.2:3b",

    # --- CLOUD (paid, high quality) ---
    "code":     "anthropic/claude-sonnet-4-20250514",
    "debug":    "anthropic/claude-sonnet-4-20250514",
    "refactor": "anthropic/claude-sonnet-4-20250514",
    "creative": "anthropic/claude-sonnet-4-20250514",
    "test":     "anthropic/claude-sonnet-4-20250514",

    # --- Fallback ---
    "default":  "anthropic/claude-sonnet-4-20250514",
}

# Fallback chain: if primary model fails, try these in order.
FALLBACK_MODELS: List[str] = [
    "openai/gpt-4o",
    "ollama/llama3.2:3b",  # Always available locally
]


# ============================================================================
# Configuration
# ============================================================================

def configure_litellm(
    max_daily_budget_usd: float = 10.0,
    enable_caching: bool = True,
    log_level: str = "WARNING",
) -> bool:
    """Configure LiteLLM for Hermes Agent.

    Call once at startup (e.g., in gateway/run.py or main.py).
    """
    if not LITELLM_AVAILABLE:
        return False

    # Suppress verbose LiteLLM logs.
    litellm.set_verbose = False
    logging.getLogger("litellm").setLevel(getattr(logging, log_level))

    # Enable token counting for cost tracking.
    litellm.success_callback = []
    litellm.failure_callback = []

    # Add Langfuse callback for auto-tracing if available.
    if LANGFUSE_AVAILABLE and os.environ.get("LANGFUSE_PUBLIC_KEY"):
        litellm.success_callback.append("langfuse")
        litellm.failure_callback.append("langfuse")
        logger.info("LiteLLM → Langfuse tracing enabled")

    # Enable caching (avoid re-calling LLM for identical prompts).
    if enable_caching:
        litellm.cache = litellm.Cache(type="local")
        logger.info("LiteLLM caching enabled (in-memory)")

    # Set max budget.
    litellm.max_budget = max_daily_budget_usd

    # Drop unsupported params silently (instead of crashing).
    litellm.drop_params = True

    logger.info(
        "LiteLLM configured: budget=$%.2f/day, caching=%s",
        max_daily_budget_usd,
        enable_caching,
    )
    return True


# ============================================================================
# Completion API
# ============================================================================

@observe(name="litellm_completion")
def get_completion(
    messages: List[Dict[str, str]],
    intent: str = "default",
    model: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    **kwargs: Any,
) -> Any:
    """Get a completion from the optimal model.

    Routes by intent if no model specified. Falls back to cheaper
    models if budget is exhausted or primary model fails.

    Args:
        messages: Chat messages in OpenAI format.
        intent: Task intent for auto-routing (code/debug/simple/etc).
        model: Override model (skips routing).
        max_tokens: Max response tokens.
        temperature: Sampling temperature.

    Returns:
        LiteLLM completion response.

    Raises:
        ImportError: If LiteLLM not installed.
        Exception: If all models fail.
    """
    if not LITELLM_AVAILABLE:
        raise ImportError("LiteLLM not installed. Run: pip install litellm")

    # Resolve model from routing table.
    target_model = model or DEFAULT_MODEL_ROUTES.get(
        intent, DEFAULT_MODEL_ROUTES["default"]
    )

    # Try primary model, then fallbacks.
    models_to_try = [target_model] + [
        fb for fb in FALLBACK_MODELS if fb != target_model
    ]

    last_error = None
    for m in models_to_try:
        try:
            response = completion(
                model=m,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )

            # Log cost.
            cost = getattr(response, '_hidden_params', {}).get('response_cost', 0)
            if cost:
                logger.debug("LLM cost: $%.6f (model=%s)", cost, m)

            return response

        except Exception as e:
            last_error = e
            logger.warning("Model %s failed: %s — trying fallback", m, e)
            continue

    raise last_error or RuntimeError("All models failed")


async def get_completion_async(
    messages: List[Dict[str, str]],
    intent: str = "default",
    model: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    **kwargs: Any,
) -> Any:
    """Async version of get_completion."""
    if not LITELLM_AVAILABLE:
        raise ImportError("LiteLLM not installed")

    target_model = model or DEFAULT_MODEL_ROUTES.get(
        intent, DEFAULT_MODEL_ROUTES["default"]
    )

    models_to_try = [target_model] + [
        fb for fb in FALLBACK_MODELS if fb != target_model
    ]

    last_error = None
    for m in models_to_try:
        try:
            response = await acompletion(
                model=m,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
            return response
        except Exception as e:
            last_error = e
            logger.warning("Model %s failed: %s — trying fallback", m, e)
            continue

    raise last_error or RuntimeError("All models failed")


# ============================================================================
# Utilities
# ============================================================================

def get_model_for_intent(intent: str) -> str:
    """Get the model name for an intent (for display in UI)."""
    return DEFAULT_MODEL_ROUTES.get(intent, DEFAULT_MODEL_ROUTES["default"])


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate the cost of a completion in USD."""
    if not LITELLM_AVAILABLE:
        return 0.0

    try:
        cost = litellm.completion_cost(
            model=model,
            prompt="x" * input_tokens,  # Rough estimate.
            completion="x" * output_tokens,
        )
        return cost
    except Exception:
        return 0.0


def list_available_models() -> List[str]:
    """List all models configured in the routing table."""
    return list(set(DEFAULT_MODEL_ROUTES.values()))
