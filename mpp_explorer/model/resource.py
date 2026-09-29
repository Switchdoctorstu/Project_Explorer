from dataclasses import dataclass, field


@dataclass
class Resource:
    unique_id: int
    id: str
    name: str
    initials: str = ""
    resource_type: str = ""
    email: str = ""
    group: str = ""
    max_units: str = ""
    standard_rate: str = ""
    overtime_rate: str = ""
    cost_per_use: str = ""
    calendar_name: str = ""

    work: str = ""
    actual_work: str = ""
    remaining_work: str = ""
    cost: str = ""
    actual_cost: str = ""
    remaining_cost: str = ""

    properties: list[tuple[str, str]] = field(default_factory=list)
