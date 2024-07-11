"""Plugins: classes with hook methods that the builder calls at fixed points."""

from __future__ import annotations

from .base import Plugin, hook_names
from .manager import PluginManager

__all__ = ["Plugin", "PluginManager", "hook_names"]
