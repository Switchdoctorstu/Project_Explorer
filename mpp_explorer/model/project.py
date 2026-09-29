from dataclasses import dataclass, field

from .assignment import Assignment
from .calendar import Calendar
from .dependency import Dependency
from .resource import Resource
from .task import Task


@dataclass
class Project:
    source_path: str = ""
    title: str = ""
    tasks: list[Task] = field(default_factory=list)
    resources: list[Resource] = field(default_factory=list)
    assignments: list[Assignment] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)
    calendars: list[Calendar] = field(default_factory=list)
    properties: list[tuple[str, str]] = field(default_factory=list)
    import_messages: list[str] = field(default_factory=list)

    tasks_by_unique_id: dict[int, Task] = field(default_factory=dict)
    resources_by_unique_id: dict[int, Resource] = field(default_factory=dict)
    calendars_by_unique_id: dict[int, Calendar] = field(default_factory=dict)

    def index(self) -> None:
        self.tasks_by_unique_id = {
            task.unique_id: task for task in self.tasks if task.unique_id is not None
        }
        self.resources_by_unique_id = {
            resource.unique_id: resource
            for resource in self.resources
            if resource.unique_id is not None
        }
        self.calendars_by_unique_id = {
            calendar.unique_id: calendar
            for calendar in self.calendars
            if calendar.unique_id is not None
        }

    def root_tasks(self) -> list[Task]:
        return [task for task in self.tasks if task.parent_unique_id is None]

    def task_children(self, task: Task) -> list[Task]:
        return [
            self.tasks_by_unique_id[child]
            for child in task.child_unique_ids
            if child in self.tasks_by_unique_id
        ]
