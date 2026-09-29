from __future__ import annotations

from dataclasses import dataclass

from ..model.project import Project


@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: str
    label: str
    attributes: dict[str, str | int | bool]


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    kind: str
    attributes: dict[str, str | int | bool]


def build_overlay_graph(project: Project) -> dict[str, object]:
    """
    Build a stable, serialisable graph payload for downstream overlay tooling.

    The payload is intentionally simple: node and edge records with explicit
    kinds and attributes so it can be consumed by networkx or external systems.
    """
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    project_node_id = _project_node_id(project)
    nodes.append(
        GraphNode(
            id=project_node_id,
            kind="project",
            label=project.title or "Untitled Project",
            attributes={
                "title": project.title,
                "source_path": project.source_path,
            },
        )
    )

    for task in project.tasks:
        task_node_id = _task_node_id(task.unique_id)
        nodes.append(
            GraphNode(
                id=task_node_id,
                kind="task",
                label=task.display_label(),
                attributes={
                    "unique_id": task.unique_id,
                    "id": task.id,
                    "wbs": task.wbs,
                    "outline_level": task.outline_level,
                    "is_summary": task.is_summary,
                    "is_milestone": task.is_milestone,
                    "is_critical": task.is_critical,
                    "is_active": task.is_active,
                    "start": task.start,
                    "finish": task.finish,
                    "percent_complete": task.percent_complete,
                },
            )
        )

        if task.parent_unique_id is None:
            edges.append(
                GraphEdge(
                    source=project_node_id,
                    target=task_node_id,
                    kind="contains",
                    attributes={"role": "root_task"},
                )
            )
        else:
            edges.append(
                GraphEdge(
                    source=_task_node_id(task.parent_unique_id),
                    target=task_node_id,
                    kind="hierarchy",
                    attributes={"role": "parent_child"},
                )
            )

    for dependency in project.dependencies:
        if dependency.predecessor_unique_id is None or dependency.successor_unique_id is None:
            continue

        edges.append(
            GraphEdge(
                source=_task_node_id(dependency.predecessor_unique_id),
                target=_task_node_id(dependency.successor_unique_id),
                kind="dependency",
                attributes={
                    "type": dependency.relation_type,
                    "lag": dependency.lag,
                },
            )
        )

    seen_resources: set[int] = set()
    for resource in project.resources:
        if resource.unique_id in seen_resources:
            continue
        seen_resources.add(resource.unique_id)

        nodes.append(
            GraphNode(
                id=_resource_node_id(resource.unique_id),
                kind="resource",
                label=resource.name or resource.id,
                attributes={
                    "unique_id": resource.unique_id,
                    "id": resource.id,
                    "type": resource.resource_type,
                    "group": resource.group,
                },
            )
        )

        edges.append(
            GraphEdge(
                source=project_node_id,
                target=_resource_node_id(resource.unique_id),
                kind="contains",
                attributes={"role": "resource"},
            )
        )

    for assignment in project.assignments:
        if assignment.task_unique_id is None or assignment.resource_unique_id is None:
            continue

        edges.append(
            GraphEdge(
                source=_resource_node_id(assignment.resource_unique_id),
                target=_task_node_id(assignment.task_unique_id),
                kind="assignment",
                attributes={
                    "units": assignment.units,
                    "work": assignment.work,
                    "actual_work": assignment.actual_work,
                    "remaining_work": assignment.remaining_work,
                    "cost": assignment.cost,
                },
            )
        )

    return {
        "nodes": [_node_as_dict(node) for node in nodes],
        "edges": [_edge_as_dict(edge) for edge in edges],
        "meta": {
            "task_count": len(project.tasks),
            "resource_count": len(project.resources),
            "dependency_count": len(project.dependencies),
            "assignment_count": len(project.assignments),
        },
    }


def to_networkx_compatible(project: Project) -> tuple[list[tuple[str, dict]], list[tuple[str, str, dict]]]:
    """Return nodes and edges tuples that can be passed directly into networkx."""
    payload = build_overlay_graph(project)
    node_tuples = [(node["id"], {k: v for k, v in node.items() if k != "id"}) for node in payload["nodes"]]
    edge_tuples = [
        (edge["source"], edge["target"], {k: v for k, v in edge.items() if k not in ("source", "target")})
        for edge in payload["edges"]
    ]
    return node_tuples, edge_tuples


def _project_node_id(project: Project) -> str:
    if project.source_path:
        return f"project:{project.source_path}"
    return "project:current"


def _task_node_id(unique_id: int) -> str:
    return f"task:{unique_id}"


def _resource_node_id(unique_id: int) -> str:
    return f"resource:{unique_id}"


def _node_as_dict(node: GraphNode) -> dict[str, object]:
    return {
        "id": node.id,
        "kind": node.kind,
        "label": node.label,
        "attributes": node.attributes,
    }


def _edge_as_dict(edge: GraphEdge) -> dict[str, object]:
    return {
        "source": edge.source,
        "target": edge.target,
        "kind": edge.kind,
        "attributes": edge.attributes,
    }
