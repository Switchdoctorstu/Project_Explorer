from __future__ import annotations

"""Build a deterministic 3D Gantt payload from project data and schedule analysis."""

from dataclasses import asdict
from datetime import datetime

from ..model.project import Project
from .schedule import ScheduleAnalysisOptions, analyse_schedule


def build_gantt_payload(
    project: Project,
    options: ScheduleAnalysisOptions | None = None,
) -> dict[str, object]:
    analysis = analyse_schedule(project, options)

    task_records = []
    for task in sorted(project.tasks, key=lambda item: item.unique_id):
        uid = task.unique_id
        tm = analysis.task_metrics.get(uid)
        bv = analysis.baseline_variance.get(uid)
        dm = analysis.dependency_metrics.get(uid)
        bottleneck = analysis.bottleneck_scores.get(uid)

        if tm is None:
            continue

        resource_ids = sorted(
            {
                assignment.resource_unique_id
                for assignment in project.assignments
                if assignment.task_unique_id == uid and assignment.resource_unique_id is not None
            }
        )

        predecessors = sorted(
            {
                dep.predecessor_unique_id
                for dep in project.dependencies
                if dep.successor_unique_id == uid and dep.predecessor_unique_id is not None
            }
        )
        successors = sorted(
            {
                dep.successor_unique_id
                for dep in project.dependencies
                if dep.predecessor_unique_id == uid and dep.successor_unique_id is not None
            }
        )

        task_records.append(
            {
                "id": task.id,
                "unique_id": uid,
                "label": task.display_label(),
                "wbs": task.wbs,
                "outline_level": task.outline_level,
                "parent_unique_id": task.parent_unique_id,
                "start": task.start,
                "finish": task.finish,
                "duration_days": _duration_days(task.duration, task.start, task.finish),
                "early_start": tm.early_start,
                "early_finish": tm.early_finish,
                "late_start": tm.late_start,
                "late_finish": tm.late_finish,
                "total_float_days": tm.total_float_days,
                "free_float_days": tm.free_float_days,
                "is_critical": tm.is_critical,
                "is_near_critical": tm.is_near_critical,
                "is_summary": task.is_summary,
                "is_milestone": task.is_milestone,
                "is_active": task.is_active,
                "percent_complete": _number(task.percent_complete),
                "cost": _number(task.cost),
                "actual_cost": _number(task.actual_cost),
                "remaining_cost": _number(task.remaining_cost),
                "work": _number(task.work),
                "actual_work": _number(task.actual_work),
                "remaining_work": _number(task.remaining_work),
                "resource_unique_ids": resource_ids,
                "baseline_start": task.baseline_start,
                "baseline_finish": task.baseline_finish,
                "finish_variance_days": bv.finish_variance_days if bv else None,
                "bottleneck_score": bottleneck.score if bottleneck else 0.0,
                "bottleneck_components": bottleneck.components if bottleneck else {},
                "constraint_type": tm.constraint_type,
                "constraint_date": tm.constraint_date,
                "unresolved_constraint": tm.unresolved_constraint,
                "predecessor_unique_ids": predecessors,
                "successor_unique_ids": successors,
                "kind": "milestone" if task.is_milestone else "summary" if task.is_summary else "task",
                "dependency_metrics": asdict(dm) if dm else {},
            }
        )

    resource_records = []
    for resource in sorted(project.resources, key=lambda item: item.unique_id):
        rid = resource.unique_id
        series = analysis.resource_load.get(rid)
        resource_records.append(
            {
                "unique_id": rid,
                "name": resource.name,
                "type": resource.resource_type,
                "max_units": _number(resource.max_units),
                "peak_utilisation": max(series.utilisation) if series and series.utilisation else 0.0,
                "overallocation_windows": [asdict(window) for window in series.overallocation_windows] if series else [],
            }
        )

    assignment_records = []
    for assignment in sorted(
        project.assignments,
        key=lambda item: (
            item.task_unique_id if item.task_unique_id is not None else -1,
            item.resource_unique_id if item.resource_unique_id is not None else -1,
            item.start,
        ),
    ):
        assignment_records.append(
            {
                "task_unique_id": assignment.task_unique_id,
                "resource_unique_id": assignment.resource_unique_id,
                "units": _number(assignment.units),
                "work": _number(assignment.work),
                "cost": _number(assignment.cost),
                "start": assignment.start,
                "finish": assignment.finish,
            }
        )

    critical_set = set(analysis.critical_path_task_ids)
    dependency_records = []
    for dep in sorted(
        project.dependencies,
        key=lambda item: (
            item.predecessor_unique_id if item.predecessor_unique_id is not None else -1,
            item.successor_unique_id if item.successor_unique_id is not None else -1,
            item.relation_type,
        ),
    ):
        dependency_records.append(
            {
                "predecessor_unique_id": dep.predecessor_unique_id,
                "successor_unique_id": dep.successor_unique_id,
                "type": (dep.relation_type or "FS").upper(),
                "lag_days": _number(dep.lag),
                "is_critical": dep.predecessor_unique_id in critical_set and dep.successor_unique_id in critical_set,
            }
        )

    calendars = []
    for calendar in sorted(project.calendars, key=lambda item: item.unique_id or -1):
        cid = calendar.unique_id if calendar.unique_id is not None else calendar.name
        calendars.append(
            {
                "unique_id": cid,
                "name": calendar.name,
                "non_working_intervals": analysis.calendar_non_working_intervals.get(cid, []),
            }
        )

    resource_load = {
        str(rid): {
            "buckets": series.buckets,
            "load": series.load,
            "capacity": series.capacity,
            "utilisation": series.utilisation,
        }
        for rid, series in sorted(analysis.resource_load.items(), key=lambda item: item[0])
    }

    cost_profile = {
        "buckets": analysis.cost_profile.buckets,
        "planned": analysis.cost_profile.planned,
        "actual": analysis.cost_profile.actual,
        "forecast": analysis.cost_profile.forecast,
        "cumulative_planned": analysis.cost_profile.cumulative_planned,
        "cumulative_actual": analysis.cost_profile.cumulative_actual,
        "cumulative_forecast": analysis.cost_profile.cumulative_forecast,
        "peaks": [asdict(peak) for peak in analysis.cost_profile.peaks],
        "earned_value_available": analysis.cost_profile.earned_value_available,
        "earned_value": analysis.cost_profile.earned_value,
        "wbs_cost_concentration": analysis.cost_profile.wbs_cost_concentration,
    }

    bottlenecks = [asdict(item) for item in analysis.top_bottlenecks]

    payload = {
        "meta": {
            "project_title": project.title,
            "source_path": project.source_path,
            "time_window": {
                "start": analysis.project_start,
                "finish": analysis.project_finish,
            },
            "bucket_size": analysis.options.bucket_size,
            "units": {"time": "day", "cost": "currency", "work": "hours"},
            "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "is_cyclic": analysis.is_cyclic,
            "warnings": analysis.warnings,
            "task_count": len(task_records),
            "resource_count": len(resource_records),
            "dependency_count": len(dependency_records),
            "assignment_count": len(assignment_records),
        },
        "timeAxis": {
            "start": analysis.project_start,
            "finish": analysis.project_finish,
            "buckets": analysis.cost_profile.buckets,
            "bucket_size": analysis.options.bucket_size,
        },
        "tasks": task_records,
        "resources": resource_records,
        "assignments": assignment_records,
        "dependencies": dependency_records,
        "calendars": calendars,
        "resourceLoad": resource_load,
        "resourceLoadMatrix": analysis.resource_load_matrix,
        "costProfile": cost_profile,
        "bottlenecks": bottlenecks,
        "criticalPath": analysis.critical_path_task_ids,
        "wbsTree": _build_wbs_tree(task_records),
        "lodBuckets": _build_lod_buckets(task_records),
    }

    return payload


def _build_wbs_tree(task_records: list[dict[str, object]]) -> list[dict[str, object]]:
    by_id = {task["unique_id"]: {"task_unique_id": task["unique_id"], "children": []} for task in task_records}
    roots: list[dict[str, object]] = []

    for task in task_records:
        uid = task["unique_id"]
        parent = task.get("parent_unique_id")
        node = by_id[uid]
        if parent in by_id:
            by_id[parent]["children"].append(node)
        else:
            roots.append(node)

    def sort_tree(nodes: list[dict[str, object]]) -> None:
        nodes.sort(key=lambda item: item["task_unique_id"])
        for node in nodes:
            sort_tree(node["children"])

    sort_tree(roots)
    return roots


def _build_lod_buckets(task_records: list[dict[str, object]]) -> dict[str, list[int]]:
    summaries = [task["unique_id"] for task in task_records if task.get("is_summary")]
    level_1 = [task["unique_id"] for task in task_records if int(task.get("outline_level", 0)) <= 1]
    level_2 = [task["unique_id"] for task in task_records if int(task.get("outline_level", 0)) <= 2]
    full = [task["unique_id"] for task in task_records]

    return {
        "summary_only": sorted(summaries),
        "level_1": sorted(level_1),
        "level_2": sorted(level_2),
        "full": sorted(full),
    }


def _duration_days(duration: str, start: str, finish: str) -> float:
    numeric = _number(duration)
    if numeric > 0:
        return numeric

    start_date = _parse_date(start)
    finish_date = _parse_date(finish)
    if start_date and finish_date:
        return float(max(1, (finish_date - start_date).days))
    return 1.0


def _number(value: str) -> float:
    import re

    text = (value or "").strip().replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else 0.0


def _parse_date(value: str):
    from datetime import datetime

    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return datetime.fromisoformat(text[:19]).date()
        except ValueError:
            return None
    return None
