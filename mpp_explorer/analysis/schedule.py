from __future__ import annotations

"""Schedule analysis utilities for deterministic 3D Gantt payloads.

This module is intentionally pure and side-effect free. It accepts Project model
objects, computes schedule/resource/cost/bottleneck metrics, and returns frozen
serialisable dataclasses.
"""

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
import math
import re
from typing import Iterable

from ..model.project import Project


@dataclass(frozen=True)
class BottleneckWeights:
    criticality: float = 0.25
    float: float = 0.20
    fan: float = 0.15
    resource: float = 0.15
    cost: float = 0.10
    duration: float = 0.10
    constraint: float = 0.05


@dataclass(frozen=True)
class ScheduleAnalysisOptions:
    bucket_size: str = "day"
    near_critical_threshold_days: float = 5.0
    lag_heavy_threshold_days: float = 10.0
    top_bottleneck_count: int = 25
    bottleneck_weights: BottleneckWeights = field(default_factory=BottleneckWeights)
    status_date_override: str | None = None


@dataclass(frozen=True)
class TaskScheduleMetrics:
    unique_id: int
    early_start: str
    early_finish: str
    late_start: str
    late_finish: str
    total_float_days: float
    free_float_days: float
    is_critical: bool
    is_near_critical: bool
    constraint_type: str
    constraint_date: str
    unresolved_constraint: bool
    cycle_participant: bool


@dataclass(frozen=True)
class OverallocationWindow:
    start_index: int
    end_index: int
    peak_utilisation: float


@dataclass(frozen=True)
class ResourceLoadSeries:
    resource_unique_id: int
    bucket_size: str
    buckets: list[str]
    load: list[float]
    capacity: list[float]
    utilisation: list[float]
    overallocated_buckets: list[int]
    peak_load: float
    peak_bucket_index: int
    overallocation_windows: list[OverallocationWindow]


@dataclass(frozen=True)
class CostPeak:
    bucket_index: int
    bucket_start: str
    amount: float


@dataclass(frozen=True)
class CostProfile:
    buckets: list[str]
    planned: list[float]
    actual: list[float]
    forecast: list[float]
    cumulative_planned: list[float]
    cumulative_actual: list[float]
    cumulative_forecast: list[float]
    peaks: list[CostPeak]
    wbs_cost_concentration: list[tuple[str, float]]
    earned_value_available: bool
    earned_value: dict[str, float | None]


@dataclass(frozen=True)
class DependencyBottleneckMetrics:
    unique_id: int
    predecessor_count: int
    successor_count: int
    fan_in: int
    fan_out: int
    is_merge_point: bool
    is_split_point: bool
    longest_incoming_lag_days: float
    longest_outgoing_lag_days: float
    lag_heavy: bool
    external_dependency: bool


@dataclass(frozen=True)
class BaselineVariance:
    unique_id: int
    start_variance_days: float | None
    finish_variance_days: float | None
    duration_variance_days: float | None
    cost_variance: float | None
    work_variance_days: float | None
    slip: bool
    acceleration: bool


@dataclass(frozen=True)
class BottleneckBreakdown:
    unique_id: int
    score: float
    components: dict[str, float]


@dataclass(frozen=True)
class ScheduleAnalysis:
    options: ScheduleAnalysisOptions
    project_start: str
    project_finish: str
    critical_path_task_ids: list[int]
    is_cyclic: bool
    warnings: list[str]
    task_metrics: dict[int, TaskScheduleMetrics]
    resource_load: dict[int, ResourceLoadSeries]
    resource_load_matrix: dict[str, object]
    cost_profile: CostProfile
    dependency_metrics: dict[int, DependencyBottleneckMetrics]
    bottleneck_scores: dict[int, BottleneckBreakdown]
    top_bottlenecks: list[BottleneckBreakdown]
    calendar_non_working_intervals: dict[int | str, list[tuple[str, str]]]
    baseline_variance: dict[int, BaselineVariance]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["task_metrics"] = {
            str(key): asdict(value) for key, value in sorted(self.task_metrics.items(), key=lambda item: item[0])
        }
        payload["resource_load"] = {
            str(key): asdict(value) for key, value in sorted(self.resource_load.items(), key=lambda item: item[0])
        }
        payload["dependency_metrics"] = {
            str(key): asdict(value)
            for key, value in sorted(self.dependency_metrics.items(), key=lambda item: item[0])
        }
        payload["bottleneck_scores"] = {
            str(key): asdict(value)
            for key, value in sorted(self.bottleneck_scores.items(), key=lambda item: item[0])
        }
        payload["baseline_variance"] = {
            str(key): asdict(value) for key, value in sorted(self.baseline_variance.items(), key=lambda item: item[0])
        }
        return payload


def analyse_schedule(project: Project, options: ScheduleAnalysisOptions | None = None) -> ScheduleAnalysis:
    options = options or ScheduleAnalysisOptions()
    warnings: list[str] = []

    if options.bucket_size not in {"day", "week", "month"}:
        warnings.append(f"Unsupported bucket_size '{options.bucket_size}', falling back to day.")
        options = ScheduleAnalysisOptions(
            bucket_size="day",
            near_critical_threshold_days=options.near_critical_threshold_days,
            lag_heavy_threshold_days=options.lag_heavy_threshold_days,
            top_bottleneck_count=options.top_bottleneck_count,
            bottleneck_weights=options.bottleneck_weights,
            status_date_override=options.status_date_override,
        )

    tasks = [task for task in project.tasks if task.unique_id is not None]
    task_ids = {task.unique_id for task in tasks}

    project_start_date = _find_project_start(tasks)
    project_finish_date = _find_project_finish(tasks)

    if project_start_date is None or project_finish_date is None:
        warnings.append("Unable to infer project start/finish from task dates; defaulting to today.")
        today = date.today()
        project_start_date = project_start_date or today
        project_finish_date = project_finish_date or today

    task_duration_days = {
        task.unique_id: _task_duration_days(task) for task in tasks
    }

    constraints = {
        task.unique_id: _extract_constraint(task) for task in tasks
    }

    graph_succ: dict[int, list[tuple[int, str, float]]] = {task.unique_id: [] for task in tasks}
    graph_pred: dict[int, list[tuple[int, str, float]]] = {task.unique_id: [] for task in tasks}
    for dep in project.dependencies:
        pred = dep.predecessor_unique_id
        succ = dep.successor_unique_id
        if pred not in task_ids or succ not in task_ids:
            continue
        relation = (dep.relation_type or "FS").strip().upper() or "FS"
        if relation not in {"FS", "SS", "FF", "SF"}:
            relation = "FS"
        lag_days = _parse_duration_days(dep.lag)
        graph_succ[pred].append((succ, relation, lag_days))
        graph_pred[succ].append((pred, relation, lag_days))

    topo_order, cycle_participants = _topological_order(graph_succ, graph_pred)
    is_cyclic = bool(cycle_participants)
    if is_cyclic:
        warnings.append("Cyclic dependency detected; analysis contains partial topological assumptions.")

    if len(topo_order) < len(tasks):
        leftover = sorted(task_ids.difference(set(topo_order)))
        topo_order.extend(leftover)

    es: dict[int, float] = {}
    ef: dict[int, float] = {}

    for uid in topo_order:
        task = project.tasks_by_unique_id.get(uid)
        if task is None:
            continue
        earliest = _date_to_offset_days(_parse_date(task.start), project_start_date)
        if earliest is None:
            earliest = 0.0

        lower_bound, unresolved = _constraint_lower_bound(task, project_start_date)
        if unresolved:
            warnings.append(f"Unresolved constraint for task {uid}: {_extract_constraint(task)[0]}")

        if lower_bound is not None:
            earliest = max(earliest, lower_bound)

        for pred, relation, lag_days in graph_pred.get(uid, []):
            pred_es = es.get(pred, 0.0)
            pred_ef = ef.get(pred, pred_es + task_duration_days.get(pred, 1.0))
            dur = task_duration_days.get(uid, 1.0)

            if relation == "FS":
                bound = pred_ef + lag_days
            elif relation == "SS":
                bound = pred_es + lag_days
            elif relation == "FF":
                bound = pred_ef + lag_days - dur
            else:  # SF
                bound = pred_es + lag_days - dur

            earliest = max(earliest, bound)

        dur = task_duration_days.get(uid, 1.0)
        es[uid] = earliest
        ef[uid] = earliest + dur

    horizon = max(ef.values(), default=0.0)
    fallback_finish_offset = _date_to_offset_days(project_finish_date, project_start_date)
    if fallback_finish_offset is not None:
        horizon = max(horizon, fallback_finish_offset)

    ls: dict[int, float] = {uid: horizon - task_duration_days.get(uid, 1.0) for uid in task_ids}
    lf: dict[int, float] = {uid: horizon for uid in task_ids}

    for uid in reversed(topo_order):
        dur = task_duration_days.get(uid, 1.0)
        latest_start = ls[uid]

        successors = graph_succ.get(uid, [])
        if successors:
            latest_start = float("inf")
            for succ, relation, lag_days in successors:
                succ_ls = ls.get(succ, horizon - task_duration_days.get(succ, 1.0))
                succ_lf = lf.get(succ, horizon)
                if relation == "FS":
                    bound = succ_ls - lag_days - dur
                elif relation == "SS":
                    bound = succ_ls - lag_days
                elif relation == "FF":
                    bound = succ_lf - lag_days - dur
                else:  # SF
                    bound = succ_lf - lag_days
                latest_start = min(latest_start, bound)

        upper_bound = _constraint_upper_bound(project.tasks_by_unique_id.get(uid), project_start_date)
        if upper_bound is not None:
            latest_start = min(latest_start, upper_bound)

        if math.isinf(latest_start):
            latest_start = horizon - dur

        ls[uid] = latest_start
        lf[uid] = latest_start + dur

    task_metrics: dict[int, TaskScheduleMetrics] = {}
    critical_path: list[int] = []

    for uid in sorted(task_ids):
        task = project.tasks_by_unique_id[uid]
        total_float = ls.get(uid, 0.0) - es.get(uid, 0.0)

        free_float_values: list[float] = []
        for succ, relation, lag_days in graph_succ.get(uid, []):
            succ_es = es.get(succ, horizon)
            succ_ef = ef.get(succ, succ_es + task_duration_days.get(succ, 1.0))
            current_es = es.get(uid, 0.0)
            current_ef = ef.get(uid, current_es + task_duration_days.get(uid, 1.0))
            if relation == "FS":
                free_float_values.append(succ_es - (current_ef + lag_days))
            elif relation == "SS":
                free_float_values.append(succ_es - (current_es + lag_days))
            elif relation == "FF":
                free_float_values.append(succ_ef - (current_ef + lag_days))
            else:  # SF
                free_float_values.append(succ_ef - (current_es + lag_days))

        free_float = min(free_float_values) if free_float_values else total_float

        is_critical = total_float <= 0.0
        is_near_critical = total_float <= options.near_critical_threshold_days
        if is_critical:
            critical_path.append(uid)

        constraint_type, constraint_date, unresolved_constraint = _extract_constraint(task)

        task_metrics[uid] = TaskScheduleMetrics(
            unique_id=uid,
            early_start=_offset_to_iso(project_start_date, es.get(uid, 0.0)),
            early_finish=_offset_to_iso(project_start_date, ef.get(uid, 0.0)),
            late_start=_offset_to_iso(project_start_date, ls.get(uid, 0.0)),
            late_finish=_offset_to_iso(project_start_date, lf.get(uid, 0.0)),
            total_float_days=round(total_float, 3),
            free_float_days=round(free_float, 3),
            is_critical=is_critical,
            is_near_critical=is_near_critical,
            constraint_type=constraint_type,
            constraint_date=constraint_date,
            unresolved_constraint=unresolved_constraint,
            cycle_participant=uid in cycle_participants,
        )

    critical_path = sorted(critical_path, key=lambda uid: (es.get(uid, 0.0), uid))

    buckets = _build_buckets(project_start_date, project_finish_date, options.bucket_size)

    resource_load, resource_matrix = _analyse_resource_load(project, buckets, options.bucket_size)

    status_date = _parse_status_date(project, options.status_date_override, warnings, project_finish_date)
    cost_profile = _analyse_cost_profile(project, buckets, status_date)

    dependency_metrics = _analyse_dependency_metrics(project, options)

    baseline_variance = _analyse_baseline_variance(project)

    bottleneck_scores = _analyse_bottlenecks(
        project,
        task_metrics,
        dependency_metrics,
        resource_load,
        task_duration_days,
        options,
    )

    top_bottlenecks = sorted(
        bottleneck_scores.values(), key=lambda item: (item.score, item.unique_id), reverse=True
    )[: max(0, options.top_bottleneck_count)]

    calendar_non_working = _analyse_calendar_non_working(project, project_start_date, project_finish_date)

    return ScheduleAnalysis(
        options=options,
        project_start=project_start_date.isoformat(),
        project_finish=project_finish_date.isoformat(),
        critical_path_task_ids=critical_path,
        is_cyclic=is_cyclic,
        warnings=sorted(set(warnings)),
        task_metrics=task_metrics,
        resource_load=resource_load,
        resource_load_matrix=resource_matrix,
        cost_profile=cost_profile,
        dependency_metrics=dependency_metrics,
        bottleneck_scores=bottleneck_scores,
        top_bottlenecks=top_bottlenecks,
        calendar_non_working_intervals=calendar_non_working,
        baseline_variance=baseline_variance,
    )


def _topological_order(
    graph_succ: dict[int, list[tuple[int, str, float]]],
    graph_pred: dict[int, list[tuple[int, str, float]]],
) -> tuple[list[int], set[int]]:
    indegree = {uid: len(preds) for uid, preds in graph_pred.items()}
    queue = sorted([uid for uid, degree in indegree.items() if degree == 0])
    order: list[int] = []

    while queue:
        uid = queue.pop(0)
        order.append(uid)
        for succ, _relation, _lag in graph_succ.get(uid, []):
            indegree[succ] = max(0, indegree.get(succ, 0) - 1)
            if indegree[succ] == 0 and succ not in queue and succ not in order:
                queue.append(succ)
                queue.sort()

    cycle_participants = {uid for uid, degree in indegree.items() if degree > 0}
    return order, cycle_participants


def _extract_constraint(task) -> tuple[str, str, bool]:
    if task is None:
        return "", "", False

    constraint_type = ""
    constraint_date = ""

    for name, value in task.general_properties:
        if name == "Constraint Type":
            constraint_type = value or ""
        elif name == "Constraint Date":
            constraint_date = value or ""

    unresolved = bool(constraint_type and constraint_type.strip().lower() in {"", "none", "null", "unknown"})
    if constraint_type.strip() and constraint_type.strip().lower() not in {
        "as soon as possible",
        "as late as possible",
        "must start on",
        "must finish on",
        "start no earlier than",
        "finish no later than",
    }:
        unresolved = True

    return constraint_type.strip(), constraint_date.strip(), unresolved


def _constraint_lower_bound(task, project_start: date) -> tuple[float | None, bool]:
    constraint_type, constraint_date, unresolved = _extract_constraint(task)
    cdate = _parse_date(constraint_date)
    offset = _date_to_offset_days(cdate, project_start)
    ctype = constraint_type.lower()

    if ctype in {"must start on", "start no earlier than"} and offset is not None:
        return offset, unresolved
    if ctype == "as late as possible":
        return None, unresolved
    return None, unresolved


def _constraint_upper_bound(task, project_start: date) -> float | None:
    constraint_type, constraint_date, _unresolved = _extract_constraint(task)
    cdate = _parse_date(constraint_date)
    offset = _date_to_offset_days(cdate, project_start)
    ctype = constraint_type.lower()
    if ctype in {"must start on", "finish no later than"} and offset is not None:
        return offset
    return None


def _find_project_start(tasks) -> date | None:
    starts = [_parse_date(task.start) for task in tasks]
    starts = [item for item in starts if item is not None]
    if not starts:
        return None
    return min(starts)


def _find_project_finish(tasks) -> date | None:
    finishes = [_parse_date(task.finish) for task in tasks]
    finishes = [item for item in finishes if item is not None]
    if not finishes:
        return None
    return max(finishes)


def _task_duration_days(task) -> float:
    explicit = _parse_duration_days(task.duration)
    if explicit > 0:
        return max(explicit, 0.25)

    start = _parse_date(task.start)
    finish = _parse_date(task.finish)
    if start is None or finish is None:
        return 1.0
    delta = (finish - start).days
    return max(float(delta), 1.0)


def _parse_status_date(
    project: Project,
    override: str | None,
    warnings: list[str],
    default_date: date,
) -> date:
    if override:
        parsed_override = _parse_date(override)
        if parsed_override is not None:
            return parsed_override
        warnings.append(f"Invalid status_date_override '{override}', using project finish.")

    for key, value in project.properties:
        if key == "Status Date":
            parsed = _parse_date(value)
            if parsed is not None:
                return parsed

    warnings.append("Status date is unavailable; using project finish date.")
    return default_date


def _analyse_resource_load(
    project: Project,
    buckets: list[tuple[date, date]],
    bucket_size: str,
) -> tuple[dict[int, ResourceLoadSeries], dict[str, object]]:
    assignments_by_resource: dict[int, list] = {}
    for assignment in project.assignments:
        if assignment.resource_unique_id is None:
            continue
        assignments_by_resource.setdefault(assignment.resource_unique_id, []).append(assignment)

    resource_load: dict[int, ResourceLoadSeries] = {}
    matrix_rows: list[list[float]] = []
    matrix_ids: list[int] = []

    for resource in sorted(project.resources, key=lambda item: item.unique_id):
        rid = resource.unique_id
        if rid is None:
            continue

        load = [0.0 for _ in buckets]
        capacity = [0.0 for _ in buckets]
        utilisation = [0.0 for _ in buckets]

        capacity_factor = _parse_units_fraction(resource.max_units)
        for index, (bstart, bend) in enumerate(buckets):
            working_hours = _bucket_working_hours(bstart, bend, bucket_size)
            capacity[index] = round(capacity_factor * working_hours, 6)

        for assignment in assignments_by_resource.get(rid, []):
            astart = _parse_date(assignment.start)
            afinish = _parse_date(assignment.finish)
            if astart is None or afinish is None:
                continue
            units = _parse_units_fraction(assignment.units)
            for index, (bstart, bend) in enumerate(buckets):
                overlap_days = _overlap_days(astart, afinish, bstart, bend)
                if overlap_days <= 0:
                    continue
                load[index] += units * overlap_days * 8.0

        overallocated: list[int] = []
        peak_load = 0.0
        peak_index = 0
        for index in range(len(buckets)):
            if load[index] > peak_load:
                peak_load = load[index]
                peak_index = index
            cap = capacity[index]
            utilisation[index] = round((load[index] / cap), 6) if cap > 0 else 0.0
            if utilisation[index] > 1.0:
                overallocated.append(index)

        windows = _build_overallocation_windows(utilisation)

        series = ResourceLoadSeries(
            resource_unique_id=rid,
            bucket_size=bucket_size,
            buckets=[start.isoformat() for start, _end in buckets],
            load=[round(value, 6) for value in load],
            capacity=[round(value, 6) for value in capacity],
            utilisation=utilisation,
            overallocated_buckets=overallocated,
            peak_load=round(peak_load, 6),
            peak_bucket_index=peak_index,
            overallocation_windows=windows,
        )
        resource_load[rid] = series
        matrix_ids.append(rid)
        matrix_rows.append(series.utilisation)

    matrix = {
        "resource_ids": matrix_ids,
        "buckets": [start.isoformat() for start, _end in buckets],
        "matrix": matrix_rows,
    }
    return resource_load, matrix


def _analyse_cost_profile(project: Project, buckets: list[tuple[date, date]], status_date: date) -> CostProfile:
    planned = [0.0 for _ in buckets]
    actual = [0.0 for _ in buckets]
    forecast = [0.0 for _ in buckets]

    wbs_totals: dict[str, float] = {}

    for task in project.tasks:
        start = _parse_date(task.start)
        finish = _parse_date(task.finish)
        if start is None or finish is None:
            continue

        planned_cost = _parse_number(task.cost)
        actual_cost = _parse_number(task.actual_cost)
        remaining_cost = _parse_number(task.remaining_cost)

        _spread_cost(planned, buckets, start, finish, planned_cost)

        actual_finish = min(finish, status_date)
        if actual_finish >= start:
            _spread_cost(actual, buckets, start, actual_finish, actual_cost)

        rem_start = max(start, status_date)
        if finish >= rem_start:
            _spread_cost(forecast, buckets, rem_start, finish, remaining_cost)

        wbs_key = task.wbs or "(unassigned)"
        wbs_totals[wbs_key] = wbs_totals.get(wbs_key, 0.0) + planned_cost

    cumulative_planned = _cumulative(planned)
    cumulative_actual = _cumulative(actual)
    cumulative_forecast = _cumulative([planned[i] + forecast[i] for i in range(len(planned))])

    peaks = _cost_peaks(planned, buckets)

    concentration = sorted(wbs_totals.items(), key=lambda item: item[1], reverse=True)[:10]

    earned = _earned_value(project)

    return CostProfile(
        buckets=[start.isoformat() for start, _end in buckets],
        planned=[round(value, 6) for value in planned],
        actual=[round(value, 6) for value in actual],
        forecast=[round(value, 6) for value in forecast],
        cumulative_planned=[round(value, 6) for value in cumulative_planned],
        cumulative_actual=[round(value, 6) for value in cumulative_actual],
        cumulative_forecast=[round(value, 6) for value in cumulative_forecast],
        peaks=peaks,
        wbs_cost_concentration=[(key, round(value, 6)) for key, value in concentration],
        earned_value_available=earned["available"],
        earned_value=earned["values"],
    )


def _analyse_dependency_metrics(
    project: Project,
    options: ScheduleAnalysisOptions,
) -> dict[int, DependencyBottleneckMetrics]:
    incoming: dict[int, list] = {task.unique_id: [] for task in project.tasks}
    outgoing: dict[int, list] = {task.unique_id: [] for task in project.tasks}

    for dep in project.dependencies:
        pred = dep.predecessor_unique_id
        succ = dep.successor_unique_id
        if pred is None or succ is None:
            continue
        outgoing.setdefault(pred, []).append(dep)
        incoming.setdefault(succ, []).append(dep)

    metrics: dict[int, DependencyBottleneckMetrics] = {}
    for task in sorted(project.tasks, key=lambda item: item.unique_id):
        uid = task.unique_id
        in_deps = incoming.get(uid, [])
        out_deps = outgoing.get(uid, [])

        in_lags = [_parse_duration_days(dep.lag) for dep in in_deps]
        out_lags = [_parse_duration_days(dep.lag) for dep in out_deps]
        longest_in = max(in_lags, default=0.0)
        longest_out = max(out_lags, default=0.0)

        fan_in = len({dep.predecessor_unique_id for dep in in_deps if dep.predecessor_unique_id is not None})
        fan_out = len({dep.successor_unique_id for dep in out_deps if dep.successor_unique_id is not None})

        external = any(
            "external" in (dep.predecessor_name or "").lower()
            or "subproject" in (dep.predecessor_name or "").lower()
            or "external" in (dep.successor_name or "").lower()
            or "subproject" in (dep.successor_name or "").lower()
            for dep in in_deps + out_deps
        )

        lag_heavy = max(longest_in, longest_out) > options.lag_heavy_threshold_days

        metrics[uid] = DependencyBottleneckMetrics(
            unique_id=uid,
            predecessor_count=len(in_deps),
            successor_count=len(out_deps),
            fan_in=fan_in,
            fan_out=fan_out,
            is_merge_point=fan_in >= 3,
            is_split_point=fan_out >= 3,
            longest_incoming_lag_days=round(longest_in, 6),
            longest_outgoing_lag_days=round(longest_out, 6),
            lag_heavy=lag_heavy,
            external_dependency=external,
        )

    return metrics


def _analyse_bottlenecks(
    project: Project,
    task_metrics: dict[int, TaskScheduleMetrics],
    dependency_metrics: dict[int, DependencyBottleneckMetrics],
    resource_load: dict[int, ResourceLoadSeries],
    task_duration_days: dict[int, float],
    options: ScheduleAnalysisOptions,
) -> dict[int, BottleneckBreakdown]:
    max_cost = max((_parse_number(task.cost) for task in project.tasks), default=0.0)
    max_duration = max(task_duration_days.values(), default=1.0)

    assignments_by_task: dict[int, list] = {}
    for assignment in project.assignments:
        if assignment.task_unique_id is None:
            continue
        assignments_by_task.setdefault(assignment.task_unique_id, []).append(assignment)

    scores: dict[int, BottleneckBreakdown] = {}

    for task in project.tasks:
        uid = task.unique_id
        tm = task_metrics.get(uid)
        dm = dependency_metrics.get(uid)
        if tm is None or dm is None:
            continue

        criticality = 1.0 if tm.is_critical else 0.5 if tm.is_near_critical else 0.0
        low_float = 1.0 - min(max(tm.total_float_days, 0.0), 20.0) / 20.0
        fan_score = min((dm.fan_in + dm.fan_out) / 10.0, 1.0)

        res_contention = 0.0
        for assignment in assignments_by_task.get(uid, []):
            rid = assignment.resource_unique_id
            if rid is None or rid not in resource_load:
                continue
            series = resource_load[rid]
            res_contention = max(res_contention, max(series.utilisation, default=0.0))
        res_contention = min(res_contention, 2.0) / 2.0

        cost_score = (_parse_number(task.cost) / max_cost) if max_cost > 0 else 0.0
        duration_score = task_duration_days.get(uid, 0.0) / max_duration if max_duration > 0 else 0.0
        constraint_score = 1.0 if tm.unresolved_constraint else 0.0

        components = {
            "criticality": round(criticality, 6),
            "float": round(low_float, 6),
            "fan": round(fan_score, 6),
            "resource": round(cost_score * 0 + res_contention, 6),
            "cost": round(cost_score, 6),
            "duration": round(duration_score, 6),
            "constraint": round(constraint_score, 6),
        }

        weights = options.bottleneck_weights
        weighted = (
            weights.criticality * criticality
            + weights.float * low_float
            + weights.fan * fan_score
            + weights.resource * res_contention
            + weights.cost * cost_score
            + weights.duration * duration_score
            + weights.constraint * constraint_score
        )
        score = max(0.0, min(1.0, weighted))

        scores[uid] = BottleneckBreakdown(unique_id=uid, score=round(score, 6), components=components)

    return scores


def _analyse_calendar_non_working(
    project: Project,
    project_start: date,
    project_finish: date,
) -> dict[int | str, list[tuple[str, str]]]:
    intervals_by_calendar: dict[int | str, list[tuple[str, str]]] = {}
    span_days = max(0, (project_finish - project_start).days)

    for calendar in project.calendars:
        cid = calendar.unique_id if calendar.unique_id is not None else calendar.name or "calendar"
        declared_working = _parse_working_days(calendar.working_days)
        non_working_weekdays = [
            weekday for weekday in range(7) if weekday not in declared_working
        ]

        intervals: list[tuple[str, str]] = []
        for delta in range(span_days + 1):
            current = project_start + timedelta(days=delta)
            if current.weekday() in non_working_weekdays:
                end = current + timedelta(days=1)
                intervals.append((current.isoformat(), end.isoformat()))

        intervals_by_calendar[cid] = intervals

    if not intervals_by_calendar:
        intervals_by_calendar["default"] = []

    return intervals_by_calendar


def _analyse_baseline_variance(project: Project) -> dict[int, BaselineVariance]:
    baseline: dict[int, BaselineVariance] = {}
    for task in project.tasks:
        uid = task.unique_id

        start = _parse_date(task.start)
        finish = _parse_date(task.finish)
        baseline_start = _parse_date(task.baseline_start)
        baseline_finish = _parse_date(task.baseline_finish)

        start_var = _days_delta(start, baseline_start)
        finish_var = _days_delta(finish, baseline_finish)

        actual_duration = _task_duration_days(task)
        baseline_duration = _parse_duration_days(task.baseline_duration)
        duration_var = None
        if baseline_duration > 0:
            duration_var = round(actual_duration - baseline_duration, 6)

        cost = _parse_number(task.cost)
        baseline_cost = _read_property_float(task.cost_properties, "Baseline Cost")
        cost_var = None
        if baseline_cost is not None:
            cost_var = round(cost - baseline_cost, 6)

        work = _parse_duration_days(task.work)
        baseline_work = _read_property_float(task.cost_properties, "Baseline Work")
        work_var = None
        if baseline_work is not None:
            work_var = round(work - baseline_work, 6)

        finish_variance_value = finish_var if finish_var is not None else 0.0

        baseline[uid] = BaselineVariance(
            unique_id=uid,
            start_variance_days=start_var,
            finish_variance_days=finish_var,
            duration_variance_days=duration_var,
            cost_variance=cost_var,
            work_variance_days=work_var,
            slip=finish_variance_value > 0,
            acceleration=finish_variance_value < 0,
        )

    return baseline


def _build_buckets(start: date, finish: date, bucket_size: str) -> list[tuple[date, date]]:
    if finish < start:
        finish = start

    buckets: list[tuple[date, date]] = []
    cursor = start
    while cursor <= finish:
        if bucket_size == "week":
            end = cursor + timedelta(days=7)
        elif bucket_size == "month":
            if cursor.month == 12:
                end = date(cursor.year + 1, 1, 1)
            else:
                end = date(cursor.year, cursor.month + 1, 1)
        else:
            end = cursor + timedelta(days=1)
        buckets.append((cursor, end))
        cursor = end

    return buckets


def _spread_cost(target: list[float], buckets: list[tuple[date, date]], start: date, finish: date, total_cost: float) -> None:
    span_days = max(1.0, float((finish - start).days + 1))
    if total_cost == 0:
        return
    daily = total_cost / span_days

    for index, (bstart, bend) in enumerate(buckets):
        overlap = _overlap_days(start, finish, bstart, bend)
        if overlap > 0:
            target[index] += daily * overlap


def _cumulative(values: Iterable[float]) -> list[float]:
    result: list[float] = []
    running = 0.0
    for value in values:
        running += value
        result.append(running)
    return result


def _cost_peaks(costs: list[float], buckets: list[tuple[date, date]], percentile: float = 0.90) -> list[CostPeak]:
    if not costs:
        return []

    sorted_values = sorted(costs)
    threshold_index = int(max(0, min(len(sorted_values) - 1, math.floor(percentile * (len(sorted_values) - 1)))))
    threshold = sorted_values[threshold_index]

    peaks: list[CostPeak] = []
    for index, value in enumerate(costs):
        if value >= threshold and value > 0:
            peaks.append(CostPeak(bucket_index=index, bucket_start=buckets[index][0].isoformat(), amount=round(value, 6)))
    return peaks


def _earned_value(project: Project) -> dict[str, object]:
    pv = sum(filter(None, (_read_property_float(task.cost_properties, "BCWS") for task in project.tasks)))
    ev = sum(filter(None, (_read_property_float(task.cost_properties, "BCWP") for task in project.tasks)))
    ac = sum(filter(None, (_read_property_float(task.cost_properties, "ACWP") for task in project.tasks)))

    available = any(_read_property_float(task.cost_properties, "BCWS") is not None for task in project.tasks)

    cpi = (ev / ac) if ac not in (0.0, None) else None
    spi = (ev / pv) if pv not in (0.0, None) else None
    eac = (ac + (pv - ev)) if available else None
    vac = (pv - eac) if (eac is not None and pv is not None) else None
    tcpi = ((pv - ev) / (pv - ac)) if (pv not in (None, 0.0) and (pv - ac) not in (0.0,)) else None

    values = {
        "PV": round(pv, 6) if available else None,
        "EV": round(ev, 6) if available else None,
        "AC": round(ac, 6) if available else None,
        "CPI": round(cpi, 6) if cpi is not None else None,
        "SPI": round(spi, 6) if spi is not None else None,
        "EAC": round(eac, 6) if eac is not None else None,
        "VAC": round(vac, 6) if vac is not None else None,
        "TCPI": round(tcpi, 6) if tcpi is not None else None,
    }
    return {"available": available, "values": values}


def _build_overallocation_windows(utilisation: list[float]) -> list[OverallocationWindow]:
    windows: list[OverallocationWindow] = []
    start: int | None = None
    peak = 0.0

    for index, value in enumerate(utilisation):
        if value > 1.0:
            if start is None:
                start = index
                peak = value
            else:
                peak = max(peak, value)
        elif start is not None:
            windows.append(
                OverallocationWindow(start_index=start, end_index=index - 1, peak_utilisation=round(peak, 6))
            )
            start = None
            peak = 0.0

    if start is not None:
        windows.append(
            OverallocationWindow(
                start_index=start,
                end_index=len(utilisation) - 1,
                peak_utilisation=round(peak, 6),
            )
        )

    return windows


def _bucket_working_hours(start: date, end: date, bucket_size: str) -> float:
    if bucket_size == "day":
        return 8.0
    if bucket_size == "week":
        return 40.0
    days = max(1, (end - start).days)
    return float(days) * 8.0


def _overlap_days(a_start: date, a_finish: date, b_start: date, b_end: date) -> float:
    left = max(a_start, b_start)
    right = min(a_finish + timedelta(days=1), b_end)
    delta = (right - left).days
    return float(max(0, delta))


def _days_delta(left: date | None, right: date | None) -> float | None:
    if left is None or right is None:
        return None
    return float((left - right).days)


def _offset_to_iso(project_start: date, offset_days: float) -> str:
    whole_days = int(math.floor(offset_days))
    return (project_start + timedelta(days=whole_days)).isoformat()


def _date_to_offset_days(value: date | None, project_start: date) -> float | None:
    if value is None:
        return None
    return float((value - project_start).days)


def _parse_working_days(text: str) -> set[int]:
    lowered = (text or "").lower()
    mapping = {
        "mon": 0,
        "tue": 1,
        "wed": 2,
        "thu": 3,
        "fri": 4,
        "sat": 5,
        "sun": 6,
    }
    days = {index for token, index in mapping.items() if token in lowered}
    if days:
        return days
    return {0, 1, 2, 3, 4}


def _read_property_float(properties: list[tuple[str, str]], key: str) -> float | None:
    for prop_key, prop_value in properties:
        if prop_key == key:
            return _parse_number(prop_value)
    return None


def _parse_units_fraction(value: str) -> float:
    text = (value or "").strip()
    if not text:
        return 1.0
    number = _parse_number(text)
    if "%" in text:
        return max(0.0, number / 100.0)
    if number > 1.5:
        return number / 100.0
    return max(0.0, number)


def _parse_duration_days(value: str) -> float:
    text = (value or "").strip().lower()
    if not text:
        return 0.0

    number = _parse_number(text)
    if "week" in text or text.endswith("w"):
        return number * 5.0
    if "month" in text or text.endswith("mo"):
        return number * 22.0
    if "hour" in text or text.endswith("h"):
        return number / 8.0
    if "min" in text:
        return number / (8.0 * 60.0)
    return number


def _parse_number(value: str) -> float:
    text = (value or "").strip()
    if not text:
        return 0.0

    cleaned = text.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return 0.0
    try:
        return float(match.group(0))
    except ValueError:
        return 0.0


def _parse_date(value: str) -> date | None:
    text = (value or "").strip()
    if not text:
        return None

    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return datetime.fromisoformat(text[:19]).date()
        except ValueError:
            pass

    candidates = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M",
        "%m/%d/%Y",
        "%m/%d/%Y %H:%M",
        "%d %b %Y",
        "%d %B %Y",
    ]
    for fmt in candidates:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    # Last attempt: use first date-like token.
    token_match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if token_match:
        try:
            return datetime.strptime(token_match.group(0), "%Y-%m-%d").date()
        except ValueError:
            return None

    return None
