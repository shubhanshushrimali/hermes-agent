"""Spend and token budgets for the core conversation loop.

Daily USD spend used to live only on ``gateway.graph_engine.BudgetGuard`` —
the LiteLLM router and the cost dashboard read it, but ``run_conversation``
never stopped. This module is the turn-loop source of truth:

* ``max_daily_cost_usd`` (default 10) — process-wide daily cap
* ``max_session_cost_usd`` — this agent's estimated USD
* ``max_session_tokens`` — billed ``session_total_tokens``

At 80% the loop injects a wrap-up notice (same cache-safe tool-result
channel as the wall-clock run budget). At 100% the loop **hard-stops
before the next provider call** — it does not make a summary API call
(that would spend more).
"""

from __future__ import annotations

import datetime
import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hermes.spend_budget")

DEFAULT_MAX_DAILY_USD = 10.0

SPEND_BUDGET_WRAPUP_NOTICE = (
    "[SYSTEM NOTICE — spend/token budget nearly exhausted] "
    "Spend or token budget nearly exhausted. Stop new discovery work now. "
    "Produce the required final deliverable from the state you already have, "
    "completing only mandatory writes."
)

_guard_lock = threading.Lock()
_budget: Optional["BudgetGuard"] = None


class BudgetGuard:
    """Track and limit API spend per process-day.

    Prevents runaway costs when agents run 24/7 on a laptop. Shared by the
    conversation loop (hard-stop), the LiteLLM router, and the cost dashboard.
    """

    def __init__(self, max_daily_usd: float = DEFAULT_MAX_DAILY_USD, db_path: str = None):
        self.max_daily_usd = max_daily_usd
        self._daily_spend: float = 0.0
        self._date: str = ""
        self._db_path = db_path
        self._by_model: Dict[str, float] = {}
        self._by_intent: Dict[str, float] = {}
        self._day_history: List[Dict[str, Any]] = []

    def _today(self) -> str:
        return datetime.date.today().isoformat()

    def _roll_day(self) -> None:
        today = self._today()
        if today != self._date:
            if self._date and self._daily_spend:
                self._day_history.append({"date": self._date, "cost": self._daily_spend})
                self._day_history = self._day_history[-7:]
            self._daily_spend = 0.0
            self._by_model = {}
            self._by_intent = {}
            self._date = today

    def check_budget(self) -> bool:
        """Return True if we're under budget."""
        self._roll_day()
        return self._daily_spend < self.max_daily_usd

    def record_cost(
        self,
        cost_usd: float,
        model: Optional[str] = None,
        intent: Optional[str] = None,
    ) -> None:
        """Record a cost. Logs when the daily cap is crossed."""
        self._roll_day()
        try:
            amount = float(cost_usd)
        except (TypeError, ValueError):
            return
        if amount <= 0:
            return
        self._daily_spend += amount
        if model:
            key = str(model).strip()
            if key:
                self._by_model[key] = self._by_model.get(key, 0.0) + amount
        if intent:
            key = str(intent).strip()
            if key:
                self._by_intent[key] = self._by_intent.get(key, 0.0) + amount
        if self._daily_spend >= self.max_daily_usd:
            logger.warning(
                "Daily spend budget exceeded: $%.4f / $%.2f",
                self._daily_spend,
                self.max_daily_usd,
            )

    @property
    def remaining_budget(self) -> float:
        self._roll_day()
        return max(0.0, self.max_daily_usd - self._daily_spend)

    @property
    def daily_spend(self) -> float:
        self._roll_day()
        return self._daily_spend

    @property
    def by_model(self) -> Dict[str, float]:
        self._roll_day()
        return dict(self._by_model)

    @property
    def by_intent(self) -> Dict[str, float]:
        self._roll_day()
        return dict(self._by_intent)

    @property
    def last_7_days(self) -> List[Dict[str, Any]]:
        self._roll_day()
        days = list(self._day_history)
        if self._date:
            days.append({"date": self._date, "cost": self._daily_spend})
        return days[-7:]


def get_budget() -> BudgetGuard:
    """Process-wide daily spend guard (cost dashboard + turn loop)."""
    global _budget
    with _guard_lock:
        if _budget is None:
            _budget = BudgetGuard(max_daily_usd=DEFAULT_MAX_DAILY_USD)
        return _budget


def reset_budget_for_tests() -> None:
    """Reset the singleton. Tests only."""
    global _budget
    with _guard_lock:
        _budget = None


def normalize_positive_float(value: Any) -> Optional[float]:
    """None / non-numeric / non-positive → None (feature off). Reject bool."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number <= 0:
        return None
    return number


def normalize_positive_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def record_turn_cost(agent: Any, cost_usd: Optional[float]) -> None:
    """Feed a priced API call into the daily guard. Session USD is already updated."""
    if cost_usd is None:
        return
    try:
        amount = float(cost_usd)
    except (TypeError, ValueError):
        return
    if amount <= 0:
        return
    if getattr(agent, "max_daily_cost_usd", None) is None:
        return
    try:
        get_budget().record_cost(
            amount,
            model=str(getattr(agent, "model", "") or "") or None,
            intent=str(getattr(agent, "_current_intent", "") or "") or None,
        )
    except Exception:
        logger.debug("daily spend record failed", exc_info=True)


def spend_or_token_budget_reason(agent: Any) -> Optional[str]:
    """Why the next provider call must not run, or None.

    The budget-crossing request is allowed to finish (tools land); this
    fires at the top of the next iteration, same as review input budget.
    """
    session_cap = getattr(agent, "max_session_cost_usd", None)
    if session_cap is not None:
        used = getattr(agent, "session_estimated_cost_usd", 0.0) or 0.0
        try:
            if float(used) >= float(session_cap):
                return "spend_budget_exhausted"
        except (TypeError, ValueError):
            pass

    daily_cap = getattr(agent, "max_daily_cost_usd", None)
    if daily_cap is not None:
        try:
            agent_cap = float(daily_cap)
            live_cap = float(get_budget().max_daily_usd)
            cap = min(agent_cap, live_cap) if live_cap > 0 else agent_cap
            if get_budget().daily_spend >= cap:
                return "spend_budget_exhausted"
        except (TypeError, ValueError):
            logger.debug("daily spend check failed", exc_info=True)

    token_cap = getattr(agent, "max_session_tokens", None)
    if token_cap is not None:
        used = getattr(agent, "session_total_tokens", 0) or 0
        try:
            if int(used) >= int(token_cap):
                return "token_budget_exhausted"
        except (TypeError, ValueError):
            pass
    return None


def _closest_ratio(agent: Any) -> float:
    """Highest fraction of any armed budget currently consumed (0–1+)."""
    ratios: list[float] = []
    session_cap = getattr(agent, "max_session_cost_usd", None)
    if session_cap:
        try:
            ratios.append(float(agent.session_estimated_cost_usd or 0) / float(session_cap))
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    daily_cap = getattr(agent, "max_daily_cost_usd", None)
    if daily_cap:
        try:
            agent_cap = float(daily_cap)
            live_cap = float(get_budget().max_daily_usd)
            cap = min(agent_cap, live_cap) if live_cap > 0 else agent_cap
            if cap > 0:
                ratios.append(get_budget().daily_spend / cap)
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    token_cap = getattr(agent, "max_session_tokens", None)
    if token_cap:
        try:
            ratios.append(float(agent.session_total_tokens or 0) / float(token_cap))
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    return max(ratios) if ratios else 0.0


def maybe_inject_spend_budget_wrapup(agent: Any, messages: List[Dict[str, Any]]) -> bool:
    """Inject the 80% wrap-up notice onto the newest tool result."""
    if getattr(agent, "_spend_budget_wrapup_injected", False):
        return False
    armed = (
        getattr(agent, "max_daily_cost_usd", None) is not None
        or getattr(agent, "max_session_cost_usd", None) is not None
        or getattr(agent, "max_session_tokens", None) is not None
    )
    if not armed:
        return False
    if _closest_ratio(agent) < 0.8:
        return False
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if not (isinstance(msg, dict) and msg.get("role") == "tool"):
            continue
        existing = msg.get("content", "")
        if isinstance(existing, str):
            msg["content"] = existing + f"\n\n{SPEND_BUDGET_WRAPUP_NOTICE}"
        else:
            try:
                blocks = list(existing) if existing else []
                blocks.append({"type": "text", "text": SPEND_BUDGET_WRAPUP_NOTICE})
                msg["content"] = blocks
            except Exception:
                return False
        agent._spend_budget_wrapup_injected = True
        logger.info("Spend/token budget wrap-up notice injected (ratio=%.2f)", _closest_ratio(agent))
        return True
    return False
