"""Plugin registry for integrations."""
from __future__ import annotations

from typing import Dict, Type

from app.plugins.base import Plugin

_REGISTRY: Dict[str, Type[Plugin]] = {}


def register_plugin(plugin_cls: Type[Plugin]) -> None:
    _REGISTRY[plugin_cls.name] = plugin_cls


def get_plugin(name: str) -> Type[Plugin] | None:
    return _REGISTRY.get(name)


def list_plugins() -> list[str]:
    return sorted(_REGISTRY.keys())


def clear_plugins() -> None:
    _REGISTRY.clear()
