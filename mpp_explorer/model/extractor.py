from __future__ import annotations

from ..core.jvm import jclass
from ..core.safe import as_bool_text, as_text, collection_items, safe_call
from .assignment import Assignment
from .calendar import Calendar
from .dependency import Dependency
from .project import Project
from .resource import Resource
from .task import Task


class ProjectExtractor:
    def extract(self, java_project, source_path: str = "") -> Project:
        project = Project(source_path=source_path)
        properties_object = safe_call(java_project, "getProjectProperties", None) or safe_call(
            java_project, "getProperties", None
        )
        project.title = as_text(safe_call(properties_object, "getProjectTitle"))

        java_tasks = collection_items(
            safe_call(java_project, "getTasks", None)
            or safe_call(java_project, "getAllTasks", None)
        )

        project.tasks = self._extract_tasks(java_tasks)
        project.resources = self._extract_resources(java_project)
        project.calendars = self._extract_calendars(java_project)
        project.dependencies = self._extract_dependencies(java_tasks, project.tasks)
        project.assignments = self._extract_assignments(java_tasks)
        project.properties = self._extract_project_properties(properties_object)
        project.import_messages = self._extract_messages(java_project)

        project.index()
        self._link_children(project)
        return project

    def _extract_tasks(self, tasks) -> list[Task]:
        result: list[Task] = []
        for java_task in tasks:
            unique_id = self._as_int(safe_call(java_task, "getUniqueID", None))
            if unique_id is None:
                continue

            parent_task = safe_call(java_task, "getParentTask", None)
            parent_unique_id = self._as_int(safe_call(parent_task, "getUniqueID", None))

            is_summary = self._as_bool(safe_call(java_task, "getSummary", False))
            is_milestone = self._as_bool(safe_call(java_task, "getMilestone", False))
            is_critical = self._as_bool(safe_call(java_task, "getCritical", False))
            is_active = self._as_bool(safe_call(java_task, "getActive", True), True)

            task = Task(
                unique_id=unique_id,
                id=as_text(safe_call(java_task, "getID")),
                name=as_text(safe_call(java_task, "getName")),
                wbs=as_text(safe_call(java_task, "getWBS")),
                outline_level=self._as_int(safe_call(java_task, "getOutlineLevel", 0), 0) or 0,
                outline_number=as_text(safe_call(java_task, "getOutlineNumber")),
                start=as_text(safe_call(java_task, "getStart")),
                finish=as_text(safe_call(java_task, "getFinish")),
                duration=as_text(safe_call(java_task, "getDuration")),
                actual_start=as_text(safe_call(java_task, "getActualStart")),
                actual_finish=as_text(safe_call(java_task, "getActualFinish")),
                actual_duration=as_text(safe_call(java_task, "getActualDuration")),
                remaining_duration=as_text(safe_call(java_task, "getRemainingDuration")),
                baseline_start=as_text(safe_call(java_task, "getBaselineStart")),
                baseline_finish=as_text(safe_call(java_task, "getBaselineFinish")),
                baseline_duration=as_text(safe_call(java_task, "getBaselineDuration")),
                percent_complete=as_text(safe_call(java_task, "getPercentageComplete")),
                percent_work_complete=as_text(safe_call(java_task, "getPercentageWorkComplete")),
                is_summary=is_summary,
                is_milestone=is_milestone,
                is_critical=is_critical,
                is_active=is_active,
                cost=as_text(safe_call(java_task, "getCost")),
                actual_cost=as_text(safe_call(java_task, "getActualCost")),
                remaining_cost=as_text(safe_call(java_task, "getRemainingCost")),
                work=as_text(safe_call(java_task, "getWork")),
                actual_work=as_text(safe_call(java_task, "getActualWork")),
                remaining_work=as_text(safe_call(java_task, "getRemainingWork")),
                resource_names=as_text(safe_call(java_task, "getResourceNames")),
                notes=as_text(safe_call(java_task, "getNotes")),
                parent_unique_id=parent_unique_id,
            )

            task.general_properties = self._task_general_properties(java_task)
            task.schedule_properties = self._task_schedule_properties(java_task)
            task.cost_properties = self._task_cost_properties(java_task)

            task.predecessor_ids = self._relation_target_ids(
                collection_items(safe_call(java_task, "getPredecessors", None)),
                "predecessor",
            )
            task.successor_ids = self._relation_target_ids(
                collection_items(safe_call(java_task, "getSuccessors", None)),
                "successor",
            )

            result.append(task)

        return result

    def _extract_resources(self, java_project) -> list[Resource]:
        resources = collection_items(
            safe_call(java_project, "getResources", None)
            or safe_call(java_project, "getAllResources", None)
        )

        result: list[Resource] = []
        for java_resource in resources:
            unique_id = self._as_int(safe_call(java_resource, "getUniqueID", None), -1)
            calendar = safe_call(java_resource, "getCalendar", None)
            resource = Resource(
                unique_id=unique_id,
                id=as_text(safe_call(java_resource, "getID")),
                name=as_text(safe_call(java_resource, "getName")),
                initials=as_text(safe_call(java_resource, "getInitials")),
                resource_type=as_text(safe_call(java_resource, "getType")),
                email=as_text(safe_call(java_resource, "getEmailAddress")),
                group=as_text(safe_call(java_resource, "getGroup")),
                max_units=as_text(safe_call(java_resource, "getMaxUnits")),
                standard_rate=as_text(safe_call(java_resource, "getStandardRate")),
                overtime_rate=as_text(safe_call(java_resource, "getOvertimeRate")),
                cost_per_use=as_text(safe_call(java_resource, "getCostPerUse")),
                calendar_name=as_text(safe_call(calendar, "getName")),
                work=as_text(safe_call(java_resource, "getWork")),
                actual_work=as_text(safe_call(java_resource, "getActualWork")),
                remaining_work=as_text(safe_call(java_resource, "getRemainingWork")),
                cost=as_text(safe_call(java_resource, "getCost")),
                actual_cost=as_text(safe_call(java_resource, "getActualCost")),
                remaining_cost=as_text(safe_call(java_resource, "getRemainingCost")),
            )
            resource.properties = self._resource_properties(java_resource)
            result.append(resource)

        return result

    def _extract_calendars(self, java_project) -> list[Calendar]:
        calendars = collection_items(safe_call(java_project, "getCalendars", None))
        result: list[Calendar] = []

        for java_calendar in calendars:
            parent = safe_call(java_calendar, "getParent", None)
            calendar = Calendar(
                unique_id=self._as_int(safe_call(java_calendar, "getUniqueID", None)),
                name=as_text(safe_call(java_calendar, "getName")),
                calendar_type=as_text(safe_call(java_calendar, "getType")),
                parent_name=as_text(safe_call(parent, "getName")),
                working_days=self._describe_calendar_days(java_calendar),
            )
            calendar.properties = [
                ("Name", calendar.name),
                ("Unique ID", as_text(safe_call(java_calendar, "getUniqueID"))),
                ("Type", calendar.calendar_type),
                ("Parent Calendar", calendar.parent_name),
                ("Working Days", calendar.working_days),
                ("Personal Calendar", as_bool_text(safe_call(java_calendar, "getPersonal"))),
            ]
            result.append(calendar)

        return result

    def _extract_dependencies(self, java_tasks, tasks: list[Task]) -> list[Dependency]:
        dependencies: list[Dependency] = []
        by_unique = {task.unique_id: task for task in tasks}

        for java_successor in java_tasks:
            successor_unique = self._as_int(safe_call(java_successor, "getUniqueID", None))
            if successor_unique is None:
                continue

            successor = by_unique.get(successor_unique)
            relations = collection_items(safe_call(java_successor, "getPredecessors", None))
            for relation in relations:
                predecessor_task = self._relation_task(relation, "predecessor")
                predecessor_unique = self._as_int(safe_call(predecessor_task, "getUniqueID", None))
                predecessor = by_unique.get(predecessor_unique) if predecessor_unique is not None else None
                dependencies.append(
                    Dependency(
                        predecessor_unique_id=predecessor_unique,
                        successor_unique_id=successor_unique,
                        predecessor_id=predecessor.id if predecessor else "",
                        predecessor_name=predecessor.name if predecessor else "",
                        successor_id=successor.id if successor else "",
                        successor_name=successor.name if successor else "",
                        relation_type=as_text(safe_call(relation, "getType")),
                        lag=as_text(self._relation_lag(relation)),
                    )
                )

        return dependencies

    def _extract_assignments(self, java_tasks) -> list[Assignment]:
        assignments: list[Assignment] = []
        for java_task in java_tasks:
            task_unique_id = self._as_int(safe_call(java_task, "getUniqueID", None))
            task_id = as_text(safe_call(java_task, "getID"))
            task_name = as_text(safe_call(java_task, "getName"))

            task_assignments = collection_items(
                safe_call(java_task, "getResourceAssignments", None)
            )
            for java_assignment in task_assignments:
                resource = safe_call(java_assignment, "getResource", None)
                assignments.append(
                    Assignment(
                        task_unique_id=task_unique_id,
                        resource_unique_id=self._as_int(safe_call(resource, "getUniqueID", None)),
                        task_id=task_id,
                        task_name=task_name,
                        resource_name=as_text(safe_call(resource, "getName")),
                        start=as_text(safe_call(java_assignment, "getStart")),
                        finish=as_text(safe_call(java_assignment, "getFinish")),
                        units=as_text(safe_call(java_assignment, "getUnits")),
                        work=as_text(safe_call(java_assignment, "getWork")),
                        actual_work=as_text(safe_call(java_assignment, "getActualWork")),
                        remaining_work=as_text(safe_call(java_assignment, "getRemainingWork")),
                        cost=as_text(safe_call(java_assignment, "getCost")),
                        actual_cost=as_text(safe_call(java_assignment, "getActualCost")),
                        remaining_cost=as_text(safe_call(java_assignment, "getRemainingCost")),
                    )
                )
        return assignments

    def _extract_project_properties(self, properties_object) -> list[tuple[str, str]]:
        if properties_object is None:
            return []

        return [
            ("Project Title", as_text(safe_call(properties_object, "getProjectTitle"))),
            ("Title", as_text(safe_call(properties_object, "getTitle"))),
            ("Subject", as_text(safe_call(properties_object, "getSubject"))),
            ("Author", as_text(safe_call(properties_object, "getAuthor"))),
            ("Manager", as_text(safe_call(properties_object, "getManager"))),
            ("Company", as_text(safe_call(properties_object, "getCompany"))),
            ("Category", as_text(safe_call(properties_object, "getCategory"))),
            ("Keywords", as_text(safe_call(properties_object, "getKeywords"))),
            ("Comments", as_text(safe_call(properties_object, "getComments"))),
            ("Creation Date", as_text(safe_call(properties_object, "getCreationDate"))),
            ("Last Saved", as_text(safe_call(properties_object, "getLastSaved"))),
            ("Last Author", as_text(safe_call(properties_object, "getLastAuthor"))),
            ("Application Version", as_text(safe_call(properties_object, "getApplicationVersion"))),
            ("File Application", as_text(safe_call(properties_object, "getFileApplication"))),
            ("File Type", as_text(safe_call(properties_object, "getFileType"))),
            ("Schedule From", as_text(safe_call(properties_object, "getScheduleFrom"))),
            ("Project Start Date", as_text(safe_call(properties_object, "getStartDate"))),
            ("Project Finish Date", as_text(safe_call(properties_object, "getFinishDate"))),
            ("Status Date", as_text(safe_call(properties_object, "getStatusDate"))),
            ("Current Date", as_text(safe_call(properties_object, "getCurrentDate"))),
            (
                "Default Calendar",
                as_text(safe_call(safe_call(properties_object, "getDefaultCalendar", None), "getName")),
            ),
            ("Minutes Per Day", as_text(safe_call(properties_object, "getMinutesPerDay"))),
            ("Minutes Per Week", as_text(safe_call(properties_object, "getMinutesPerWeek"))),
            ("Days Per Month", as_text(safe_call(properties_object, "getDaysPerMonth"))),
            ("Currency Symbol", as_text(safe_call(properties_object, "getCurrencySymbol"))),
            ("Currency Digits", as_text(safe_call(properties_object, "getCurrencyDigits"))),
            ("Default Task Type", as_text(safe_call(properties_object, "getDefaultTaskType"))),
            (
                "Default Fixed Cost Accrual",
                as_text(safe_call(properties_object, "getDefaultFixedCostAccrual")),
            ),
            ("New Tasks Estimated", as_bool_text(safe_call(properties_object, "getNewTasksEstimated"))),
            (
                "Auto Add New Resources and Tasks",
                as_bool_text(safe_call(properties_object, "getAutoAddNewResourcesAndTasks")),
            ),
        ]

    def _extract_messages(self, java_project) -> list[str]:
        ignored_errors = collection_items(safe_call(java_project, "getIgnoredErrors", None))
        return [as_text(error) for error in ignored_errors]

    def _link_children(self, project: Project) -> None:
        for task in project.tasks:
            if task.parent_unique_id is not None and task.parent_unique_id in project.tasks_by_unique_id:
                project.tasks_by_unique_id[task.parent_unique_id].child_unique_ids.append(task.unique_id)

    def _task_general_properties(self, java_task) -> list[tuple[str, str]]:
        parent_task = safe_call(java_task, "getParentTask", None)
        calendar = safe_call(java_task, "getCalendar", None)
        return [
            ("Name", as_text(safe_call(java_task, "getName"))),
            ("ID", as_text(safe_call(java_task, "getID"))),
            ("Unique ID", as_text(safe_call(java_task, "getUniqueID"))),
            ("GUID", as_text(safe_call(java_task, "getGUID"))),
            ("WBS", as_text(safe_call(java_task, "getWBS"))),
            ("Outline Number", as_text(safe_call(java_task, "getOutlineNumber"))),
            ("Outline Level", as_text(safe_call(java_task, "getOutlineLevel"))),
            ("Parent Task", as_text(safe_call(parent_task, "getName")) if parent_task else ""),
            ("Summary Task", as_bool_text(safe_call(java_task, "getSummary"))),
            ("Milestone", as_bool_text(safe_call(java_task, "getMilestone"))),
            ("Critical", as_bool_text(safe_call(java_task, "getCritical"))),
            ("Active", as_bool_text(safe_call(java_task, "getActive"))),
            ("External Task", as_bool_text(safe_call(java_task, "getExternalTask"))),
            ("Subproject", as_bool_text(safe_call(java_task, "getSubproject"))),
            ("Task Type", as_text(safe_call(java_task, "getType"))),
            ("Task Mode", as_text(safe_call(java_task, "getTaskMode"))),
            ("Priority", as_text(safe_call(java_task, "getPriority"))),
            ("Constraint Type", as_text(safe_call(java_task, "getConstraintType"))),
            ("Constraint Date", as_text(safe_call(java_task, "getConstraintDate"))),
            ("Calendar", as_text(safe_call(calendar, "getName")) if calendar else ""),
            ("Resource Names", as_text(safe_call(java_task, "getResourceNames"))),
            ("Contact", as_text(safe_call(java_task, "getContact"))),
            ("Hyperlink", as_text(safe_call(java_task, "getHyperlink"))),
            ("Hyperlink Address", as_text(safe_call(java_task, "getHyperlinkAddress"))),
            ("Hyperlink Sub-address", as_text(safe_call(java_task, "getHyperlinkSubAddress"))),
        ]

    def _task_schedule_properties(self, java_task) -> list[tuple[str, str]]:
        return [
            ("Start", as_text(safe_call(java_task, "getStart"))),
            ("Finish", as_text(safe_call(java_task, "getFinish"))),
            ("Duration", as_text(safe_call(java_task, "getDuration"))),
            ("Actual Start", as_text(safe_call(java_task, "getActualStart"))),
            ("Actual Finish", as_text(safe_call(java_task, "getActualFinish"))),
            ("Actual Duration", as_text(safe_call(java_task, "getActualDuration"))),
            ("Remaining Duration", as_text(safe_call(java_task, "getRemainingDuration"))),
            ("Baseline Start", as_text(safe_call(java_task, "getBaselineStart"))),
            ("Baseline Finish", as_text(safe_call(java_task, "getBaselineFinish"))),
            ("Baseline Duration", as_text(safe_call(java_task, "getBaselineDuration"))),
            ("Early Start", as_text(safe_call(java_task, "getEarlyStart"))),
            ("Early Finish", as_text(safe_call(java_task, "getEarlyFinish"))),
            ("Late Start", as_text(safe_call(java_task, "getLateStart"))),
            ("Late Finish", as_text(safe_call(java_task, "getLateFinish"))),
            ("Total Slack", as_text(safe_call(java_task, "getTotalSlack"))),
            ("Free Slack", as_text(safe_call(java_task, "getFreeSlack"))),
            ("% Complete", as_text(safe_call(java_task, "getPercentageComplete"))),
            ("% Work Complete", as_text(safe_call(java_task, "getPercentageWorkComplete"))),
            ("Deadline", as_text(safe_call(java_task, "getDeadline"))),
            ("Stop", as_text(safe_call(java_task, "getStop"))),
            ("Resume", as_text(safe_call(java_task, "getResume"))),
            ("Leveling Delay", as_text(safe_call(java_task, "getLevelingDelay"))),
            ("Ignore Resource Calendar", as_bool_text(safe_call(java_task, "getIgnoreResourceCalendar"))),
            ("Estimated", as_bool_text(safe_call(java_task, "getEstimated"))),
        ]

    def _task_cost_properties(self, java_task) -> list[tuple[str, str]]:
        return [
            ("Cost", as_text(safe_call(java_task, "getCost"))),
            ("Actual Cost", as_text(safe_call(java_task, "getActualCost"))),
            ("Remaining Cost", as_text(safe_call(java_task, "getRemainingCost"))),
            ("Fixed Cost", as_text(safe_call(java_task, "getFixedCost"))),
            ("Fixed Cost Accrual", as_text(safe_call(java_task, "getFixedCostAccrual"))),
            ("Baseline Cost", as_text(safe_call(java_task, "getBaselineCost"))),
            ("Cost Variance", as_text(safe_call(java_task, "getCostVariance"))),
            ("Work", as_text(safe_call(java_task, "getWork"))),
            ("Actual Work", as_text(safe_call(java_task, "getActualWork"))),
            ("Remaining Work", as_text(safe_call(java_task, "getRemainingWork"))),
            ("Baseline Work", as_text(safe_call(java_task, "getBaselineWork"))),
            ("Work Variance", as_text(safe_call(java_task, "getWorkVariance"))),
            ("Budget Cost", as_text(safe_call(java_task, "getBudgetCost"))),
            ("Budget Work", as_text(safe_call(java_task, "getBudgetWork"))),
            ("BCWS", as_text(safe_call(java_task, "getBCWS"))),
            ("BCWP", as_text(safe_call(java_task, "getBCWP"))),
            ("ACWP", as_text(safe_call(java_task, "getACWP"))),
            ("CPI", as_text(safe_call(java_task, "getCPI"))),
            ("SPI", as_text(safe_call(java_task, "getSPI"))),
            ("CV", as_text(safe_call(java_task, "getCV"))),
            ("SV", as_text(safe_call(java_task, "getSV"))),
            ("EAC", as_text(safe_call(java_task, "getEAC"))),
            ("VAC", as_text(safe_call(java_task, "getVAC"))),
            ("TCPI", as_text(safe_call(java_task, "getTCPI"))),
        ]

    def _resource_properties(self, java_resource) -> list[tuple[str, str]]:
        calendar = safe_call(java_resource, "getCalendar", None)
        return [
            ("Name", as_text(safe_call(java_resource, "getName"))),
            ("ID", as_text(safe_call(java_resource, "getID"))),
            ("Unique ID", as_text(safe_call(java_resource, "getUniqueID"))),
            ("GUID", as_text(safe_call(java_resource, "getGUID"))),
            ("Initials", as_text(safe_call(java_resource, "getInitials"))),
            ("Type", as_text(safe_call(java_resource, "getType"))),
            ("Email Address", as_text(safe_call(java_resource, "getEmailAddress"))),
            ("Group", as_text(safe_call(java_resource, "getGroup"))),
            ("Code", as_text(safe_call(java_resource, "getCode"))),
            ("Account", as_text(safe_call(java_resource, "getAccount"))),
            ("Active", as_bool_text(safe_call(java_resource, "getActive"))),
            ("Generic", as_bool_text(safe_call(java_resource, "getGeneric"))),
            ("Resource Calendar", as_text(safe_call(calendar, "getName")) if calendar else ""),
            ("Max Units", as_text(safe_call(java_resource, "getMaxUnits"))),
            ("Standard Rate", as_text(safe_call(java_resource, "getStandardRate"))),
            ("Overtime Rate", as_text(safe_call(java_resource, "getOvertimeRate"))),
            ("Cost Per Use", as_text(safe_call(java_resource, "getCostPerUse"))),
            ("Cost", as_text(safe_call(java_resource, "getCost"))),
            ("Actual Cost", as_text(safe_call(java_resource, "getActualCost"))),
            ("Remaining Cost", as_text(safe_call(java_resource, "getRemainingCost"))),
            ("Work", as_text(safe_call(java_resource, "getWork"))),
            ("Actual Work", as_text(safe_call(java_resource, "getActualWork"))),
            ("Remaining Work", as_text(safe_call(java_resource, "getRemainingWork"))),
            ("Baseline Work", as_text(safe_call(java_resource, "getBaselineWork"))),
            ("Start", as_text(safe_call(java_resource, "getStart"))),
            ("Finish", as_text(safe_call(java_resource, "getFinish"))),
        ]

    def _relation_target_ids(self, relations, direction: str) -> list[int]:
        ids: list[int] = []
        for relation in relations:
            related_task = self._relation_task(relation, direction)
            related_unique_id = self._as_int(safe_call(related_task, "getUniqueID", None))
            if related_unique_id is not None:
                ids.append(related_unique_id)
        return ids

    def _relation_task(self, relation, direction: str):
        if direction == "predecessor":
            method_names = ["getTargetTask", "getPredecessorTask", "getSourceTask"]
        else:
            method_names = ["getTargetTask", "getSuccessorTask", "getSourceTask"]

        for method_name in method_names:
            value = safe_call(relation, method_name, None)
            if value is not None:
                return value

        return None

    def _relation_lag(self, relation):
        lag = safe_call(relation, "getLag", None)
        if lag is None:
            lag = safe_call(relation, "getDuration", "")
        return lag

    def _describe_calendar_days(self, java_calendar) -> str:
        working_days: list[str] = []
        for day_name in (
            "SUNDAY",
            "MONDAY",
            "TUESDAY",
            "WEDNESDAY",
            "THURSDAY",
            "FRIDAY",
            "SATURDAY",
        ):
            try:
                day_class = jclass("net.sf.mpxj.Day")
                day_value = getattr(day_class, day_name)
                day_type = java_calendar.getCalendarDayType(day_value)
                if "WORKING" in as_text(day_type).upper():
                    working_days.append(day_name.title())
            except Exception:
                continue
        return ", ".join(working_days)

    def _as_int(self, value, default=None):
        if value is None:
            return default
        try:
            return int(str(value))
        except Exception:
            return default

    def _as_bool(self, value, default=False) -> bool:
        if value is None:
            return default
        return str(value).strip().lower() == "true"
