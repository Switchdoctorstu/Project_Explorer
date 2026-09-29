from dataclasses import dataclass, field


@dataclass
class Calendar:
    unique_id: int | None
    name: str
    calendar_type: str = ""
    parent_name: str = ""
    working_days: str = ""
    properties: list[tuple[str, str]] = field(default_factory=list)
