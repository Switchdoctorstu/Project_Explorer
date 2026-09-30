from __future__ import annotations

import sys
import webbrowser
import csv
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import jpype

from .analysis import build_summary_text, analyse_schedule
from .core import MpxjSession, flatten_exception
from .gui import PropertyGrid, ScrollableTree
from .model import Project, ProjectExtractor, Task
from .reporting import (
    export_static_gantt,
    export_static_viewer,
    export_tree_to_csv,
    open_dynamic_gantt,
    open_dynamic_viewer,
)

APP_TITLE = "MPP Programme Explorer"
JAR_NAME = "projectlibre-1.9.8.jar"
SCRIPT_DIR = Path(__file__).resolve().parent.parent
JAR_PATH = SCRIPT_DIR / JAR_NAME
REPORTS_DIR = SCRIPT_DIR / "REPORTS"


class ProgrammeExplorer:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1600x920")
        self.root.minsize(1100, 700)

        self.project: Project | None = None
        self.session = MpxjSession(JAR_PATH)
        self.extractor = ProjectExtractor()
        self.current_file: Path | None = None

        self.task_by_tree_id: dict[str, Task] = {}
        self.task_by_unique_id: dict[int, Task] = {}
        self.resource_by_unique_id: dict[int, object] = {}

        self.status_text = tk.StringVar(value="Starting...")
        self.filter_text = tk.StringVar()
        self.file_text = tk.StringVar(value="No programme loaded")
        self.summary_text = tk.StringVar(value="")

        self._configure_style()
        self._build_menu()
        self._build_interface()

        self.root.report_callback_exception = self._handle_tk_callback_exception
        self.root.protocol("WM_DELETE_WINDOW", self.close_application)
        self.root.after(50, self.start_jvm)

    def _log_exception(self, context: str, exception: BaseException):
        print(f"\n[{APP_TITLE}] {context}", file=sys.stderr)
        traceback.print_exception(type(exception), exception, exception.__traceback__, file=sys.stderr)

    def _show_error(self, title: str, summary: str, exception: BaseException | None = None):
        if exception is not None:
            self._log_exception(title, exception)
            details = flatten_exception(exception)
            messagebox.showerror(
                title,
                f"{summary}\n\n{details}\n\nSee console output for the full traceback.",
            )
            return
        messagebox.showerror(title, summary)

    def _handle_tk_callback_exception(self, exc_type, exc_value, exc_traceback):
        print(f"\n[{APP_TITLE}] Unhandled Tkinter callback exception", file=sys.stderr)
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
        self._show_error(
            "Unexpected application error",
            "An unexpected error occurred while handling a UI action.",
            exc_value,
        )

    def _configure_style(self):
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        style.configure("Treeview", rowheight=24)
        style.configure("Heading.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Summary.TLabel", font=("Segoe UI", 10))
        style.configure("Status.TLabel", relief="sunken", padding=(6, 3))

    def _build_menu(self):
        menu_bar = tk.Menu(self.root)

        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Open MPP...", accelerator="Ctrl+O", command=self.open_mpp)
        file_menu.add_separator()
        file_menu.add_command(label="Export task register...", command=self.export_tasks_csv)
        file_menu.add_command(label="Export resource register...", command=self.export_resources_csv)
        file_menu.add_command(label="Export dependency register...", command=self.export_dependencies_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Open 3D Network preview", command=self.open_3d_network_preview)
        file_menu.add_command(label="Export 3D Network visualisation...", command=self.export_3d_network_visualisation)
        file_menu.add_command(label="Open 3D Gantt preview", command=self.open_3d_gantt_preview)
        file_menu.add_command(label="Export 3D Gantt visualisation...", command=self.export_3d_gantt_visualisation)
        file_menu.add_separator()
        file_menu.add_command(label="Export schedule analysis (CSV)...", command=self.export_schedule_analysis_csv)
        file_menu.add_command(label="Export bottleneck report (CSV)...", command=self.export_bottleneck_report_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.close_application)

        view_menu = tk.Menu(menu_bar, tearoff=False)
        view_menu.add_command(label="Expand all tasks", command=self.expand_all_tasks)
        view_menu.add_command(label="Collapse all tasks", command=self.collapse_all_tasks)
        view_menu.add_separator()
        view_menu.add_command(label="Show all tasks", command=self.clear_filter)

        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(label="Environment information", command=self.show_environment_information)
        help_menu.add_command(label="About", command=self.show_about)

        menu_bar.add_cascade(label="File", menu=file_menu)
        menu_bar.add_cascade(label="View", menu=view_menu)
        menu_bar.add_cascade(label="Help", menu=help_menu)

        self.root.configure(menu=menu_bar)
        self.root.bind("<Control-o>", lambda event: self.open_mpp())

    def _build_interface(self):
        self._build_toolbar()
        self._build_summary_strip()
        self._build_notebook()
        self._build_status_bar()

    def _build_toolbar(self):
        toolbar = ttk.Frame(self.root, padding=(8, 6))
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="Open MPP", command=self.open_mpp).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="Expand All", command=self.expand_all_tasks).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Collapse All", command=self.collapse_all_tasks).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Export Tasks", command=self.export_tasks_csv).pack(side="left", padx=3)
        ttk.Button(toolbar, text="3D Network", command=self.open_3d_network_preview).pack(side="left", padx=3)
        ttk.Button(toolbar, text="3D Gantt", command=self.open_3d_gantt_preview).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Bottlenecks", command=self.export_bottleneck_report_csv).pack(side="left", padx=3)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=10)

        ttk.Label(toolbar, text="Find task:").pack(side="left", padx=(0, 5))
        filter_entry = ttk.Entry(toolbar, textvariable=self.filter_text, width=35)
        filter_entry.pack(side="left", padx=(0, 5))
        filter_entry.bind("<Return>", lambda event: self.apply_task_filter())

        ttk.Button(toolbar, text="Find", command=self.apply_task_filter).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Clear", command=self.clear_filter).pack(side="left", padx=3)

        ttk.Label(toolbar, textvariable=self.file_text).pack(side="right", padx=5)

    def _build_summary_strip(self):
        summary_frame = ttk.Frame(self.root, padding=(10, 3))
        summary_frame.pack(fill="x")
        ttk.Label(summary_frame, textvariable=self.summary_text, style="Summary.TLabel").pack(anchor="w")

    def _build_notebook(self):
        self.main_notebook = ttk.Notebook(self.root)
        self.main_notebook.pack(fill="both", expand=True, padx=8, pady=5)

        self._build_programme_tab()
        self._build_task_register_tab()
        self._build_milestones_tab()
        self._build_dependencies_tab()
        self._build_resources_tab()
        self._build_assignments_tab()
        self._build_calendars_tab()
        self._build_project_properties_tab()
        self._build_import_messages_tab()

    def _build_programme_tab(self):
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="Programme Structure")

        paned = ttk.Panedwindow(tab, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left_frame = ttk.Frame(paned, padding=4)
        right_frame = ttk.Frame(paned, padding=4)
        paned.add(left_frame, weight=3)
        paned.add(right_frame, weight=2)

        columns = ("ID", "WBS", "Start", "Finish", "Duration", "Complete", "Milestone", "Critical")
        self.programme_tree_frame = ScrollableTree(left_frame, columns=columns, headings={"Complete": "% Complete"}, tree_column=True)
        self.programme_tree_frame.pack(fill="both", expand=True)

        self.programme_tree = self.programme_tree_frame.tree
        self.programme_tree.heading("#0", text="Programme / Task")
        self.programme_tree.column("#0", width=440, minwidth=250)

        widths = {
            "ID": 65,
            "WBS": 100,
            "Start": 155,
            "Finish": 155,
            "Duration": 100,
            "Complete": 90,
            "Milestone": 85,
            "Critical": 75,
        }
        for column, width in widths.items():
            self.programme_tree.column(column, width=width, minwidth=50, stretch=False)

        self.programme_tree.tag_configure("summary", font=("Segoe UI", 9, "bold"))
        self.programme_tree.tag_configure("milestone", foreground="#005A9C")
        self.programme_tree.tag_configure("critical", foreground="#B00020")
        self.programme_tree.tag_configure("inactive", foreground="#777777")

        self.programme_tree.bind("<<TreeviewSelect>>", self.on_programme_task_selected)
        self.programme_tree.bind("<Double-1>", self.on_programme_task_double_click)

        self.task_detail_notebook = ttk.Notebook(right_frame)
        self.task_detail_notebook.pack(fill="both", expand=True)

        general_tab = ttk.Frame(self.task_detail_notebook)
        schedule_tab = ttk.Frame(self.task_detail_notebook)
        cost_tab = ttk.Frame(self.task_detail_notebook)
        relationship_tab = ttk.Frame(self.task_detail_notebook)
        notes_tab = ttk.Frame(self.task_detail_notebook)

        self.task_detail_notebook.add(general_tab, text="General")
        self.task_detail_notebook.add(schedule_tab, text="Schedule")
        self.task_detail_notebook.add(cost_tab, text="Cost and Work")
        self.task_detail_notebook.add(relationship_tab, text="Relationships")
        self.task_detail_notebook.add(notes_tab, text="Notes")

        self.task_general_grid = PropertyGrid(general_tab)
        self.task_general_grid.pack(fill="both", expand=True)
        self.task_schedule_grid = PropertyGrid(schedule_tab)
        self.task_schedule_grid.pack(fill="both", expand=True)
        self.task_cost_grid = PropertyGrid(cost_tab)
        self.task_cost_grid.pack(fill="both", expand=True)

        relationship_paned = ttk.Panedwindow(relationship_tab, orient="vertical")
        relationship_paned.pack(fill="both", expand=True)

        predecessor_frame = ttk.LabelFrame(relationship_paned, text="Predecessors", padding=4)
        successor_frame = ttk.LabelFrame(relationship_paned, text="Successors", padding=4)
        assignment_frame = ttk.LabelFrame(relationship_paned, text="Resource Assignments", padding=4)

        relationship_paned.add(predecessor_frame, weight=1)
        relationship_paned.add(successor_frame, weight=1)
        relationship_paned.add(assignment_frame, weight=1)

        relation_columns = ("ID", "Task", "Type", "Lag")
        self.task_predecessor_tree = ScrollableTree(predecessor_frame, relation_columns, tree_column=False)
        self.task_predecessor_tree.pack(fill="both", expand=True)
        self.task_successor_tree = ScrollableTree(successor_frame, relation_columns, tree_column=False)
        self.task_successor_tree.pack(fill="both", expand=True)

        assignment_columns = ("Resource", "Units", "Work", "Actual Work", "Cost")
        self.task_assignment_tree = ScrollableTree(assignment_frame, assignment_columns, tree_column=False)
        self.task_assignment_tree.pack(fill="both", expand=True)

        self.task_notes_text = tk.Text(notes_tab, wrap="word", font=("Segoe UI", 10))
        notes_scrollbar = ttk.Scrollbar(notes_tab, orient="vertical", command=self.task_notes_text.yview)
        self.task_notes_text.configure(yscrollcommand=notes_scrollbar.set)
        self.task_notes_text.pack(side="left", fill="both", expand=True)
        notes_scrollbar.pack(side="right", fill="y")

    def _build_task_register_tab(self):
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="Task Register")

        columns = (
            "ID",
            "Unique ID",
            "WBS",
            "Outline Level",
            "Name",
            "Start",
            "Finish",
            "Duration",
            "% Complete",
            "Summary",
            "Milestone",
            "Critical",
            "Active",
            "Resource Names",
            "Predecessors",
        )

        self.task_register = ScrollableTree(tab, columns, tree_column=False)
        self.task_register.pack(fill="both", expand=True)

        for column in columns:
            width = 120
            if column == "Name":
                width = 360
            elif column in ("Start", "Finish"):
                width = 165
            elif column in ("Resource Names", "Predecessors"):
                width = 220
            elif column in ("ID", "Unique ID", "Outline Level"):
                width = 85
            self.task_register.tree.column(column, width=width)

        self.task_register.tree.bind("<Double-1>", self.open_task_from_register)

    def _build_milestones_tab(self):
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="Milestones")

        columns = ("ID", "WBS", "Milestone", "Date", "% Complete", "Critical", "Predecessors", "Successors")
        self.milestone_tree = ScrollableTree(tab, columns, tree_column=False)
        self.milestone_tree.pack(fill="both", expand=True)
        self.milestone_tree.tree.column("Milestone", width=420)
        self.milestone_tree.tree.column("Date", width=170)
        self.milestone_tree.tree.column("Predecessors", width=220)
        self.milestone_tree.tree.column("Successors", width=220)

    def _build_dependencies_tab(self):
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="Dependencies")

        columns = ("Successor ID", "Successor", "Predecessor ID", "Predecessor", "Type", "Lag")
        self.dependency_tree = ScrollableTree(tab, columns, tree_column=False)
        self.dependency_tree.pack(fill="both", expand=True)
        self.dependency_tree.tree.column("Successor", width=330)
        self.dependency_tree.tree.column("Predecessor", width=330)

    def _build_resources_tab(self):
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="Resources")

        paned = ttk.Panedwindow(tab, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left_frame = ttk.Frame(paned, padding=4)
        right_frame = ttk.Frame(paned, padding=4)
        paned.add(left_frame, weight=3)
        paned.add(right_frame, weight=2)

        columns = (
            "ID",
            "Unique ID",
            "Name",
            "Initials",
            "Type",
            "Email",
            "Group",
            "Max Units",
            "Standard Rate",
            "Overtime Rate",
            "Cost/Use",
            "Calendar",
        )

        self.resource_tree = ScrollableTree(left_frame, columns, tree_column=False)
        self.resource_tree.pack(fill="both", expand=True)
        self.resource_tree.tree.column("Name", width=240)
        self.resource_tree.tree.column("Email", width=260)
        self.resource_tree.tree.bind("<<TreeviewSelect>>", self.on_resource_selected)

        self.resource_detail_grid = PropertyGrid(right_frame)
        self.resource_detail_grid.pack(fill="both", expand=True)

    def _build_assignments_tab(self):
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="Assignments")

        columns = (
            "Task ID",
            "Task",
            "Resource",
            "Start",
            "Finish",
            "Units",
            "Work",
            "Actual Work",
            "Remaining Work",
            "Cost",
            "Actual Cost",
            "Remaining Cost",
        )

        self.assignment_tree = ScrollableTree(tab, columns, tree_column=False)
        self.assignment_tree.pack(fill="both", expand=True)
        self.assignment_tree.tree.column("Task", width=320)
        self.assignment_tree.tree.column("Resource", width=220)
        self.assignment_tree.tree.column("Start", width=165)
        self.assignment_tree.tree.column("Finish", width=165)

    def _build_calendars_tab(self):
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="Calendars")

        paned = ttk.Panedwindow(tab, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left_frame = ttk.Frame(paned, padding=4)
        right_frame = ttk.Frame(paned, padding=4)
        paned.add(left_frame, weight=2)
        paned.add(right_frame, weight=3)

        columns = ("Unique ID", "Name", "Type", "Parent", "Working Days")
        self.calendar_tree = ScrollableTree(left_frame, columns, tree_column=False)
        self.calendar_tree.pack(fill="both", expand=True)
        self.calendar_tree.tree.column("Name", width=250)
        self.calendar_tree.tree.column("Working Days", width=260)
        self.calendar_tree.tree.bind("<<TreeviewSelect>>", self.on_calendar_selected)

        self.calendar_detail_grid = PropertyGrid(right_frame)
        self.calendar_detail_grid.pack(fill="both", expand=True)

    def _build_project_properties_tab(self):
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="Project Properties")
        self.project_property_grid = PropertyGrid(tab)
        self.project_property_grid.pack(fill="both", expand=True)

    def _build_import_messages_tab(self):
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="Import Messages")

        self.import_messages_text = tk.Text(tab, wrap="word", font=("Consolas", 10))
        vertical_scrollbar = ttk.Scrollbar(tab, orient="vertical", command=self.import_messages_text.yview)
        self.import_messages_text.configure(yscrollcommand=vertical_scrollbar.set)
        self.import_messages_text.pack(side="left", fill="both", expand=True)
        vertical_scrollbar.pack(side="right", fill="y")

    def _build_status_bar(self):
        ttk.Label(self.root, textvariable=self.status_text, style="Status.TLabel", anchor="w").pack(fill="x", side="bottom")

    def reports_dir(self) -> Path:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        return REPORTS_DIR

    def start_jvm(self):
        try:
            self.session.start()
            self.status_text.set(f"Ready. MPXJ loaded using Java {self.session.java_version}")
        except Exception as exception:
            self.status_text.set("JVM initialisation failed")
            self._show_error(
                "Java / MPXJ error",
                "The programme explorer could not initialise MPXJ.\n\n"
                "Confirm that JDK 21 is active and that "
                f"{JAR_NAME} is beside this Python script.",
                exception,
            )

    def open_mpp(self):
        filename = filedialog.askopenfilename(
            title="Open Microsoft Project programme",
            filetypes=[
                ("Microsoft Project files", "*.mpp"),
                ("Microsoft Project templates", "*.mpt"),
                ("Microsoft Project XML", "*.xml"),
                ("All files", "*.*"),
            ],
        )

        if not filename:
            return

        self.status_text.set(f"Reading {Path(filename).name}...")
        self.root.update_idletasks()

        try:
            java_project = self.session.read_project(str(filename))
            self.project = self.extractor.extract(java_project, filename)
            self.current_file = Path(filename)

            self.file_text.set(self.current_file.name)
            self.root.title(f"{APP_TITLE} - {self.current_file.name}")

            self.refresh_all_views()
            self.status_text.set(f"Loaded {self.current_file}")

        except Exception as exception:
            self.project = None
            self.status_text.set("Programme load failed")
            self._show_error(
                "Could not open programme",
                "The selected file could not be read.",
                exception,
            )

    def refresh_all_views(self):
        self.clear_all_views()
        self.index_project_entities()

        self.populate_programme_structure()
        self.populate_task_register()
        self.populate_milestones()
        self.populate_dependencies()
        self.populate_resources()
        self.populate_assignments()
        self.populate_calendars()
        self.populate_project_properties()
        self.populate_import_messages()
        self.populate_summary()

    def clear_all_views(self):
        self.task_by_tree_id.clear()
        self.task_by_unique_id.clear()
        self.resource_by_unique_id.clear()

        for component in (
            self.programme_tree_frame,
            self.task_register,
            self.milestone_tree,
            self.dependency_tree,
            self.resource_tree,
            self.assignment_tree,
            self.calendar_tree,
        ):
            component.clear()

        self.task_general_grid.clear()
        self.task_schedule_grid.clear()
        self.task_cost_grid.clear()
        self.resource_detail_grid.clear()
        self.calendar_detail_grid.clear()
        self.project_property_grid.clear()
        self.task_predecessor_tree.clear()
        self.task_successor_tree.clear()
        self.task_assignment_tree.clear()

        self.task_notes_text.delete("1.0", "end")
        self.import_messages_text.delete("1.0", "end")

    def index_project_entities(self):
        if self.project is None:
            return
        self.task_by_unique_id = dict(self.project.tasks_by_unique_id)
        self.resource_by_unique_id = dict(self.project.resources_by_unique_id)

    def populate_programme_structure(self):
        if self.project is None:
            return

        roots = self.project.root_tasks() or self.project.tasks
        visited: set[int] = set()
        for task in roots:
            self.insert_task_node("", task, visited)

    def insert_task_node(self, parent_tree_id, task: Task, visited: set[int]):
        if task.unique_id in visited:
            return
        visited.add(task.unique_id)

        tags = []
        if task.is_summary:
            tags.append("summary")
        if task.is_milestone:
            tags.append("milestone")
        if task.is_critical:
            tags.append("critical")
        if not task.is_active:
            tags.append("inactive")

        tree_id = self.programme_tree.insert(
            parent_tree_id,
            "end",
            text=task.display_label(),
            values=(
                task.id,
                task.wbs,
                task.start,
                task.finish,
                task.duration,
                task.percent_complete,
                "Yes" if task.is_milestone else "No",
                "Yes" if task.is_critical else "No",
            ),
            tags=tuple(tags),
            open=False,
        )

        self.task_by_tree_id[tree_id] = task
        if self.project is None:
            return
        for child in self.project.task_children(task):
            self.insert_task_node(tree_id, child, visited)

    def on_programme_task_selected(self, event=None):
        selection = self.programme_tree.selection()
        if not selection:
            return
        task = self.task_by_tree_id.get(selection[0])
        if task:
            self.display_task_details(task)

    def on_programme_task_double_click(self, event=None):
        item_id = self.programme_tree.identify_row(event.y)
        if not item_id:
            return
        current_state = self.programme_tree.item(item_id, "open")
        self.programme_tree.item(item_id, open=not current_state)

    def display_task_details(self, task: Task):
        self.task_general_grid.populate(task.general_properties)
        self.task_schedule_grid.populate(task.schedule_properties)
        self.task_cost_grid.populate(task.cost_properties)
        self.populate_selected_task_relationships(task)

        self.task_notes_text.delete("1.0", "end")
        self.task_notes_text.insert("1.0", task.notes)

    def populate_task_register(self, task_filter=""):
        self.task_register.clear()
        if self.project is None:
            return

        filter_value = task_filter.strip().lower()
        for task in self.project.tasks:
            searchable = " ".join([task.name, task.wbs, task.id, str(task.unique_id)]).lower()
            if filter_value and filter_value not in searchable:
                continue

            predecessors = self.describe_predecessors(task)
            self.task_register.tree.insert(
                "",
                "end",
                values=(
                    task.id,
                    str(task.unique_id),
                    task.wbs,
                    str(task.outline_level),
                    task.name,
                    task.start,
                    task.finish,
                    task.duration,
                    task.percent_complete,
                    "Yes" if task.is_summary else "No",
                    "Yes" if task.is_milestone else "No",
                    "Yes" if task.is_critical else "No",
                    "Yes" if task.is_active else "No",
                    task.resource_names,
                    predecessors,
                ),
            )

    def apply_task_filter(self):
        if self.project is None:
            return

        filter_value = self.filter_text.get().strip()
        self.populate_task_register(filter_value)

        match = self.find_programme_tree_match(filter_value)
        if match:
            self.programme_tree.selection_set(match)
            self.programme_tree.focus(match)
            self.programme_tree.see(match)
            self.main_notebook.select(0)

    def find_programme_tree_match(self, filter_value):
        if not filter_value:
            return None

        target = filter_value.lower()
        for tree_id, task in self.task_by_tree_id.items():
            searchable = " ".join([task.name, task.wbs, task.id, str(task.unique_id)]).lower()
            if target in searchable:
                self.open_parent_nodes(tree_id)
                return tree_id

        return None

    def open_parent_nodes(self, tree_id):
        parent_id = self.programme_tree.parent(tree_id)
        while parent_id:
            self.programme_tree.item(parent_id, open=True)
            parent_id = self.programme_tree.parent(parent_id)

    def clear_filter(self):
        self.filter_text.set("")
        if self.project is not None:
            self.populate_task_register()

    def open_task_from_register(self, event=None):
        item_id = self.task_register.tree.identify_row(event.y)
        if not item_id:
            return
        unique_id_text = self.task_register.tree.set(item_id, "Unique ID")
        try:
            unique_id = int(unique_id_text)
        except Exception:
            return
        self.select_task_by_unique_id(unique_id)

    def select_task_by_unique_id(self, unique_id: int):
        for tree_id, task in self.task_by_tree_id.items():
            if task.unique_id == unique_id:
                self.open_parent_nodes(tree_id)
                self.programme_tree.selection_set(tree_id)
                self.programme_tree.focus(tree_id)
                self.programme_tree.see(tree_id)
                self.display_task_details(task)
                self.main_notebook.select(0)
                return

    def populate_selected_task_relationships(self, task: Task):
        self.task_predecessor_tree.clear()
        self.task_successor_tree.clear()
        self.task_assignment_tree.clear()

        if self.project is None:
            return

        for dependency in self.project.dependencies:
            if dependency.successor_unique_id == task.unique_id:
                self.task_predecessor_tree.tree.insert(
                    "",
                    "end",
                    values=(dependency.predecessor_id, dependency.predecessor_name, dependency.relation_type, dependency.lag),
                )

            if dependency.predecessor_unique_id == task.unique_id:
                self.task_successor_tree.tree.insert(
                    "",
                    "end",
                    values=(dependency.successor_id, dependency.successor_name, dependency.relation_type, dependency.lag),
                )

        for assignment in self.project.assignments:
            if assignment.task_unique_id == task.unique_id:
                self.task_assignment_tree.tree.insert(
                    "",
                    "end",
                    values=(
                        assignment.resource_name,
                        assignment.units,
                        assignment.work,
                        assignment.actual_work,
                        assignment.cost,
                    ),
                )

    def describe_predecessors(self, task: Task) -> str:
        if self.project is None:
            return ""
        descriptions = []
        for dependency in self.project.dependencies:
            if dependency.successor_unique_id != task.unique_id:
                continue
            description = dependency.predecessor_id
            if dependency.relation_type:
                description = f"{description} {dependency.relation_type}".strip()
            if description:
                descriptions.append(description)
        return ", ".join(descriptions)

    def describe_successors(self, task: Task) -> str:
        if self.project is None:
            return ""
        descriptions = []
        for dependency in self.project.dependencies:
            if dependency.predecessor_unique_id != task.unique_id:
                continue
            description = dependency.successor_id
            if dependency.relation_type:
                description = f"{description} {dependency.relation_type}".strip()
            if description:
                descriptions.append(description)
        return ", ".join(descriptions)

    def populate_dependencies(self):
        if self.project is None:
            return
        for dependency in self.project.dependencies:
            self.dependency_tree.tree.insert(
                "",
                "end",
                values=(
                    dependency.successor_id,
                    dependency.successor_name,
                    dependency.predecessor_id,
                    dependency.predecessor_name,
                    dependency.relation_type,
                    dependency.lag,
                ),
            )

    def populate_milestones(self):
        if self.project is None:
            return
        for task in self.project.tasks:
            if not task.is_milestone:
                continue
            self.milestone_tree.tree.insert(
                "",
                "end",
                values=(
                    task.id,
                    task.wbs,
                    task.name,
                    task.finish,
                    task.percent_complete,
                    "Yes" if task.is_critical else "No",
                    self.describe_predecessors(task),
                    self.describe_successors(task),
                ),
            )

    def populate_resources(self):
        if self.project is None:
            return
        for resource in self.project.resources:
            if not resource.name and not resource.id:
                continue
            self.resource_tree.tree.insert(
                "",
                "end",
                values=(
                    resource.id,
                    str(resource.unique_id),
                    resource.name,
                    resource.initials,
                    resource.resource_type,
                    resource.email,
                    resource.group,
                    resource.max_units,
                    resource.standard_rate,
                    resource.overtime_rate,
                    resource.cost_per_use,
                    resource.calendar_name,
                ),
            )

    def on_resource_selected(self, event=None):
        if self.project is None:
            return

        selection = self.resource_tree.tree.selection()
        if not selection:
            return

        item_id = selection[0]
        unique_id_text = self.resource_tree.tree.set(item_id, "Unique ID")
        try:
            unique_id = int(unique_id_text)
        except Exception:
            return

        resource = self.project.resources_by_unique_id.get(unique_id)
        if resource is None:
            return

        self.resource_detail_grid.populate(resource.properties)

    def populate_assignments(self):
        if self.project is None:
            return
        for assignment in self.project.assignments:
            self.assignment_tree.tree.insert(
                "",
                "end",
                values=(
                    assignment.task_id,
                    assignment.task_name,
                    assignment.resource_name,
                    assignment.start,
                    assignment.finish,
                    assignment.units,
                    assignment.work,
                    assignment.actual_work,
                    assignment.remaining_work,
                    assignment.cost,
                    assignment.actual_cost,
                    assignment.remaining_cost,
                ),
            )

    def populate_calendars(self):
        if self.project is None:
            return

        for calendar in self.project.calendars:
            self.calendar_tree.tree.insert(
                "",
                "end",
                values=(
                    str(calendar.unique_id) if calendar.unique_id is not None else "",
                    calendar.name,
                    calendar.calendar_type,
                    calendar.parent_name,
                    calendar.working_days,
                ),
            )

    def on_calendar_selected(self, event=None):
        if self.project is None:
            return

        selection = self.calendar_tree.tree.selection()
        if not selection:
            return

        item_id = selection[0]
        unique_id_text = self.calendar_tree.tree.set(item_id, "Unique ID")
        try:
            unique_id = int(unique_id_text)
        except Exception:
            return

        calendar = self.project.calendars_by_unique_id.get(unique_id)
        if calendar is None:
            return

        self.calendar_detail_grid.populate(calendar.properties)

    def populate_project_properties(self):
        if self.project is None:
            return
        self.project_property_grid.populate(self.project.properties)

    def populate_import_messages(self):
        if self.project is None:
            return

        if not self.project.import_messages:
            self.import_messages_text.insert("end", "No ignored import errors were reported by MPXJ.")
            return

        for index, message in enumerate(self.project.import_messages, start=1):
            self.import_messages_text.insert("end", f"{index}. {message}\n\n")

    def populate_summary(self):
        if self.project is None:
            self.summary_text.set("")
            return
        self.summary_text.set(build_summary_text(self.project))

    def expand_all_tasks(self):
        self.set_tree_open_state("", True)

    def collapse_all_tasks(self):
        self.set_tree_open_state("", False)

    def set_tree_open_state(self, parent_id, open_state):
        for item_id in self.programme_tree.get_children(parent_id):
            self.programme_tree.item(item_id, open=open_state)
            self.set_tree_open_state(item_id, open_state)

    def export_component_csv(self, tree_component, default_filename):
        if self.project is None:
            messagebox.showwarning("No programme", "Open an MPP file before exporting.")
            return

        filename = filedialog.asksaveasfilename(
            title="Export register",
            initialdir=str(self.reports_dir()),
            initialfile=default_filename,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )

        if not filename:
            return

        try:
            export_tree_to_csv(tree_component.tree, filename)
            self.status_text.set(f"Exported {filename}")
            messagebox.showinfo("Export complete", f"The register was exported successfully.\n\n{filename}")
        except Exception as exception:
            self._show_error("Export failed", "The register export failed.", exception)

    def export_tasks_csv(self):
        source_name = self.current_file.stem if self.current_file else "programme"
        self.export_component_csv(self.task_register, f"{source_name}_tasks.csv")

    def export_resources_csv(self):
        source_name = self.current_file.stem if self.current_file else "programme"
        self.export_component_csv(self.resource_tree, f"{source_name}_resources.csv")

    def export_dependencies_csv(self):
        source_name = self.current_file.stem if self.current_file else "programme"
        self.export_component_csv(self.dependency_tree, f"{source_name}_dependencies.csv")

    def _export_rows_csv(self, default_filename: str, headers: list[str], rows: list[list[object]]):
        if self.project is None:
            messagebox.showwarning("No programme", "Open an MPP file before exporting.")
            return

        filename = filedialog.asksaveasfilename(
            title="Export CSV",
            initialdir=str(self.reports_dir()),
            initialfile=default_filename,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )

        if not filename:
            return

        try:
            with open(filename, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
                writer.writerows(rows)
            self.status_text.set(f"Exported {filename}")
            messagebox.showinfo("Export complete", f"The CSV export completed successfully.\n\n{filename}")
        except Exception as exception:
            self._show_error("Export failed", "The CSV export failed.", exception)

    def export_schedule_analysis_csv(self):
        if self.project is None:
            messagebox.showwarning("No programme", "Open an MPP file before exporting.")
            return

        analysis = analyse_schedule(self.project)
        headers = [
            "Task Unique ID",
            "Task ID",
            "Task Name",
            "Early Start",
            "Early Finish",
            "Late Start",
            "Late Finish",
            "Total Float (days)",
            "Free Float (days)",
            "Critical",
            "Near Critical",
            "Constraint Type",
            "Constraint Date",
            "Unresolved Constraint",
            "Cycle Participant",
        ]

        rows: list[list[object]] = []
        for task in sorted(self.project.tasks, key=lambda item: item.unique_id):
            metrics = analysis.task_metrics.get(task.unique_id)
            if metrics is None:
                continue
            rows.append(
                [
                    task.unique_id,
                    task.id,
                    task.name,
                    metrics.early_start,
                    metrics.early_finish,
                    metrics.late_start,
                    metrics.late_finish,
                    metrics.total_float_days,
                    metrics.free_float_days,
                    "Yes" if metrics.is_critical else "No",
                    "Yes" if metrics.is_near_critical else "No",
                    metrics.constraint_type,
                    metrics.constraint_date,
                    "Yes" if metrics.unresolved_constraint else "No",
                    "Yes" if metrics.cycle_participant else "No",
                ]
            )

        source_name = self.current_file.stem if self.current_file else "programme"
        self._export_rows_csv(f"{source_name}_schedule_analysis.csv", headers, rows)

    def export_bottleneck_report_csv(self):
        if self.project is None:
            messagebox.showwarning("No programme", "Open an MPP file before exporting.")
            return

        analysis = analyse_schedule(self.project)
        task_by_id = {task.unique_id: task for task in self.project.tasks}

        headers = [
            "Rank",
            "Task Unique ID",
            "Task ID",
            "Task Name",
            "Bottleneck Score",
            "Criticality",
            "Float",
            "Fan",
            "Resource",
            "Cost",
            "Duration",
            "Constraint",
        ]

        rows: list[list[object]] = []
        for rank, item in enumerate(analysis.top_bottlenecks, start=1):
            task = task_by_id.get(item.unique_id)
            rows.append(
                [
                    rank,
                    item.unique_id,
                    task.id if task else "",
                    task.name if task else "",
                    item.score,
                    item.components.get("criticality", 0.0),
                    item.components.get("float", 0.0),
                    item.components.get("fan", 0.0),
                    item.components.get("resource", 0.0),
                    item.components.get("cost", 0.0),
                    item.components.get("duration", 0.0),
                    item.components.get("constraint", 0.0),
                ]
            )

        source_name = self.current_file.stem if self.current_file else "programme"
        self._export_rows_csv(f"{source_name}_bottlenecks.csv", headers, rows)

    def open_3d_network_preview(self):
        if self.project is None:
            messagebox.showwarning("No programme", "Open an MPP file before creating a visualisation.")
            return

        source_name = self.current_file.stem if self.current_file else "programme"

        try:
            url = open_dynamic_viewer(
                self.project,
                self.reports_dir(),
                filename=f"{source_name}_3d_preview.html",
            )
            self.status_text.set(f"Preview ready: {url}")
        except Exception as exception:
            self._show_error("3D preview failed", "The 3D Network preview could not be generated.", exception)

    def export_3d_network_visualisation(self):
        if self.project is None:
            messagebox.showwarning("No programme", "Open an MPP file before creating a visualisation.")
            return

        source_name = self.current_file.stem if self.current_file else "programme"
        filename = filedialog.asksaveasfilename(
            title="Save 3D visualisation",
            initialdir=str(self.reports_dir()),
            initialfile=f"{source_name}_3d_visualisation.html",
            defaultextension=".html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
        )

        if not filename:
            return

        try:
            output = export_static_viewer(self.project, filename)
            self.status_text.set(f"Exported {output}")

            open_now = messagebox.askyesno(
                "3D visualisation exported",
                f"The 3D visualisation was created successfully.\n\n{output}\n\nOpen it now in your browser?",
            )
            if open_now:
                webbrowser.open(output.resolve().as_uri())
        except Exception as exception:
            self._show_error("Visualisation export failed", "The 3D Network visualisation export failed.", exception)

    def open_3d_gantt_preview(self):
        if self.project is None:
            messagebox.showwarning("No programme", "Open an MPP file before creating a visualisation.")
            return

        source_name = self.current_file.stem if self.current_file else "programme"

        try:
            url = open_dynamic_gantt(
                self.project,
                self.reports_dir(),
                filename=f"{source_name}_3d_gantt_preview.html",
            )
            self.status_text.set(f"3D Gantt preview ready: {url}")
        except Exception as exception:
            self._show_error("3D Gantt preview failed", "The 3D Gantt preview could not be generated.", exception)

    def export_3d_gantt_visualisation(self):
        if self.project is None:
            messagebox.showwarning("No programme", "Open an MPP file before creating a visualisation.")
            return

        source_name = self.current_file.stem if self.current_file else "programme"
        filename = filedialog.asksaveasfilename(
            title="Save 3D Gantt visualisation",
            initialdir=str(self.reports_dir()),
            initialfile=f"{source_name}_3d_gantt_visualisation.html",
            defaultextension=".html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
        )

        if not filename:
            return

        try:
            output = export_static_gantt(self.project, filename)
            self.status_text.set(f"Exported {output}")
            open_now = messagebox.askyesno(
                "3D Gantt visualisation exported",
                f"The 3D Gantt visualisation was created successfully.\n\n{output}\n\nOpen it now in your browser?",
            )
            if open_now:
                webbrowser.open(output.resolve().as_uri())
        except Exception as exception:
            self._show_error("3D Gantt export failed", "The 3D Gantt visualisation export failed.", exception)

    # Backwards-compatible method names kept for existing bindings.
    def open_3d_preview(self):
        self.open_3d_network_preview()

    def export_3d_visualisation(self):
        self.export_3d_network_visualisation()

    def show_environment_information(self):
        lines = [
            f"Python executable: {sys.executable}",
            f"Python version: {sys.version}",
            f"Application folder: {SCRIPT_DIR}",
            f"ProjectLibre JAR: {JAR_PATH}",
            f"JAR exists: {JAR_PATH.exists()}",
            f"JVM started: {jpype.isJVMStarted()}",
        ]

        if jpype.isJVMStarted():
            try:
                system_class = jpype.JClass("java.lang.System")
                lines.append("Java version: " + str(system_class.getProperty("java.version")))
                lines.append("Java home: " + str(system_class.getProperty("java.home")))
            except Exception:
                pass

        messagebox.showinfo("Environment information", "\n".join(lines))

    def show_about(self):
        messagebox.showinfo(
            "About MPP Programme Explorer",
            "MPP Programme Explorer\n\n"
            "A read-only programme browser using Python, Tkinter, "
            "JPype and the MPXJ classes bundled with ProjectLibre.\n\n"
            "The application does not modify the source MPP file.",
        )

    def close_application(self):
        self.session.shutdown()
        self.root.destroy()


def main():
    root = tk.Tk()
    ProgrammeExplorer(root)
    root.mainloop()
