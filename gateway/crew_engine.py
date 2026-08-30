"""
CrewAI Multi-Agent Engine for Hermes — Role-based agent teams.

Orchestrates specialist agents (Planner, Coder, Reviewer, Tester)
using CrewAI. The LangGraph engine routes tasks to the right crew;
each crew member uses a role-optimized model via LiteLLM.

Pre-built crews:
  - code-review: Senior Reviewer + Test Writer + Doc Writer
  - full-stack: Architect + Frontend Dev + Backend Dev + QA
  - debug-fix: Bug Hunter + Root Cause Analyst + Fix Engineer
  - research: Web Researcher + Source Verifier + Synthesizer

Usage:
    from gateway.crew_engine import CrewEngine, get_crew_engine

    engine = get_crew_engine()
    result = await engine.run_crew("code-review", task_description="Review auth.py")
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hermes.crew_engine")

# Try importing CrewAI (with Python 3.14 compat shim).
try:
    import gateway.crewai_compat  # noqa: F401  # patches langchain for 3.14
    from crewai import Agent, Crew, Task, Process
    from crewai.project import CrewBase

    CREWAI_AVAILABLE = True
except Exception as _crewai_err:
    CREWAI_AVAILABLE = False
    # Python 3.14 triggers TypeError in Pydantic type annotations.
    # This is a known incompatibility with crewai 0.11.x + langchain 0.3.x.
    logger.info("CrewAI not available (%s) — using built-in agent orchestration", type(_crewai_err).__name__)

# Try importing LiteLLM for model routing.
try:
    import litellm
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False

# Langfuse tracing.
try:
    from langfuse.decorators import observe
except ImportError:
    def observe(*a, **kw):
        def w(fn): return fn
        if a and callable(a[0]): return a[0]
        return w


# ============================================================================
# Agent Role Definitions
# ============================================================================

@dataclass
class AgentRole:
    """Definition of a specialist agent role."""
    role: str
    goal: str
    backstory: str
    model: str = "ollama/llama3.2:3b"  # Default: free local
    temperature: float = 0.3
    verbose: bool = False
    allow_delegation: bool = False
    max_iter: int = 10
    tools: List[str] = field(default_factory=list)


# Pre-defined agent roles.
AGENT_ROLES: Dict[str, AgentRole] = {
    # --- Code Review Crew ---
    "senior_reviewer": AgentRole(
        role="Senior Code Reviewer",
        goal="Find bugs, security vulnerabilities, performance issues, and code smells",
        backstory=(
            "You are a staff engineer with 15 years of experience across "
            "Python, TypeScript, Go, and Rust. You've reviewed thousands of PRs "
            "and have an eye for subtle bugs that junior developers miss. You "
            "focus on correctness, security, and maintainability."
        ),
        model="anthropic/claude-sonnet-4-20250514",
        tools=["read_file", "search_code"],
    ),
    "test_writer": AgentRole(
        role="Test Engineer",
        goal="Write comprehensive unit and integration tests for uncovered code",
        backstory=(
            "You are a QA specialist who believes untested code is broken code. "
            "You write pytest/jest tests that cover edge cases, error paths, and "
            "boundary conditions. You aim for >80% coverage on critical paths."
        ),
        model="anthropic/claude-sonnet-4-20250514",
        tools=["read_file", "write_file", "run_tests"],
    ),
    "doc_writer": AgentRole(
        role="Documentation Writer",
        goal="Write clear docstrings, README updates, and API documentation",
        backstory=(
            "You are a technical writer who makes complex code accessible. "
            "You write concise docstrings, helpful comments, and clear README "
            "sections. You never write 'self-explanatory' — you explain everything."
        ),
        model="ollama/llama3.2:3b",  # Cheap — docs don't need big model
    ),

    # --- Full-Stack Crew ---
    "architect": AgentRole(
        role="Software Architect",
        goal="Design scalable, maintainable system architecture",
        backstory=(
            "You are a principal engineer who designs systems at scale. You "
            "think in terms of modules, interfaces, and data flow. You prefer "
            "composition over inheritance and make decisions that reduce "
            "future complexity."
        ),
        model="anthropic/claude-sonnet-4-20250514",
    ),
    "frontend_dev": AgentRole(
        role="Frontend Developer",
        goal="Build beautiful, responsive UI components",
        backstory=(
            "You are a React/TypeScript expert who builds pixel-perfect UIs. "
            "You use modern patterns (hooks, suspense, server components) and "
            "write accessible, performant code. You love CSS animations."
        ),
        model="anthropic/claude-sonnet-4-20250514",
        tools=["read_file", "write_file"],
    ),
    "backend_dev": AgentRole(
        role="Backend Developer",
        goal="Build robust APIs, database schemas, and server logic",
        backstory=(
            "You are a Python/Node.js backend expert who builds production-grade "
            "APIs. You handle auth, caching, rate limiting, and database "
            "optimization. You write defensive code with proper error handling."
        ),
        model="anthropic/claude-sonnet-4-20250514",
        tools=["read_file", "write_file", "run_command"],
    ),

    # --- Debug Crew ---
    "bug_hunter": AgentRole(
        role="Bug Hunter",
        goal="Reproduce and isolate the root cause of bugs",
        backstory=(
            "You are a debugging specialist who can find bugs by reading code. "
            "You trace execution paths, check edge cases, and find the exact "
            "line where things go wrong. You always verify with a test."
        ),
        model="anthropic/claude-sonnet-4-20250514",
        tools=["read_file", "search_code", "run_command"],
    ),
    "fix_engineer": AgentRole(
        role="Fix Engineer",
        goal="Write minimal, correct fixes for identified bugs",
        backstory=(
            "You fix bugs with surgical precision. You change the minimum "
            "number of lines needed, never introduce regressions, and always "
            "add a regression test. You follow the existing code style."
        ),
        model="anthropic/claude-sonnet-4-20250514",
        tools=["read_file", "write_file", "run_tests"],
    ),

    # --- Research Crew ---
    "web_researcher": AgentRole(
        role="Web Researcher",
        goal="Find authoritative information from the web",
        backstory=(
            "You are a research analyst who finds answers from documentation, "
            "Stack Overflow, GitHub issues, and blog posts. You cite your "
            "sources and distinguish between official docs and community answers."
        ),
        model="ollama/llama3.2:3b",  # Cheap — just search and summarize
        tools=["web_search", "read_url"],
    ),
    "synthesizer": AgentRole(
        role="Research Synthesizer",
        goal="Combine research findings into actionable recommendations",
        backstory=(
            "You take raw research data and synthesize it into clear, "
            "actionable recommendations. You compare approaches, weigh "
            "trade-offs, and make a final recommendation with reasoning."
        ),
        model="ollama/llama3.2:3b",
    ),
}


# ============================================================================
# Crew Definitions (YAML-like configs)
# ============================================================================

@dataclass
class CrewConfig:
    """Configuration for a pre-built crew."""
    name: str
    description: str
    agents: List[str]       # Agent role keys from AGENT_ROLES
    process: str = "sequential"  # sequential or hierarchical
    verbose: bool = False
    max_rpm: int = 10       # Rate limit for API calls


CREW_CONFIGS: Dict[str, CrewConfig] = {
    "code-review": CrewConfig(
        name="Code Review Crew",
        description="Review code for bugs, write tests, update docs",
        agents=["senior_reviewer", "test_writer", "doc_writer"],
        process="sequential",
    ),
    "full-stack": CrewConfig(
        name="Full-Stack Development Crew",
        description="Design, build frontend + backend, then QA",
        agents=["architect", "frontend_dev", "backend_dev", "test_writer"],
        process="sequential",
    ),
    "debug-fix": CrewConfig(
        name="Debug & Fix Crew",
        description="Hunt the bug, find root cause, write fix + test",
        agents=["bug_hunter", "fix_engineer", "test_writer"],
        process="sequential",
    ),
    "research": CrewConfig(
        name="Research Crew",
        description="Search the web, verify sources, synthesize findings",
        agents=["web_researcher", "synthesizer"],
        process="sequential",
    ),
}


# ============================================================================
# Crew Engine
# ============================================================================

class CrewEngine:
    """Manages CrewAI crews for Hermes Agent.

    Creates and runs pre-built or custom crews with role-optimized models.
    """

    def __init__(self):
        self._active_crew: Optional[str] = None
        self._active_agents: List[str] = []

    @property
    def available_crews(self) -> Dict[str, CrewConfig]:
        return CREW_CONFIGS

    @property
    def active_crew_name(self) -> Optional[str]:
        return self._active_crew

    @property
    def active_agents(self) -> List[str]:
        return self._active_agents

    @observe(name="crew_run")
    def run_crew(
        self,
        crew_name: str,
        task_description: str,
        context: str = "",
        workspace_path: str = "",
    ) -> Dict[str, Any]:
        """Run a pre-built crew on a task.

        Args:
            crew_name: Key from CREW_CONFIGS (e.g., "code-review").
            task_description: What the crew should do.
            context: Additional context (file contents, error logs).
            workspace_path: Project root for file operations.

        Returns:
            Dict with crew output, agent logs, and metadata.
        """
        if not CREWAI_AVAILABLE:
            return self._fallback_run(crew_name, task_description, context)

        config = CREW_CONFIGS.get(crew_name)
        if not config:
            return {"error": f"Unknown crew: {crew_name}. Available: {list(CREW_CONFIGS.keys())}"}

        self._active_crew = crew_name
        self._active_agents = config.agents

        try:
            # Build CrewAI agents.
            agents = []
            for role_key in config.agents:
                role = AGENT_ROLES.get(role_key)
                if not role:
                    continue
                agent = Agent(
                    role=role.role,
                    goal=role.goal,
                    backstory=role.backstory,
                    llm=role.model,
                    verbose=role.verbose or config.verbose,
                    allow_delegation=role.allow_delegation,
                    max_iter=role.max_iter,
                )
                agents.append(agent)

            if not agents:
                return {"error": "No valid agents for this crew"}

            # Build task.
            full_description = task_description
            if context:
                full_description += f"\n\nContext:\n{context}"
            if workspace_path:
                full_description += f"\n\nWorkspace: {workspace_path}"

            task = Task(
                description=full_description,
                expected_output="Detailed analysis and actionable results",
                agent=agents[0],  # Primary agent owns the task.
            )

            # Build and run crew.
            process = Process.sequential if config.process == "sequential" else Process.hierarchical
            crew = Crew(
                agents=agents,
                tasks=[task],
                process=process,
                verbose=config.verbose,
                max_rpm=config.max_rpm,
            )

            result = crew.kickoff()

            return {
                "crew": crew_name,
                "output": str(result),
                "agents_used": [r for r in config.agents],
                "process": config.process,
            }

        except Exception as e:
            logger.error("Crew execution failed: %s", e)
            return {"error": str(e), "crew": crew_name}
        finally:
            self._active_crew = None
            self._active_agents = []

    def _fallback_run(self, crew_name: str, task: str, context: str) -> Dict[str, Any]:
        """Fallback when CrewAI is not installed — single-agent mode."""
        return {
            "crew": crew_name,
            "output": f"[CrewAI not installed] Task would be handled by: {crew_name}\n"
                      f"Agents: {CREW_CONFIGS.get(crew_name, CrewConfig('?','?',[])).agents}\n"
                      f"Task: {task}",
            "fallback": True,
        }

    def get_crew_status(self) -> Dict[str, Any]:
        """Get current crew execution status (for UI panel)."""
        return {
            "active_crew": self._active_crew,
            "active_agents": self._active_agents,
            "available_crews": {
                k: {"name": v.name, "description": v.description, "agents": v.agents}
                for k, v in CREW_CONFIGS.items()
            },
            "crewai_available": CREWAI_AVAILABLE,
        }

    def list_agents(self) -> List[Dict[str, str]]:
        """List all available agent roles (for UI display)."""
        return [
            {
                "key": key,
                "role": role.role,
                "goal": role.goal,
                "model": role.model,
            }
            for key, role in AGENT_ROLES.items()
        ]


# ============================================================================
# Singleton
# ============================================================================

_engine: Optional[CrewEngine] = None


def get_crew_engine() -> CrewEngine:
    """Get or create the global crew engine."""
    global _engine
    if _engine is None:
        _engine = CrewEngine()
    return _engine
