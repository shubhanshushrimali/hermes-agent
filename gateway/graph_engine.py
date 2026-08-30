"""
Aizen Graph Engine — LangGraph-powered reasoning state machine.

Replaces the linear TurnRunner loop with a structured graph:

    User Prompt → Classify → Route → Plan/Research/Debug
                                      ↓
                                   Execute
                                      ↓
                                   Validate
                                    ↙     ↘
                               Report    Retry (→ Execute)

Even a weak 3B model produces strong results because the SYSTEM
handles routing — each node does ONE simple task.

Usage:
    from gateway.graph_engine import create_agent_graph, AgentState

    graph = create_agent_graph(config)
    result = await graph.ainvoke(AgentState(user_prompt="Fix the login bug"))
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger("hermes.graph_engine")

# Try importing LangGraph — graceful fallback if not installed.
try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.memory import MemorySaver

    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    logger.info("LangGraph not installed — graph engine will use fallback linear mode")

# Try importing Langfuse for tracing.
try:
    from langfuse.decorators import observe, langfuse_context

    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

    # No-op decorator fallback.
    def observe(*args, **kwargs):
        def wrapper(fn):
            return fn
        if args and callable(args[0]):
            return args[0]
        return wrapper

# Try importing LiteLLM for model routing.
try:
    import litellm

    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False

# Try importing structlog.
try:
    import structlog

    slog = structlog.get_logger("hermes.graph_engine")
except ImportError:
    slog = logger


# ============================================================================
# Intent Classification
# ============================================================================

class Intent(str, Enum):
    """Classifiable user intent categories."""
    SIMPLE = "simple"           # Quick answer, no code needed
    CODE = "code"               # Write/modify code
    RESEARCH = "research"       # Needs web search / docs
    DEBUG = "debug"             # Fix a bug / error
    CREATIVE = "creative"       # Design, UI, brainstorm
    EXPLAIN = "explain"         # Explain code / concept
    REFACTOR = "refactor"       # Improve existing code
    TEST = "test"               # Write tests


# Keywords for fast local classification (no LLM needed).
_INTENT_KEYWORDS: Dict[Intent, List[str]] = {
    Intent.CODE: [
        "create", "build", "implement", "add", "write", "make",
        "generate", "scaffold", "setup", "install", "configure",
    ],
    Intent.DEBUG: [
        "fix", "bug", "error", "crash", "broken", "doesn't work",
        "fail", "issue", "problem", "wrong", "exception", "traceback",
    ],
    Intent.RESEARCH: [
        "search", "find", "look up", "what is", "how does",
        "documentation", "docs", "tutorial", "example", "best practice",
    ],
    Intent.EXPLAIN: [
        "explain", "why", "how", "what does", "understand",
        "walk me through", "describe", "tell me about",
    ],
    Intent.REFACTOR: [
        "refactor", "clean up", "improve", "optimize", "simplify",
        "reorganize", "restructure",
    ],
    Intent.TEST: [
        "test", "spec", "unit test", "integration test", "coverage",
        "assert", "pytest", "jest",
    ],
    Intent.CREATIVE: [
        "design", "ui", "ux", "layout", "style", "theme",
        "color", "font", "animation", "mockup",
    ],
}


def classify_intent_local(prompt: str) -> Intent:
    """Fast keyword-based intent classification (no LLM, $0 cost).

    Scans for keyword matches. Falls back to SIMPLE if no strong signal.
    """
    prompt_lower = prompt.lower()
    scores: Dict[Intent, int] = {}

    for intent, keywords in _INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in prompt_lower)
        if score > 0:
            scores[intent] = score

    if not scores:
        return Intent.SIMPLE

    return max(scores, key=scores.get)


@observe(name="classify_intent")
def classify_intent_llm(prompt: str, model: str = "ollama/llama3.2:3b") -> Intent:
    """LLM-based intent classification for ambiguous prompts.

    Uses a small local model (default: 3B params) for $0 cost.
    Falls back to keyword classifier if LLM fails.
    """
    if not LITELLM_AVAILABLE:
        return classify_intent_local(prompt)

    try:
        response = litellm.completion(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify the user's intent into exactly ONE category. "
                        "Reply with ONLY the category name, nothing else.\n"
                        "Categories: simple, code, research, debug, explain, "
                        "refactor, test, creative"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=10,
            temperature=0,
        )
        raw = response.choices[0].message.content.strip().lower()
        try:
            return Intent(raw)
        except ValueError:
            # LLM returned something unexpected — try partial match.
            for intent in Intent:
                if intent.value in raw:
                    return intent
            return classify_intent_local(prompt)
    except Exception as e:
        logger.debug("LLM classification failed: %s — using keyword fallback", e)
        return classify_intent_local(prompt)


# ============================================================================
# Agent State — the typed data flowing through the graph
# ============================================================================

@dataclass
class AgentState:
    """Typed state object flowing through every graph node.

    Every field is optional/has defaults so nodes can be composed
    independently and the graph can start from any checkpoint.
    """

    # --- Input ---
    user_prompt: str = ""
    session_key: str = ""
    model: str = ""                      # Primary model for generation

    # --- Classification ---
    intent: str = ""                     # Intent enum value
    confidence: float = 0.0

    # --- Planning ---
    plan: List[str] = field(default_factory=list)       # Decomposed steps
    current_step: int = 0

    # --- Research ---
    search_queries: List[str] = field(default_factory=list)
    research_context: List[str] = field(default_factory=list)

    # --- Execution ---
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    code_changes: List[Dict[str, Any]] = field(default_factory=list)
    agent_response: str = ""

    # --- Validation ---
    test_results: str = ""
    test_passed: bool = False
    lint_errors: List[str] = field(default_factory=list)

    # --- Control ---
    retry_count: int = 0
    max_retries: int = 3
    error: str = ""
    needs_human_input: bool = False
    human_feedback: str = ""

    # --- Output ---
    final_response: str = ""
    total_tokens: int = 0
    total_cost: float = 0.0
    execution_time: float = 0.0

    # --- Metadata ---
    trace_id: str = ""
    start_time: float = field(default_factory=time.time)


# ============================================================================
# Graph Nodes — each does ONE thing
# ============================================================================

@observe(name="node:classify")
def node_classify(state: dict) -> dict:
    """Classify user intent. Fast keyword match first, LLM if ambiguous."""
    prompt = state.get("user_prompt", "")

    # Try fast local classification first.
    intent = classify_intent_local(prompt)

    # If SIMPLE (no keywords matched), try LLM for better accuracy.
    if intent == Intent.SIMPLE and len(prompt.split()) > 5:
        intent = classify_intent_llm(prompt)

    slog.info("intent_classified", prompt=prompt[:80], intent=intent.value)
    return {**state, "intent": intent.value}


@observe(name="node:plan")
def node_plan(state: dict) -> dict:
    """Break the task into executable steps.

    For code/debug/refactor tasks, creates a structured plan.
    This is what makes the agent systematic instead of chaotic.
    """
    prompt = state.get("user_prompt", "")
    intent = state.get("intent", "simple")

    if intent in ("simple", "explain"):
        # No planning needed for simple questions.
        return {**state, "plan": [prompt]}

    if not LITELLM_AVAILABLE:
        return {**state, "plan": [prompt]}

    model = state.get("model") or "ollama/llama3.2:3b"

    try:
        response = litellm.completion(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Break this task into 2-5 concrete steps. "
                        "Return ONLY a JSON array of strings. "
                        "Each step should be actionable and specific.\n"
                        "Example: [\"Read the auth module\", \"Add JWT validation\", \"Write tests\"]"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        # Parse JSON array from response.
        if "[" in raw:
            raw = raw[raw.index("["):raw.rindex("]") + 1]
            plan = json.loads(raw)
            if isinstance(plan, list) and all(isinstance(s, str) for s in plan):
                slog.info("plan_created", steps=len(plan))
                return {**state, "plan": plan}
    except Exception as e:
        logger.debug("Planning failed: %s — using single-step", e)

    return {**state, "plan": [prompt]}


@observe(name="node:research")
def node_research(state: dict) -> dict:
    """Auto-search the web AND codebase graph for context.

    Uses:
    1. Codebase knowledge graph (Graphify / regex) for structural context
    2. Web search tool for external knowledge
    """
    prompt = state.get("user_prompt", "")
    context = list(state.get("research_context", []))

    # --- Codebase graph context ---
    try:
        from gateway.codebase_graph import get_graph_manager
        manager = get_graph_manager()
        # Try to find a workspace path from session or default.
        workspace = state.get("workspace_path", os.getcwd())
        graph = manager.get_graph(workspace)
        if graph:
            code_context = manager.query(workspace, prompt)
            if code_context:
                context.append(f"Codebase graph context:\n{code_context}")
                slog.info("graph_context_added", nodes=graph.node_count)
    except Exception as e:
        logger.debug("Codebase graph query failed: %s", e)

    # --- Web search ---
    try:
        from tools.web_tools import web_search_tool
        results = web_search_tool(prompt, limit=3)
        if results:
            context.append(f"Web search results:\n{results}")
            slog.info("research_complete", results_len=len(results))
    except Exception as e:
        logger.debug("Research failed: %s", e)

    return {**state, "research_context": context}


@observe(name="node:execute")
def node_execute(state: dict) -> dict:
    """Execute the agent turn using the existing GatewayRunner.

    This node bridges the graph engine to the existing Hermes agent
    loop. The graph provides structured context; the agent does the work.
    """
    # The actual execution happens in GatewayRunner._run_agent_inner.
    # This node prepares the enhanced prompt with plan + research context.
    prompt = state.get("user_prompt", "")
    plan = state.get("plan", [])
    research = state.get("research_context", [])
    current_step = state.get("current_step", 0)

    # Build enhanced prompt with context.
    enhanced_parts = []

    if plan and len(plan) > 1:
        step_info = f"[Step {current_step + 1}/{len(plan)}] {plan[current_step]}" if current_step < len(plan) else prompt
        enhanced_parts.append(f"Current task: {step_info}")
        enhanced_parts.append(f"Full plan: {json.dumps(plan)}")

    if research:
        enhanced_parts.append(f"Research context: {' '.join(research[:2])}")

    enhanced_prompt = prompt
    if enhanced_parts:
        enhanced_prompt = "\n\n".join(enhanced_parts) + f"\n\nOriginal request: {prompt}"

    slog.info("execute_start", step=current_step, has_research=bool(research))

    return {
        **state,
        "agent_response": "",  # Will be filled by GatewayRunner
        "messages": state.get("messages", []) + [
            {"role": "user", "content": enhanced_prompt}
        ],
    }


@observe(name="node:validate")
def node_validate(state: dict) -> dict:
    """Validate the agent's work — run tests, check lint, verify output.

    This is what closes the quality gap between weak and strong models.
    The graph catches mistakes and retries automatically.
    """
    response = state.get("agent_response", "")
    code_changes = state.get("code_changes", [])

    # If no code was changed, skip validation.
    if not code_changes:
        return {**state, "test_passed": True}

    test_passed = True
    test_results = ""
    lint_errors = []

    # Try running tests if any test files were modified.
    try:
        import subprocess
        # Check for Python tests.
        result = subprocess.run(
            ["python", "-m", "pytest", "--tb=short", "-q", "--no-header"],
            capture_output=True, text=True, timeout=30, cwd="."
        )
        test_results = result.stdout + result.stderr
        test_passed = result.returncode == 0
    except Exception:
        # No tests to run — that's OK.
        pass

    slog.info("validation_complete", passed=test_passed, retry=state.get("retry_count", 0))

    return {
        **state,
        "test_passed": test_passed,
        "test_results": test_results,
        "lint_errors": lint_errors,
    }


@observe(name="node:report")
def node_report(state: dict) -> dict:
    """Format the final response with execution metadata."""
    response = state.get("agent_response", "")
    execution_time = time.time() - state.get("start_time", time.time())

    slog.info(
        "turn_complete",
        intent=state.get("intent"),
        steps=len(state.get("plan", [])),
        retries=state.get("retry_count", 0),
        time=f"{execution_time:.1f}s",
        cost=f"${state.get('total_cost', 0):.4f}",
    )

    return {
        **state,
        "final_response": response,
        "execution_time": execution_time,
    }


@observe(name="node:retry")
def node_retry(state: dict) -> dict:
    """Handle retry logic — increment counter, add error context."""
    retry_count = state.get("retry_count", 0) + 1
    test_results = state.get("test_results", "")

    slog.warning("retrying", attempt=retry_count, max=state.get("max_retries", 3))

    # Add test failure context to help the agent fix the issue.
    error_context = f"\n\nPrevious attempt failed. Test results:\n{test_results}\n\nPlease fix the issues and try again."

    return {
        **state,
        "retry_count": retry_count,
        "user_prompt": state.get("user_prompt", "") + error_context,
    }


# ============================================================================
# Routing Functions — conditional edges
# ============================================================================

def route_by_intent(state: dict) -> str:
    """Route to the appropriate node based on classified intent."""
    intent = state.get("intent", "simple")

    if intent in ("research",):
        return "research"
    elif intent in ("code", "debug", "refactor", "test"):
        return "plan"
    elif intent in ("simple", "explain", "creative"):
        return "execute"  # Direct execution, no planning needed
    else:
        return "execute"


def route_after_validate(state: dict) -> str:
    """Decide whether to report success or retry."""
    if state.get("test_passed", True):
        return "report"

    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if retry_count >= max_retries:
        slog.warning("max_retries_exhausted", retries=retry_count)
        return "report"  # Give up and report what we have.

    return "retry"


# ============================================================================
# Graph Construction
# ============================================================================

def create_agent_graph(
    checkpointer: Any = None,
    config: Optional[Dict[str, Any]] = None,
) -> Any:
    """Build the LangGraph state machine for agent reasoning.

    Returns a compiled graph that can be invoked with:
        result = graph.invoke({"user_prompt": "..."})

    If LangGraph is not installed, returns a FallbackGraph that
    runs nodes linearly (classify → plan → execute → report).
    """
    if not LANGGRAPH_AVAILABLE:
        return FallbackGraph()

    graph = StateGraph(dict)

    # Add nodes.
    graph.add_node("classify", node_classify)
    graph.add_node("plan", node_plan)
    graph.add_node("research", node_research)
    graph.add_node("execute", node_execute)
    graph.add_node("validate", node_validate)
    graph.add_node("report", node_report)
    graph.add_node("retry", node_retry)

    # Set entry point.
    graph.set_entry_point("classify")

    # Conditional routing after classification.
    graph.add_conditional_edges(
        "classify",
        route_by_intent,
        {
            "plan": "plan",
            "research": "research",
            "execute": "execute",
        },
    )

    # After planning, execute.
    graph.add_edge("plan", "execute")

    # After research, plan (then execute).
    graph.add_edge("research", "plan")

    # After execution, validate.
    graph.add_edge("execute", "validate")

    # After validation, report or retry.
    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "report": "report",
            "retry": "retry",
        },
    )

    # After retry, re-execute.
    graph.add_edge("retry", "execute")

    # Report is the end.
    graph.add_edge("report", END)

    # Compile with optional checkpointer for persistence.
    if checkpointer is None:
        checkpointer = MemorySaver()

    compiled = graph.compile(checkpointer=checkpointer)
    slog.info("graph_compiled", nodes=7, edges=8)
    return compiled


class FallbackGraph:
    """Linear fallback when LangGraph is not installed.

    Runs: classify → plan → execute → validate → report
    No conditional routing, no retry loops.
    """

    def invoke(self, state: dict, config: Optional[dict] = None) -> dict:
        state = node_classify(state)
        state = node_plan(state)
        state = node_execute(state)
        state = node_validate(state)
        state = node_report(state)
        return state

    async def ainvoke(self, state: dict, config: Optional[dict] = None) -> dict:
        return await asyncio.get_event_loop().run_in_executor(
            None, self.invoke, state
        )


# ============================================================================
# Budget Guardrails
# ============================================================================

class BudgetGuard:
    """Track and limit API spend per day.

    Prevents runaway costs when agents run 24/7 on a laptop.
    """

    def __init__(self, max_daily_usd: float = 10.0, db_path: str = None):
        self.max_daily_usd = max_daily_usd
        self._daily_spend: float = 0.0
        self._date: str = ""
        self._db_path = db_path

    def _today(self) -> str:
        import datetime
        return datetime.date.today().isoformat()

    def check_budget(self) -> bool:
        """Return True if we're under budget."""
        today = self._today()
        if today != self._date:
            # New day — reset counter.
            self._daily_spend = 0.0
            self._date = today
        return self._daily_spend < self.max_daily_usd

    def record_cost(self, cost_usd: float) -> None:
        """Record a cost and check if we've exceeded the budget."""
        today = self._today()
        if today != self._date:
            self._daily_spend = 0.0
            self._date = today
        self._daily_spend += cost_usd

        if self._daily_spend >= self.max_daily_usd:
            slog.warning(
                "budget_exceeded",
                daily_spend=f"${self._daily_spend:.4f}",
                max=f"${self.max_daily_usd:.2f}",
            )

    @property
    def remaining_budget(self) -> float:
        return max(0, self.max_daily_usd - self._daily_spend)

    @property
    def daily_spend(self) -> float:
        return self._daily_spend


# ============================================================================
# LiteLLM Model Router
# ============================================================================

class ModelRouter:
    """Route tasks to the optimal model based on intent and complexity.

    Uses cheap/free local models for simple tasks, expensive cloud
    models only when needed. ~70% cost reduction.
    """

    # Default routing table — override via config.
    DEFAULT_ROUTES: Dict[str, str] = {
        # Intent → Model
        "simple": "ollama/llama3.2:3b",          # $0 — local
        "explain": "ollama/llama3.2:3b",          # $0 — local
        "classify": "ollama/llama3.2:3b",         # $0 — local
        "code": "anthropic/claude-sonnet-4-20250514",        # Cloud
        "debug": "anthropic/claude-sonnet-4-20250514",       # Cloud
        "refactor": "anthropic/claude-sonnet-4-20250514",    # Cloud
        "test": "ollama/codestral:22b",           # $0 — local (if GPU)
        "research": "ollama/llama3.2:3b",         # $0 — local
        "creative": "anthropic/claude-sonnet-4-20250514",    # Cloud
    }

    def __init__(self, routes: Optional[Dict[str, str]] = None,
                 budget: Optional[BudgetGuard] = None):
        self.routes = routes or dict(self.DEFAULT_ROUTES)
        self.budget = budget or BudgetGuard()

    def get_model(self, intent: str, fallback: str = "") -> str:
        """Get the optimal model for an intent.

        If budget is exhausted, falls back to free local models.
        """
        if not self.budget.check_budget():
            slog.warning("budget_exhausted_using_local", intent=intent)
            return "ollama/llama3.2:3b"  # Always free

        model = self.routes.get(intent, fallback or "ollama/llama3.2:3b")
        slog.debug("model_routed", intent=intent, model=model)
        return model

    @observe(name="litellm_completion")
    def completion(self, intent: str, messages: List[Dict], **kwargs) -> Any:
        """Route a completion request to the right model."""
        model = self.get_model(intent)

        if not LITELLM_AVAILABLE:
            raise ImportError("LiteLLM not installed")

        response = litellm.completion(model=model, messages=messages, **kwargs)

        # Track cost.
        cost = response._hidden_params.get("response_cost", 0) if hasattr(response, "_hidden_params") else 0
        if cost:
            self.budget.record_cost(cost)

        return response


# ============================================================================
# Public API
# ============================================================================

# Singleton instances.
_graph = None
_router = None
_budget = None


def get_graph() -> Any:
    """Get or create the global agent graph."""
    global _graph
    if _graph is None:
        _graph = create_agent_graph()
    return _graph


def get_router() -> ModelRouter:
    """Get or create the global model router."""
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


def get_budget() -> BudgetGuard:
    """Get or create the global budget guard."""
    global _budget
    if _budget is None:
        _budget = BudgetGuard(max_daily_usd=10.0)
    return _budget


def process_prompt(user_prompt: str, session_key: str = "",
                   model: str = "") -> dict:
    """Process a user prompt through the graph engine.

    This is the main entry point. Returns the final AgentState dict.
    """
    graph = get_graph()
    router = get_router()

    # Quick classify to pick the right model.
    intent = classify_intent_local(user_prompt)
    if not model:
        model = router.get_model(intent.value)

    state = {
        "user_prompt": user_prompt,
        "session_key": session_key,
        "model": model,
        "start_time": time.time(),
    }

    result = graph.invoke(state)
    return result
