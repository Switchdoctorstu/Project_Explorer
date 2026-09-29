from __future__ import annotations

from ..model.project import Project


def build_summary_text(project: Project) -> str:
    tasks = project.tasks
    resources = project.resources

    milestones = sum(1 for task in tasks if task.is_milestone)
    critical = sum(1 for task in tasks if task.is_critical)
    summary_tasks = sum(1 for task in tasks if task.is_summary)

    return (
        f"Tasks: {len(tasks):,}    "
        f"Summary tasks: {summary_tasks:,}    "
        f"Milestones: {milestones:,}    "
        f"Critical tasks: {critical:,}    "
        f"Dependencies: {len(project.dependencies):,}    "
        f"Resources: {len(resources):,}    "
        f"Assignments: {len(project.assignments):,}"
    )
