"""
Hermes Plugin System — extensible crew/daemon/tool templates.

Users can create plugins in ~/.hermes/plugins/ or ./hermes_plugins/
with standardized YAML manifests. Plugins can define:
- Custom agent templates (crew definitions)
- Custom daemon job templates
- Custom tools (Python functions exposed to agents)
- Custom prompts/personas

Plugin Structure:
    ~/.hermes/plugins/
    └── my-plugin/
        ├── plugin.yaml          # Manifest
        ├── agents/              # Agent/crew definitions
        │   └── reviewer.yaml
        ├── tools/               # Custom tool functions
        │   └── lint_check.py
        ├── prompts/             # Custom system prompts
        │   └── strict-reviewer.txt
        └── templates/           # Daemon job templates
            └── nightly-audit.yaml

Usage:
    from gateway.plugin_system import PluginRegistry
    registry = PluginRegistry()
    registry.discover()                    # Auto-scan plugin dirs
    templates = registry.get_templates()   # All available templates
    tools = registry.get_tools()           # All available tools
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("hermes.plugins")


# ============================================================================
# Types
# ============================================================================

@dataclass
class PluginTool:
    """A custom tool exposed to the agent."""
    name: str
    description: str
    function: Callable
    plugin_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginTemplate:
    """A daemon job or crew template."""
    name: str
    description: str
    type: str  # 'daemon', 'crew', 'prompt'
    plugin_name: str
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginInfo:
    """Metadata about a loaded plugin."""
    name: str
    version: str
    description: str
    author: str
    path: str
    tools: List[PluginTool] = field(default_factory=list)
    templates: List[PluginTemplate] = field(default_factory=list)
    prompts: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True


# ============================================================================
# Plugin Registry
# ============================================================================

class PluginRegistry:
    """Discover, load, and manage plugins."""

    def __init__(self, extra_dirs: list[str] = None):
        self._plugins: Dict[str, PluginInfo] = {}
        self._tools: Dict[str, PluginTool] = {}
        self._templates: Dict[str, PluginTemplate] = {}
        self._search_dirs = self._default_dirs() + (extra_dirs or [])

    def _default_dirs(self) -> list[str]:
        """Default plugin search directories."""
        dirs = []
        # Global: ~/.hermes/plugins/
        global_dir = os.path.join(os.path.expanduser("~"), ".hermes", "plugins")
        if os.path.isdir(global_dir):
            dirs.append(global_dir)

        # Workspace-local: ./hermes_plugins/
        local_dir = os.path.join(os.getcwd(), "hermes_plugins")
        if os.path.isdir(local_dir):
            dirs.append(local_dir)

        # Also check HERMES_PLUGIN_PATH env var (colon/semicolon separated).
        env_path = os.environ.get("HERMES_PLUGIN_PATH", "")
        if env_path:
            sep = ";" if sys.platform == "win32" else ":"
            for p in env_path.split(sep):
                p = p.strip()
                if p and os.path.isdir(p):
                    dirs.append(p)

        return dirs

    def discover(self) -> int:
        """Scan all plugin directories and load plugins. Returns count loaded."""
        count = 0
        for search_dir in self._search_dirs:
            if not os.path.isdir(search_dir):
                continue
            for entry in os.scandir(search_dir):
                if entry.is_dir() and not entry.name.startswith("."):
                    try:
                        info = self._load_plugin(entry.path)
                        if info:
                            self._plugins[info.name] = info
                            count += 1
                    except Exception as e:
                        logger.warning("Failed to load plugin %s: %s", entry.name, e)

        logger.info("Discovered %d plugins from %d directories", count, len(self._search_dirs))
        return count

    def _load_plugin(self, plugin_dir: str) -> Optional[PluginInfo]:
        """Load a single plugin from its directory."""
        manifest_path = os.path.join(plugin_dir, "plugin.yaml")
        manifest_yml = os.path.join(plugin_dir, "plugin.yml")

        manifest = None
        for mp in (manifest_path, manifest_yml):
            if os.path.isfile(mp):
                manifest = self._parse_yaml(mp)
                break

        if manifest is None:
            # Try to auto-detect from directory contents.
            manifest = {"name": os.path.basename(plugin_dir)}

        info = PluginInfo(
            name=manifest.get("name", os.path.basename(plugin_dir)),
            version=manifest.get("version", "0.1.0"),
            description=manifest.get("description", ""),
            author=manifest.get("author", ""),
            path=plugin_dir,
            enabled=manifest.get("enabled", True),
        )

        if not info.enabled:
            logger.debug("Plugin %s is disabled", info.name)
            return None

        # Load tools.
        tools_dir = os.path.join(plugin_dir, "tools")
        if os.path.isdir(tools_dir):
            info.tools = self._load_tools(tools_dir, info.name)
            for tool in info.tools:
                self._tools[f"{info.name}.{tool.name}"] = tool

        # Load templates.
        templates_dir = os.path.join(plugin_dir, "templates")
        if os.path.isdir(templates_dir):
            info.templates = self._load_templates(templates_dir, info.name)
            for tmpl in info.templates:
                self._templates[f"{info.name}.{tmpl.name}"] = tmpl

        # Load agents/crews.
        agents_dir = os.path.join(plugin_dir, "agents")
        if os.path.isdir(agents_dir):
            agent_templates = self._load_templates(agents_dir, info.name, default_type="crew")
            info.templates.extend(agent_templates)
            for tmpl in agent_templates:
                self._templates[f"{info.name}.{tmpl.name}"] = tmpl

        # Load prompts.
        prompts_dir = os.path.join(plugin_dir, "prompts")
        if os.path.isdir(prompts_dir):
            info.prompts = self._load_prompts(prompts_dir)

        logger.info(
            "Loaded plugin: %s v%s (%d tools, %d templates, %d prompts)",
            info.name, info.version,
            len(info.tools), len(info.templates), len(info.prompts),
        )
        return info

    def _load_tools(self, tools_dir: str, plugin_name: str) -> List[PluginTool]:
        """Load Python tool files from a directory."""
        tools = []
        for f in Path(tools_dir).glob("*.py"):
            if f.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"hermes_plugin_{plugin_name}_{f.stem}", str(f)
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # Look for functions decorated with @tool or having TOOL_META.
                    for attr_name in dir(module):
                        obj = getattr(module, attr_name)
                        if callable(obj) and hasattr(obj, "TOOL_META"):
                            meta = obj.TOOL_META
                            tools.append(PluginTool(
                                name=meta.get("name", attr_name),
                                description=meta.get("description", ""),
                                function=obj,
                                plugin_name=plugin_name,
                                parameters=meta.get("parameters", {}),
                            ))
                        elif callable(obj) and not attr_name.startswith("_") and obj.__module__ == module.__name__:
                            # Auto-register public functions.
                            tools.append(PluginTool(
                                name=attr_name,
                                description=getattr(obj, "__doc__", "") or "",
                                function=obj,
                                plugin_name=plugin_name,
                            ))
            except Exception as e:
                logger.warning("Failed to load tool %s: %s", f.name, e)
        return tools

    def _load_templates(
        self, dir_path: str, plugin_name: str, default_type: str = "daemon"
    ) -> List[PluginTemplate]:
        """Load YAML template files."""
        templates = []
        for ext in ("*.yaml", "*.yml"):
            for f in Path(dir_path).glob(ext):
                try:
                    data = self._parse_yaml(str(f))
                    if data:
                        templates.append(PluginTemplate(
                            name=data.get("name", f.stem),
                            description=data.get("description", ""),
                            type=data.get("type", default_type),
                            plugin_name=plugin_name,
                            config=data,
                        ))
                except Exception as e:
                    logger.warning("Failed to load template %s: %s", f.name, e)
        return templates

    def _load_prompts(self, prompts_dir: str) -> Dict[str, str]:
        """Load prompt text files."""
        prompts = {}
        for f in Path(prompts_dir).glob("*"):
            if f.suffix in (".txt", ".md", ".prompt"):
                try:
                    prompts[f.stem] = f.read_text(encoding="utf-8")
                except Exception:
                    pass
        return prompts

    def _parse_yaml(self, path: str) -> Optional[Dict[str, Any]]:
        """Parse a YAML file, falling back to basic parsing if PyYAML not installed."""
        try:
            import yaml
            with open(path, encoding="utf-8") as fh:
                return yaml.safe_load(fh)
        except ImportError:
            # Minimal YAML-like parser for simple key: value files.
            result = {}
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#") and ":" in line:
                        key, _, value = line.partition(":")
                        result[key.strip()] = value.strip()
            return result if result else None
        except Exception:
            return None

    # ========================================================================
    # Public API
    # ========================================================================

    def get_plugins(self) -> Dict[str, PluginInfo]:
        """Get all loaded plugins."""
        return dict(self._plugins)

    def get_tools(self) -> Dict[str, PluginTool]:
        """Get all available tools across plugins."""
        return dict(self._tools)

    def get_templates(self, type_filter: str = None) -> Dict[str, PluginTemplate]:
        """Get all templates, optionally filtered by type."""
        if type_filter:
            return {k: v for k, v in self._templates.items() if v.type == type_filter}
        return dict(self._templates)

    def get_prompts(self) -> Dict[str, str]:
        """Get all custom prompts across plugins."""
        all_prompts = {}
        for plugin in self._plugins.values():
            for name, content in plugin.prompts.items():
                all_prompts[f"{plugin.name}.{name}"] = content
        return all_prompts

    def call_tool(self, tool_name: str, **kwargs) -> Any:
        """Call a plugin tool by its qualified name."""
        tool = self._tools.get(tool_name)
        if not tool:
            raise KeyError(f"Tool not found: {tool_name}")
        return tool.function(**kwargs)

    def create_plugin_scaffold(self, name: str, directory: str = None) -> str:
        """Create a new plugin scaffold.

        Returns the path to the created plugin directory.
        """
        base_dir = directory or os.path.join(
            os.path.expanduser("~"), ".hermes", "plugins"
        )
        plugin_dir = os.path.join(base_dir, name)
        os.makedirs(plugin_dir, exist_ok=True)

        # Create subdirectories.
        for subdir in ("tools", "templates", "prompts", "agents"):
            os.makedirs(os.path.join(plugin_dir, subdir), exist_ok=True)

        # Create manifest.
        manifest = f"""# {name} — Hermes Agent Plugin
name: {name}
version: 0.1.0
description: Custom plugin for Hermes Agent
author: ""
enabled: true
"""
        with open(os.path.join(plugin_dir, "plugin.yaml"), "w", encoding="utf-8") as fh:
            fh.write(manifest)

        # Create example tool.
        example_tool = '''"""Example tool for the agent."""


def hello_world(name: str = "World") -> str:
    """Say hello — the agent can call this tool."""
    return f"Hello, {name}! This is a custom plugin tool."


# Add TOOL_META to customize how the tool appears to the agent.
hello_world.TOOL_META = {
    "name": "hello_world",
    "description": "Say hello from the custom plugin",
    "parameters": {"name": {"type": "string", "default": "World"}},
}
'''
        with open(os.path.join(plugin_dir, "tools", "example.py"), "w", encoding="utf-8") as fh:
            fh.write(example_tool)

        # Create example template.
        example_template = f"""# Example daemon job template
name: {name}-watcher
description: Example watcher job from {name} plugin
type: daemon
schedule: "*/30 * * * *"
prompt: "Check the workspace for any issues and report."
"""
        with open(os.path.join(plugin_dir, "templates", "example.yaml"), "w", encoding="utf-8") as fh:
            fh.write(example_template)

        # Create example prompt.
        example_prompt = f"""You are a custom agent from the {name} plugin.
Follow these guidelines:
1. Be helpful and precise.
2. Follow the project's coding standards.
3. Always explain your reasoning.
"""
        with open(os.path.join(plugin_dir, "prompts", "default.txt"), "w", encoding="utf-8") as fh:
            fh.write(example_prompt)

        logger.info("Created plugin scaffold: %s", plugin_dir)
        return plugin_dir

    def to_api_response(self) -> Dict[str, Any]:
        """Serialize plugin data for API response."""
        return {
            "plugins": [
                {
                    "name": p.name,
                    "version": p.version,
                    "description": p.description,
                    "author": p.author,
                    "tools": len(p.tools),
                    "templates": len(p.templates),
                    "prompts": len(p.prompts),
                    "enabled": p.enabled,
                }
                for p in self._plugins.values()
            ],
            "total_tools": len(self._tools),
            "total_templates": len(self._templates),
        }


# ============================================================================
# Singleton
# ============================================================================

_registry: Optional[PluginRegistry] = None


def get_plugin_registry() -> PluginRegistry:
    """Get or create the global plugin registry."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
        _registry.discover()
    return _registry


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Hermes Plugin Manager")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list", help="List installed plugins")
    sub.add_parser("tools", help="List available tools")
    sub.add_parser("templates", help="List available templates")

    create_p = sub.add_parser("create", help="Create new plugin scaffold")
    create_p.add_argument("name", help="Plugin name")
    create_p.add_argument("--dir", default=None, help="Parent directory")

    args = parser.parse_args()
    registry = PluginRegistry()
    registry.discover()

    if args.cmd == "list":
        plugins = registry.get_plugins()
        if not plugins:
            print("No plugins found.")
            print(f"Create one: python -m gateway.plugin_system create my-plugin")
        else:
            for name, info in plugins.items():
                print(f"  {name} v{info.version}")
                print(f"    {info.description}")
                print(f"    Tools: {len(info.tools)}, Templates: {len(info.templates)}, Prompts: {len(info.prompts)}")

    elif args.cmd == "tools":
        tools = registry.get_tools()
        for name, tool in tools.items():
            print(f"  {name}: {tool.description}")

    elif args.cmd == "templates":
        templates = registry.get_templates()
        for name, tmpl in templates.items():
            print(f"  [{tmpl.type}] {name}: {tmpl.description}")

    elif args.cmd == "create":
        path = registry.create_plugin_scaffold(args.name, args.dir)
        print(f"Created plugin scaffold at: {path}")
        print(f"  Edit plugin.yaml to configure your plugin.")
        print(f"  Add tools in tools/, templates in templates/, prompts in prompts/")
    else:
        print("Usage: python -m gateway.plugin_system [list|tools|templates|create]")
