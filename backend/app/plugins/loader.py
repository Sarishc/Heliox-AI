"""Dynamic plugin loader."""
from __future__ import annotations

import importlib
from typing import Iterable

from app.plugins.registry import list_plugins

DEFAULT_PLUGINS = [
    "app.plugins.aws_plugin",
    "app.plugins.gcp_plugin",
    "app.plugins.onprem_plugin",
]


def load_plugins(modules: Iterable[str]) -> list[str]:
    """
    Import plugin modules to register plugins.
    
    Modules should call register_plugin() during import.
    """
    for module_path in modules:
        importlib.import_module(module_path)
    return list_plugins()


def load_default_plugins() -> list[str]:
    return load_plugins(DEFAULT_PLUGINS)
