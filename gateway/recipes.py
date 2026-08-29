"""YAML Recipes — Composable Agent Workflows.

Recipes are YAML-defined sequences of agent actions that can be
triggered with a single command. Users can create, share, and
import recipes.

Example recipe:

```yaml
name: code-review
description: Run full code review on staged changes
steps:
  - action: shell
    command: git diff --staged
    output: diff_output

  - action: agent
    prompt: |
      Review this code diff for:
      1. Bugs and logic errors
      2. Security issues
      3. Performance concerns
      4. Style violations
      Diff: {{ diff_output }}
    output: review

  - action: mcp_app
    app: diff-viewer
    data:
      diff: "{{ diff_output }}"
```

Part of Phase 7: Advanced Features.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Try to import YAML parser
try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


@dataclass
class RecipeStep:
    """A single step in a recipe."""
    action: str               # "shell", "agent", "mcp_app", "wait", "condition"
    command: str = ""         # For shell actions
    prompt: str = ""          # For agent actions
    app: str = ""             # For mcp_app actions
    data: Dict[str, Any] = field(default_factory=dict)
    output: str = ""          # Variable name to store output
    condition: str = ""       # For conditional execution
    timeout: int = 300        # Seconds


@dataclass
class Recipe:
    """A composable agent workflow."""
    name: str
    description: str = ""
    author: str = ""
    version: str = "1.0"
    tags: List[str] = field(default_factory=list)
    steps: List[RecipeStep] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, content: str) -> "Recipe":
        """Parse a recipe from YAML string."""
        if yaml is None:
            raise ImportError("PyYAML is required for recipes: pip install pyyaml")
        data = yaml.safe_load(content)
        steps = []
        for step_data in data.get("steps", []):
            steps.append(RecipeStep(**{
                k: step_data[k]
                for k in RecipeStep.__dataclass_fields__
                if k in step_data
            }))
        return cls(
            name=data.get("name", "Untitled"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            version=str(data.get("version", "1.0")),
            tags=data.get("tags", []),
            steps=steps,
            variables=data.get("variables", {}),
        )

    @classmethod
    def from_file(cls, path: Path) -> "Recipe":
        """Load a recipe from a YAML file."""
        return cls.from_yaml(path.read_text(encoding="utf-8"))


class RecipeRunner:
    """Executes a recipe step by step."""

    def __init__(self, recipe: Recipe):
        self.recipe = recipe
        self.context: Dict[str, Any] = dict(recipe.variables)
        self.current_step = 0
        self.results: List[Dict[str, Any]] = []

    def _interpolate(self, text: str) -> str:
        """Replace {{ variable }} with context values."""
        def replacer(match):
            var_name = match.group(1).strip()
            return str(self.context.get(var_name, match.group(0)))
        return re.sub(r"\{\{\s*(\w+)\s*\}\}", replacer, text)

    async def run_step(self, step: RecipeStep) -> Dict[str, Any]:
        """Execute a single recipe step. Returns the step result."""
        result: Dict[str, Any] = {
            "action": step.action,
            "status": "pending",
        }

        if step.condition:
            condition_val = self.context.get(step.condition)
            if not condition_val:
                result["status"] = "skipped"
                return result

        if step.action == "shell":
            cmd = self._interpolate(step.command)
            result["command"] = cmd
            result["status"] = "ready"
            # Actual execution is delegated to the agent runtime

        elif step.action == "agent":
            prompt = self._interpolate(step.prompt)
            result["prompt"] = prompt
            result["status"] = "ready"

        elif step.action == "mcp_app":
            data = {}
            for k, v in step.data.items():
                data[k] = self._interpolate(str(v)) if isinstance(v, str) else v
            result["app"] = step.app
            result["data"] = data
            result["status"] = "ready"

        elif step.action == "wait":
            result["timeout"] = step.timeout
            result["status"] = "ready"

        if step.output:
            result["output_var"] = step.output

        self.results.append(result)
        return result

    def store_output(self, var_name: str, value: Any) -> None:
        """Store a step's output in the context."""
        self.context[var_name] = value


class RecipeLibrary:
    """Manages recipe discovery and loading."""

    def __init__(self, recipes_dir: Path):
        self._dir = recipes_dir

    def list_recipes(self) -> List[Dict[str, str]]:
        """List all available recipes."""
        recipes = []
        if not self._dir.exists():
            return recipes
        for f in self._dir.glob("*.yaml"):
            try:
                recipe = Recipe.from_file(f)
                recipes.append({
                    "name": recipe.name,
                    "description": recipe.description,
                    "file": str(f),
                    "steps": len(recipe.steps),
                    "tags": recipe.tags,
                })
            except Exception:
                logger.warning("Failed to load recipe: %s", f)
        return recipes

    def load(self, name: str) -> Optional[Recipe]:
        """Load a recipe by name."""
        for f in self._dir.glob("*.yaml"):
            try:
                recipe = Recipe.from_file(f)
                if recipe.name == name:
                    return recipe
            except Exception:
                continue
        return None
