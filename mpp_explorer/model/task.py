from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Task:
    unique_id: int
    id: str
    name: str
    wbs: str = ""
    outline_level: int = 0
    outline_number: str = ""

    start: str = ""
    finish: str = ""
    duration: str = ""

    actual_start: str = ""
    actual_finish: str = ""
    actual_duration: str = ""
    remaining_duration: str = ""

    baseline_start: str = ""
    baseline_finish: str = ""
    baseline_duration: str = ""

    percent_complete: str = ""
    percent_work_complete: str = ""

    is_summary: bool = False
    is_milestone: bool = False
    is_critical: bool = False
    is_active: bool = True

    cost: str = ""
    actual_cost: str = ""
    remaining_cost: str = ""
    work: str = ""
    actual_work: str = ""
    remaining_work: str = ""

    resource_names: str = ""
    notes: str = ""

    parent_unique_id: Optional[int] = None
    child_unique_ids: list[int] = field(default_factory=list)
    predecessor_ids: list[int] = field(default_factory=list)
    successor_ids: list[int] = field(default_factory=list)

    general_properties: list[tuple[str, str]] = field(default_factory=list)
    schedule_properties: list[tuple[str, str]] = field(default_factory=list)
    cost_properties: list[tuple[str, str]] = field(default_factory=list)

    def display_label(self) -> str:
        return self.name or "(Unnamed task)"
