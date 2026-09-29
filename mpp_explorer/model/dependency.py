from dataclasses import dataclass


@dataclass
class Dependency:
    predecessor_unique_id: int | None
    successor_unique_id: int | None
    predecessor_id: str = ""
    predecessor_name: str = ""
    successor_id: str = ""
    successor_name: str = ""
    relation_type: str = ""
    lag: str = ""
