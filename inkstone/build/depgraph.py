"""Which output was made from which inputs.

Nodes are plain strings with a kind prefix::

    source:posts/hello.md      a content file, relative to the content dir
    template:partials/nav.html a template, by name
    output:posts/index.html    a file in the output directory
    config, data               the configuration and the data directory

The graph only records and answers questions. Whether something has to be
rebuilt is decided by comparing hashes in the cache; the graph is what lets
the builder say *why*, and what the dev server uses to tell which pages a
changed file touches.
"""

from __future__ import annotations

from typing import Iterable, Iterator

SOURCE = "source"
TEMPLATE = "template"
OUTPUT = "output"
CONFIG = "config"
DATA = "data"
STATIC = "static"


def node(kind: str, name: str = "") -> str:
    return f"{kind}:{name}" if name else kind


def split_node(text: str) -> tuple[str, str]:
    kind, _, name = text.partition(":")
    return kind, name


class DepGraph:
    def __init__(self):
        self._needs: dict[str, set[str]] = {}
        self._needed_by: dict[str, set[str]] = {}

    def __len__(self) -> int:
        return len(self._needs)

    def __contains__(self, target: str) -> bool:
        return target in self._needs

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._needs))

    def __eq__(self, other) -> bool:
        if not isinstance(other, DepGraph):
            return NotImplemented
        return self._needs == other._needs

    def __repr__(self) -> str:
        edges = sum(len(deps) for deps in self._needs.values())
        return f"<DepGraph {len(self._needs)} targets, {edges} edges>"

    def set(self, target: str, dependencies: Iterable[str]) -> None:
        """Record what ``target`` was built from, replacing what was known."""
        self.discard(target)
        deps = {dep for dep in dependencies if dep != target}
        self._needs[target] = deps
        for dep in deps:
            self._needed_by.setdefault(dep, set()).add(target)

    def add(self, target: str, dependency: str) -> None:
        if dependency == target:
            return
        self._needs.setdefault(target, set()).add(dependency)
        self._needed_by.setdefault(dependency, set()).add(target)

    def discard(self, target: str) -> None:
        for dep in self._needs.pop(target, ()):
            users = self._needed_by.get(dep)
            if users is not None:
                users.discard(target)
                if not users:
                    del self._needed_by[dep]

    def dependencies(self, target: str) -> set[str]:
        return set(self._needs.get(target, ()))

    def dependents(self, dependency: str) -> set[str]:
        """Targets that list ``dependency`` directly."""
        return set(self._needed_by.get(dependency, ()))

    def affected(self, changed: Iterable[str]) -> set[str]:
        """Everything downstream of the changed nodes, following chains.

        A target can itself be a dependency (an included template, say), so
        this walks until nothing new turns up. Cycles are harmless.
        """
        seen: set[str] = set()
        todo = list(changed)
        while todo:
            current = todo.pop()
            for user in self._needed_by.get(current, ()):
                if user not in seen:
                    seen.add(user)
                    todo.append(user)
        return seen

    def affected_outputs(self, changed: Iterable[str]) -> set[str]:
        """Output paths (without the prefix) that depend on the changed nodes."""
        prefix = OUTPUT + ":"
        return {
            target[len(prefix) :]
            for target in self.affected(changed)
            if target.startswith(prefix)
        }

    def reasons(self, target: str, changed: Iterable[str]) -> list[str]:
        """Which of the changed nodes ``target`` depends on, directly or not."""
        changed = set(changed)
        found: set[str] = set()
        seen: set[str] = set()
        todo = [target]
        while todo:
            current = todo.pop()
            for dep in self._needs.get(current, ()):
                if dep in changed:
                    found.add(dep)
                if dep not in seen:
                    seen.add(dep)
                    todo.append(dep)
        return sorted(found)

    def prune(self, keep: Iterable[str]) -> None:
        """Forget every target that is not in ``keep``."""
        keep = set(keep)
        for target in [t for t in self._needs if t not in keep]:
            self.discard(target)

    def to_dict(self) -> dict[str, list[str]]:
        return {target: sorted(deps) for target, deps in sorted(self._needs.items())}

    @classmethod
    def from_dict(cls, data) -> DepGraph:
        """Rebuild a graph from to_dict() output; raises ValueError on junk."""
        if not isinstance(data, dict):
            raise ValueError("dependency graph must be a mapping")
        graph = cls()
        for target, deps in data.items():
            if not isinstance(target, str) or not isinstance(deps, list):
                raise ValueError(f"bad dependency entry for {target!r}")
            if not all(isinstance(dep, str) for dep in deps):
                raise ValueError(f"bad dependency list for {target!r}")
            graph.set(target, deps)
        return graph
