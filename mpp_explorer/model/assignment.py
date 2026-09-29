from dataclasses import dataclass


@dataclass
class Assignment:
    task_unique_id: int | None
    resource_unique_id: int | None
    task_id: str = ""
    task_name: str = ""
    resource_name: str = ""
    start: str = ""
    finish: str = ""
    units: str = ""
    work: str = ""
    actual_work: str = ""
    remaining_work: str = ""
    cost: str = ""
    actual_cost: str = ""
    remaining_cost: str = ""
