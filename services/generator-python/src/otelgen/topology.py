from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from otelgen.contract.models import ComponentSpec, TopologyConfig


@dataclass
class ComponentNode:
    spec: ComponentSpec
    upstream: list[str] = field(default_factory=list)   # depends_on
    downstream: list[str] = field(default_factory=list)  # components that depend on this one


class Topology:
    """In-memory directed component graph built from a TopologyConfig."""

    def __init__(self, config: TopologyConfig) -> None:
        self._nodes: dict[str, ComponentNode] = {}
        for spec in config.components:
            self._nodes[spec.name] = ComponentNode(spec=spec, upstream=list(spec.depends_on))

        # Populate downstream edges
        for name, node in self._nodes.items():
            for dep in node.upstream:
                self._nodes[dep].downstream.append(name)

    @property
    def components(self) -> dict[str, ComponentNode]:
        return self._nodes

    def get(self, name: str) -> ComponentNode:
        try:
            return self._nodes[name]
        except KeyError as exc:
            raise KeyError(f"Component '{name}' not found in topology.") from exc

    def roots(self) -> list[ComponentNode]:
        """Components with no upstream dependencies."""
        return [n for n in self._nodes.values() if not n.upstream]

    def leaves(self) -> list[ComponentNode]:
        """Components with no downstream dependents."""
        return [n for n in self._nodes.values() if not n.downstream]

    def __iter__(self) -> Iterator[ComponentNode]:
        return iter(self._nodes.values())

    def __len__(self) -> int:
        return len(self._nodes)

    def topological_order(self) -> list[ComponentNode]:
        """Yield nodes in topological order (roots first) via Kahn's algorithm."""
        in_degree = {name: len(node.upstream) for name, node in self._nodes.items()}
        queue = [name for name, deg in in_degree.items() if deg == 0]
        result: list[ComponentNode] = []
        while queue:
            name = queue.pop(0)
            result.append(self._nodes[name])
            for downstream_name in self._nodes[name].downstream:
                in_degree[downstream_name] -= 1
                if in_degree[downstream_name] == 0:
                    queue.append(downstream_name)
        if len(result) != len(self._nodes):
            raise ValueError("Topology contains a dependency cycle.")
        return result
