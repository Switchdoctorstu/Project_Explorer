from .assignment import Assignment
from .calendar import Calendar
from .dependency import Dependency
from .project import Project
from .resource import Resource
from .task import Task

__all__ = [
    "Assignment",
    "Calendar",
    "Dependency",
    "ProjectExtractor",
    "Project",
    "Resource",
    "Task",
]


def __getattr__(name):
    if name == "ProjectExtractor":
        from .extractor import ProjectExtractor

        return ProjectExtractor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
