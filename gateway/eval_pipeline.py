"""
Langfuse Evaluation Pipeline — automated quality benchmarking.

Runs evaluation datasets against the agent and tracks quality scores
in Langfuse. This enables:
1. Regression detection (quality drops after changes)
2. Model comparison (which model performs best per intent)
3. Cost/quality tradeoff analysis
4. CI/CD quality gates

Usage:
    python -m gateway.eval_pipeline run --dataset code-review
    python -m gateway.eval_pipeline compare --models claude,gpt4,ollama
    python -m gateway.eval_pipeline report
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hermes.eval")


@dataclass
class EvalCase:
    """A single evaluation test case."""
    id: str
    prompt: str
    intent: str                    # code, debug, refactor, research, chat
    expected_keywords: List[str]   # Must appear in response
    forbidden_keywords: List[str] = field(default_factory=list)
    max_response_time_s: float = 30.0
    max_cost_usd: float = 0.10


@dataclass
class EvalResult:
    """Result of evaluating a single test case."""
    case_id: str
    model: str
    passed: bool
    score: float                   # 0.0-1.0
    response_time_s: float
    cost_usd: float
    response_length: int
    keyword_hits: int
    keyword_total: int
    errors: List[str] = field(default_factory=list)


# =============================================================================
# Built-in Evaluation Datasets
# =============================================================================

DATASETS: Dict[str, List[EvalCase]] = {
    "code-review": [
        EvalCase(
            id="cr-1",
            prompt="Review this Python function for bugs:\ndef divide(a, b):\n    return a / b",
            intent="code",
            expected_keywords=["zero", "ZeroDivisionError", "exception", "error"],
        ),
        EvalCase(
            id="cr-2",
            prompt="Review this code:\npassword = 'admin123'\ndb_conn = connect(password=password)",
            intent="code",
            expected_keywords=["hardcoded", "security", "credential", "secret"],
        ),
        EvalCase(
            id="cr-3",
            prompt="Review:\nimport os\nos.system(f'rm -rf {user_input}')",
            intent="code",
            expected_keywords=["injection", "sanitize", "security", "dangerous"],
        ),
        EvalCase(
            id="cr-4",
            prompt="Review:\ndef get_user(id):\n    return db.execute(f'SELECT * FROM users WHERE id = {id}')",
            intent="code",
            expected_keywords=["SQL injection", "parameterized", "prepared"],
        ),
        EvalCase(
            id="cr-5",
            prompt="Review:\ndef process(data):\n    for item in data:\n        for sub in item:\n            for x in sub:\n                result.append(transform(x))\n    return result",
            intent="code",
            expected_keywords=["nested", "readability", "comprehension", "refactor"],
        ),
    ],
    "debug": [
        EvalCase(
            id="db-1",
            prompt="Why does this crash?\nmy_list = [1, 2, 3]\nprint(my_list[5])",
            intent="debug",
            expected_keywords=["IndexError", "out of range", "index"],
        ),
        EvalCase(
            id="db-2",
            prompt="Why is this slow?\nresult = []\nfor i in range(1000000):\n    result = result + [i]",
            intent="debug",
            expected_keywords=["append", "O(n", "performance", "copy"],
        ),
        EvalCase(
            id="db-3",
            prompt="TypeError: unhashable type: 'list'\nmy_dict = {[1,2]: 'value'}",
            intent="debug",
            expected_keywords=["unhashable", "list", "tuple", "immutable"],
        ),
        EvalCase(
            id="db-4",
            prompt="My recursive function never returns:\ndef fib(n):\n    return fib(n-1) + fib(n-2)",
            intent="debug",
            expected_keywords=["base case", "recursion", "infinite", "stack overflow"],
        ),
    ],
    "classify": [
        EvalCase(
            id="cl-1",
            prompt="Fix the auth bug in login.py",
            intent="debug",
            expected_keywords=["auth", "fix", "bug"],
        ),
        EvalCase(
            id="cl-2",
            prompt="What's the weather like today?",
            intent="chat",
            expected_keywords=["weather"],
        ),
        EvalCase(
            id="cl-3",
            prompt="Refactor the database module to use connection pooling",
            intent="refactor",
            expected_keywords=["refactor", "database", "pool"],
        ),
        EvalCase(
            id="cl-4",
            prompt="Find papers about transformer architectures from 2024",
            intent="research",
            expected_keywords=["transformer", "research", "paper"],
        ),
    ],
    "refactor": [
        EvalCase(
            id="rf-1",
            prompt="Refactor this to remove duplication:\ndef area_circle(r): return 3.14*r*r\ndef area_sphere(r): return 4*3.14*r*r",
            intent="refactor",
            expected_keywords=["constant", "math.pi", "DRY", "reuse"],
        ),
        EvalCase(
            id="rf-2",
            prompt="Refactor these if-elif chains into a cleaner pattern:\nif action == 'create': do_create()\nelif action == 'read': do_read()\nelif action == 'update': do_update()\nelif action == 'delete': do_delete()",
            intent="refactor",
            expected_keywords=["dict", "dispatch", "mapping", "strategy"],
        ),
        EvalCase(
            id="rf-3",
            prompt="Refactor: class with 15 methods and 500 lines doing auth, email, and logging",
            intent="refactor",
            expected_keywords=["single responsibility", "separate", "class", "module"],
        ),
    ],
    "security": [
        EvalCase(
            id="sec-1",
            prompt="Is this JWT validation secure?\ntoken = jwt.decode(token_str, algorithms=['none'])",
            intent="code",
            expected_keywords=["algorithm none", "insecure", "verify", "secret"],
        ),
        EvalCase(
            id="sec-2",
            prompt="Review CORS config:\napp.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True)",
            intent="code",
            expected_keywords=["wildcard", "credentials", "CORS", "restrict"],
        ),
        EvalCase(
            id="sec-3",
            prompt="Is this safe?\nuser_input = request.args.get('name')\nreturn f'<h1>Hello {user_input}</h1>'",
            intent="code",
            expected_keywords=["XSS", "cross-site", "escape", "sanitize"],
        ),
        EvalCase(
            id="sec-4",
            prompt="Review:\nsubprocess.call(f'convert {filename}', shell=True)",
            intent="code",
            expected_keywords=["shell", "injection", "subprocess", "list"],
            forbidden_keywords=["looks good", "no issues"],
        ),
    ],
    "api-design": [
        EvalCase(
            id="api-1",
            prompt="Design a REST API for a todo app with users, lists, and items",
            intent="code",
            expected_keywords=["GET", "POST", "endpoint", "resource"],
        ),
        EvalCase(
            id="api-2",
            prompt="How should I handle pagination in a REST API returning 10,000 items?",
            intent="code",
            expected_keywords=["cursor", "offset", "limit", "page"],
        ),
    ],
    "testing": [
        EvalCase(
            id="test-1",
            prompt="Write unit tests for:\ndef is_palindrome(s): return s == s[::-1]",
            intent="code",
            expected_keywords=["test", "assert", "palindrome", "edge case"],
        ),
        EvalCase(
            id="test-2",
            prompt="What's wrong with this test?\ndef test_add(): assert add(2, 2) == 5",
            intent="debug",
            expected_keywords=["expected", "4", "wrong", "assertion"],
        ),
    ],
    "architecture": [
        EvalCase(
            id="arch-1",
            prompt="I have a monolith handling auth, payments, and email. How should I split it?",
            intent="code",
            expected_keywords=["microservice", "domain", "service", "boundary"],
        ),
        EvalCase(
            id="arch-2",
            prompt="When should I use a message queue vs direct API calls between services?",
            intent="code",
            expected_keywords=["async", "decouple", "reliability", "queue"],
        ),
    ],
}


# =============================================================================
# Evaluation Engine
# =============================================================================

class EvalEngine:
    """Run evaluation datasets and score results."""

    def __init__(self, model: str = ""):
        self.model = model
        self.results: List[EvalResult] = []

    def run_dataset(self, dataset_name: str) -> List[EvalResult]:
        """Run all cases in a dataset."""
        dataset = DATASETS.get(dataset_name, [])
        if not dataset:
            logger.warning("Unknown dataset: %s", dataset_name)
            return []

        results = []
        for case in dataset:
            result = self._run_case(case)
            results.append(result)
            self.results.append(result)

        return results

    def _run_case(self, case: EvalCase) -> EvalResult:
        """Run a single evaluation case."""
        errors = []
        start = time.time()
        response = ""

        try:
            from gateway.graph_engine import process_prompt
            result = process_prompt(case.prompt, model=self.model)
            response = result.get("final_response", "")
        except Exception as e:
            errors.append(str(e))
            # Fallback: use classify only.
            try:
                from gateway.graph_engine import classify_intent_local
                intent = classify_intent_local(case.prompt)
                response = f"Classified as: {intent.value}"
            except Exception:
                response = ""

        elapsed = time.time() - start

        # Score: keyword matching.
        response_lower = response.lower()
        hits = sum(
            1 for kw in case.expected_keywords
            if kw.lower() in response_lower
        )
        forbidden_hits = sum(
            1 for kw in case.forbidden_keywords
            if kw.lower() in response_lower
        )

        total = len(case.expected_keywords)
        keyword_score = hits / total if total > 0 else 1.0
        time_penalty = 0.0 if elapsed <= case.max_response_time_s else 0.2
        forbidden_penalty = 0.2 * forbidden_hits

        score = max(0.0, keyword_score - time_penalty - forbidden_penalty)
        passed = score >= 0.5 and len(errors) == 0

        return EvalResult(
            case_id=case.id,
            model=self.model or "default",
            passed=passed,
            score=round(score, 3),
            response_time_s=round(elapsed, 2),
            cost_usd=0.0,  # TODO: integrate with budget guard
            response_length=len(response),
            keyword_hits=hits,
            keyword_total=total,
            errors=errors,
        )

    def summary(self) -> Dict[str, Any]:
        """Generate evaluation summary."""
        if not self.results:
            return {"total": 0, "passed": 0, "failed": 0, "avg_score": 0}

        passed = sum(1 for r in self.results if r.passed)
        avg_score = sum(r.score for r in self.results) / len(self.results)
        avg_time = sum(r.response_time_s for r in self.results) / len(self.results)

        return {
            "total": len(self.results),
            "passed": passed,
            "failed": len(self.results) - passed,
            "pass_rate": round(passed / len(self.results), 3),
            "avg_score": round(avg_score, 3),
            "avg_response_time_s": round(avg_time, 2),
            "model": self.model or "default",
        }

    def to_langfuse(self) -> None:
        """Push results to Langfuse as scored observations."""
        try:
            from langfuse import Langfuse
            lf = Langfuse()
            for result in self.results:
                trace = lf.trace(name=f"eval-{result.case_id}")
                trace.score(
                    name="keyword_accuracy",
                    value=result.score,
                    comment=f"Hits: {result.keyword_hits}/{result.keyword_total}",
                )
                trace.score(
                    name="response_time",
                    value=max(0, 1.0 - result.response_time_s / 30.0),
                    comment=f"{result.response_time_s}s",
                )
            lf.flush()
            logger.info("Pushed %d eval results to Langfuse", len(self.results))
        except ImportError:
            logger.debug("Langfuse not available — skipping push")
        except Exception as e:
            logger.warning("Langfuse push failed: %s", e)


# =============================================================================
# CLI
# =============================================================================

def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="Hermes Eval Pipeline")
    sub = parser.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="Run evaluation dataset")
    run_p.add_argument("--dataset", default="code-review")
    run_p.add_argument("--model", default="")

    compare_p = sub.add_parser("compare", help="Compare models")
    compare_p.add_argument("--models", default="")
    compare_p.add_argument("--dataset", default="code-review")

    sub.add_parser("report", help="Show last results")
    sub.add_parser("list", help="List available datasets")

    args = parser.parse_args()

    if args.cmd == "list":
        for name, cases in DATASETS.items():
            print(f"  {name}: {len(cases)} cases")
        return

    if args.cmd == "run":
        engine = EvalEngine(model=args.model)
        results = engine.run_dataset(args.dataset)
        summary = engine.summary()

        print(f"\n=== Eval: {args.dataset} ===")
        for r in results:
            status = "PASS" if r.passed else "FAIL"
            print(f"  [{status}] {r.case_id}: score={r.score:.2f} time={r.response_time_s:.1f}s hits={r.keyword_hits}/{r.keyword_total}")

        print(f"\nSummary: {summary['passed']}/{summary['total']} passed ({summary['pass_rate']*100:.0f}%)")
        print(f"Avg score: {summary['avg_score']:.3f}")
        print(f"Avg time:  {summary['avg_response_time_s']:.1f}s")

        # Push to Langfuse if available.
        engine.to_langfuse()
        return

    if args.cmd == "compare":
        models = [m.strip() for m in args.models.split(",") if m.strip()]
        if not models:
            print("Specify --models: e.g. --models ollama/llama3.2:3b,anthropic/claude-sonnet")
            return

        for model in models:
            engine = EvalEngine(model=model)
            engine.run_dataset(args.dataset)
            s = engine.summary()
            print(f"  {model:40s}  pass={s['pass_rate']*100:.0f}%  score={s['avg_score']:.3f}  time={s['avg_response_time_s']:.1f}s")

    if args.cmd == "report":
        print("Use: python -m gateway.eval_pipeline run --dataset code-review")


if __name__ == "__main__":
    _cli()
