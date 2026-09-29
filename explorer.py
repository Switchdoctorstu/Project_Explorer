from __future__ import annotations

import csv
import os
import sys
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import jpype


# ============================================================
# Application configuration
# ============================================================

APP_TITLE = "MPP Programme Explorer"
JAR_NAME = "projectlibre-1.9.8.jar"

SCRIPT_DIR = Path(__file__).resolve().parent
JAR_PATH = SCRIPT_DIR / JAR_NAME


# ============================================================
# General conversion helpers
# ============================================================

def safe_call(obj, method_name, default=""):
    """
    Safely invoke a zero-argument Java method.

    MPXJ versions differ slightly, and some fields may be absent or
    unsupported in a particular MPP version. This prevents one missing
    property from stopping the whole explorer.
    """
    if obj is None:
        return default

    try:
        method = getattr(obj, method_name)
        value = method()

        if value is None:
            return default

        return value

    except Exception:
        return default


def as_text(value):
    """Convert a Java or Python value into displayable text."""
    if value is None:
        return ""

    try:
        return str(value)
    except Exception:
        return ""


def as_bool_text(value):
    """Convert boolean-like values to Yes, No, or blank."""
    if value is None or value == "":
        return ""

    text = str(value).strip().lower()

    if text == "true":
        return "Yes"

    if text == "false":
        return "No"

    return str(value)


def collection_items(collection):
    """
    Convert a Java collection into a Python list.

    Returns an empty list if the collection is unavailable.
    """
    if collection is None:
        return []

    try:
        return list(collection)
    except Exception:
        return []


def flatten_exception(exception):
    """Create a readable error message from a Python or Java exception."""
    lines = [str(exception)]

    try:
        java_exception = getattr(exception, "__javavalue__", None)

        if java_exception:
            lines.append(str(java_exception))
    except Exception:
        pass

    return "\n".join(line for line in lines if line)


# ============================================================
# Scrollable Treeview component
# ============================================================

class ScrollableTree(ttk.Frame):
    def __init__(self, parent, columns, headings=None, tree_column=True):
        super().__init__(parent)

        self.columns = columns

        show_mode = "tree headings" if tree_column else "headings"

        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show=show_mode,
            selectmode="browse"
        )

        self.vertical_scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.tree.yview
        )

        self.horizontal_scrollbar = ttk.Scrollbar(
            self,
            orient="horizontal",
            command=self.tree.xview
        )

        self.tree.configure(
            yscrollcommand=self.vertical_scrollbar.set,
            xscrollcommand=self.horizontal_scrollbar.set
        )

        self.tree.grid(row=0, column=0, sticky="nsew")
        self.vertical_scrollbar.grid(row=0, column=1, sticky="ns")
        self.horizontal_scrollbar.grid(row=1, column=0, sticky="ew")

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        if headings is None:
            headings = {}

        for column in columns:
            title = headings.get(column, column)

            self.tree.heading(
                column,
                text=title,
                command=lambda c=column: self.sort_by_column(c, False)
            )

    def clear(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def sort_by_column(self, column, descending):
        """
        Sort top-level grid rows.

        Hierarchical task rows are intentionally not rearranged because
        sorting would destroy the visible programme structure.
        """
        rows = []

        for item_id in self.tree.get_children(""):
            value = self.tree.set(item_id, column)
            rows.append((value, item_id))

        def sort_key(item):
            value = item[0]

            try:
                return 0, float(value.replace("%", "").replace(",", ""))
            except Exception:
                return 1, value.lower()

        rows.sort(key=sort_key, reverse=descending)

        for index, (_, item_id) in enumerate(rows):
            self.tree.move(item_id, "", index)

        self.tree.heading(
            column,
            command=lambda: self.sort_by_column(column, not descending)
        )


# ============================================================
# Property grid
# ============================================================

class PropertyGrid(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        self.tree_frame = ScrollableTree(
            self,
            columns=("Value",),
            headings={"Value": "Value"},
            tree_column=True
        )
        self.tree_frame.pack(fill="both", expand=True)

        self.tree = self.tree_frame.tree
        self.tree.heading("#0", text="Property")
        self.tree.column("#0", width=250, minwidth=150, stretch=False)
        self.tree.column("Value", width=600, minwidth=200, stretch=True)

    def clear(self):
        self.tree_frame.clear()

    def populate(self, properties):
        self.clear()

        for property_name, value in properties:
            self.tree.insert(
                "",
                "end",
                text=property_name,
                values=(as_text(value),)
            )


# ============================================================
# Main application
# ============================================================

class ProgrammeExplorer:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1600x920")
        self.root.minsize(1100, 700)

        self.project = None
        self.reader_class = None
        self.current_file = None

        self.task_by_tree_id = {}
        self.task_by_unique_id = {}
        self.resource_by_unique_id = {}

        self.status_text = tk.StringVar(value="Starting...")
        self.filter_text = tk.StringVar()
        self.file_text = tk.StringVar(value="No programme loaded")
        self.summary_text = tk.StringVar(value="")

        self._configure_style()
        self._build_menu()
        self._build_interface()

        self.root.protocol("WM_DELETE_WINDOW", self.close_application)
        self.root.after(50, self.start_jvm)

    # --------------------------------------------------------
    # UI construction
    # --------------------------------------------------------

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
        file_menu.add_command(
            label="Open MPP...",
            accelerator="Ctrl+O",
            command=self.open_mpp
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Export task register...",
            command=self.export_tasks_csv
        )
        file_menu.add_command(
            label="Export resource register...",
            command=self.export_resources_csv
        )
        file_menu.add_command(
            label="Export dependency register...",
            command=self.export_dependencies_csv
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Exit",
            command=self.close_application
        )

        view_menu = tk.Menu(menu_bar, tearoff=False)
        view_menu.add_command(
            label="Expand all tasks",
            command=self.expand_all_tasks
        )
        view_menu.add_command(
            label="Collapse all tasks",
            command=self.collapse_all_tasks
        )
        view_menu.add_separator()
        view_menu.add_command(
            label="Show all tasks",
            command=self.clear_filter
        )

        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(
            label="Environment information",
            command=self.show_environment_information
        )
        help_menu.add_command(
            label="About",
            command=self.show_about
        )

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

        ttk.Button(
            toolbar,
            text="Open MPP",
            command=self.open_mpp
        ).pack(side="left", padx=(0, 6))

        ttk.Button(
            toolbar,
            text="Expand All",
            command=self.expand_all_tasks
        ).pack(side="left", padx=3)

        ttk.Button(
            toolbar,
            text="Collapse All",
            command=self.collapse_all_tasks
        ).pack(side="left", padx=3)

        ttk.Button(
            toolbar,
            text="Export Tasks",
            command=self.export_tasks_csv
        ).pack(side="left", padx=3)

        ttk.Separator(
            toolbar,
            orient="vertical"
        ).pack(side="left", fill="y", padx=10)

        ttk.Label(toolbar, text="Find task:").pack(side="left", padx=(0, 5))

        filter_entry = ttk.Entry(
            toolbar,
            textvariable=self.filter_text,
            width=35
        )
        filter_entry.pack(side="left", padx=(0, 5))
        filter_entry.bind("<Return>", lambda event: self.apply_task_filter())

        ttk.Button(
            toolbar,
            text="Find",
            command=self.apply_task_filter
        ).pack(side="left", padx=3)

        ttk.Button(
            toolbar,
            text="Clear",
            command=self.clear_filter
        ).pack(side="left", padx=3)

        ttk.Label(
            toolbar,
            textvariable=self.file_text
        ).pack(side="right", padx=5)

    def _build_summary_strip(self):
        summary_frame = ttk.Frame(self.root, padding=(10, 3))
        summary_frame.pack(fill="x")

        ttk.Label(
            summary_frame,
            textvariable=self.summary_text,
            style="Summary.TLabel"
        ).pack(anchor="w")

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

        columns = (
            "ID",
            "WBS",
            "Start",
            "Finish",
            "Duration",
            "Complete",
            "Milestone",
            "Critical"
        )

        self.programme_tree_frame = ScrollableTree(
            left_frame,
            columns=columns,
            headings={
                "Complete": "% Complete"
            },
            tree_column=True
        )
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
            "Critical": 75
        }

        for column, width in widths.items():
            self.programme_tree.column(
                column,
                width=width,
                minwidth=50,
                stretch=False
            )

        self.programme_tree.tag_configure(
            "summary",
            font=("Segoe UI", 9, "bold")
        )
        self.programme_tree.tag_configure(
            "milestone",
            foreground="#005A9C"
        )
        self.programme_tree.tag_configure(
            "critical",
            foreground="#B00020"
        )
        self.programme_tree.tag_configure(
            "inactive",
            foreground="#777777"
        )

        self.programme_tree.bind(
            "<<TreeviewSelect>>",
            self.on_programme_task_selected
        )
        self.programme_tree.bind(
            "<Double-1>",
            self.on_programme_task_double_click
        )

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
        self.task_detail_notebook.add(
            relationship_tab,
            text="Relationships"
        )
        self.task_detail_notebook.add(notes_tab, text="Notes")

        self.task_general_grid = PropertyGrid(general_tab)
        self.task_general_grid.pack(fill="both", expand=True)

        self.task_schedule_grid = PropertyGrid(schedule_tab)
        self.task_schedule_grid.pack(fill="both", expand=True)

        self.task_cost_grid = PropertyGrid(cost_tab)
        self.task_cost_grid.pack(fill="both", expand=True)

        relationship_paned = ttk.Panedwindow(
            relationship_tab,
            orient="vertical"
        )
        relationship_paned.pack(fill="both", expand=True)

        predecessor_frame = ttk.LabelFrame(
            relationship_paned,
            text="Predecessors",
            padding=4
        )
        successor_frame = ttk.LabelFrame(
            relationship_paned,
            text="Successors",
            padding=4
        )
        assignment_frame = ttk.LabelFrame(
            relationship_paned,
            text="Resource Assignments",
            padding=4
        )

        relationship_paned.add(predecessor_frame, weight=1)
        relationship_paned.add(successor_frame, weight=1)
        relationship_paned.add(assignment_frame, weight=1)

        relation_columns = ("ID", "Task", "Type", "Lag")

        self.task_predecessor_tree = ScrollableTree(
            predecessor_frame,
            relation_columns,
            tree_column=False
        )
        self.task_predecessor_tree.pack(fill="both", expand=True)

        self.task_successor_tree = ScrollableTree(
            successor_frame,
            relation_columns,
            tree_column=False
        )
        self.task_successor_tree.pack(fill="both", expand=True)

        assignment_columns = (
            "Resource",
            "Units",
            "Work",
            "Actual Work",
            "Cost"
        )

        self.task_assignment_tree = ScrollableTree(
            assignment_frame,
            assignment_columns,
            tree_column=False
        )
        self.task_assignment_tree.pack(fill="both", expand=True)

        self.task_notes_text = tk.Text(
            notes_tab,
            wrap="word",
            font=("Segoe UI", 10)
        )
        notes_scrollbar = ttk.Scrollbar(
            notes_tab,
            orient="vertical",
            command=self.task_notes_text.yview
        )
        self.task_notes_text.configure(
            yscrollcommand=notes_scrollbar.set
        )

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
            "Predecessors"
        )

        self.task_register = ScrollableTree(
            tab,
            columns,
            tree_column=False
        )
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

        self.task_register.tree.bind(
            "<Double-1>",
            self.open_task_from_register
        )

    def _build_milestones_tab(self):
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="Milestones")

        columns = (
            "ID",
            "WBS",
            "Milestone",
            "Date",
            "% Complete",
            "Critical",
            "Predecessors",
            "Successors"
        )

        self.milestone_tree = ScrollableTree(
            tab,
            columns,
            tree_column=False
        )
        self.milestone_tree.pack(fill="both", expand=True)

        self.milestone_tree.tree.column("Milestone", width=420)
        self.milestone_tree.tree.column("Date", width=170)
        self.milestone_tree.tree.column("Predecessors", width=220)
        self.milestone_tree.tree.column("Successors", width=220)

    def _build_dependencies_tab(self):
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="Dependencies")

        columns = (
            "Successor ID",
            "Successor",
            "Predecessor ID",
            "Predecessor",
            "Type",
            "Lag"
        )

        self.dependency_tree = ScrollableTree(
            tab,
            columns,
            tree_column=False
        )
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
            "Calendar"
        )

        self.resource_tree = ScrollableTree(
            left_frame,
            columns,
            tree_column=False
        )
        self.resource_tree.pack(fill="both", expand=True)

        self.resource_tree.tree.column("Name", width=240)
        self.resource_tree.tree.column("Email", width=260)
        self.resource_tree.tree.bind(
            "<<TreeviewSelect>>",
            self.on_resource_selected
        )

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
            "Remaining Cost"
        )

        self.assignment_tree = ScrollableTree(
            tab,
            columns,
            tree_column=False
        )
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

        columns = (
            "Unique ID",
            "Name",
            "Type",
            "Parent",
            "Working Days"
        )

        self.calendar_tree = ScrollableTree(
            left_frame,
            columns,
            tree_column=False
        )
        self.calendar_tree.pack(fill="both", expand=True)
        self.calendar_tree.tree.column("Name", width=250)
        self.calendar_tree.tree.column("Working Days", width=260)

        self.calendar_tree.tree.bind(
            "<<TreeviewSelect>>",
            self.on_calendar_selected
        )

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

        self.import_messages_text = tk.Text(
            tab,
            wrap="word",
            font=("Consolas", 10)
        )

        vertical_scrollbar = ttk.Scrollbar(
            tab,
            orient="vertical",
            command=self.import_messages_text.yview
        )

        self.import_messages_text.configure(
            yscrollcommand=vertical_scrollbar.set
        )

        self.import_messages_text.pack(
            side="left",
            fill="both",
            expand=True
        )
        vertical_scrollbar.pack(side="right", fill="y")

    def _build_status_bar(self):
        ttk.Label(
            self.root,
            textvariable=self.status_text,
            style="Status.TLabel",
            anchor="w"
        ).pack(fill="x", side="bottom")

    # --------------------------------------------------------
    # Java and MPXJ initialisation
    # --------------------------------------------------------

    def start_jvm(self):
        try:
            if not JAR_PATH.exists():
                raise FileNotFoundError(
                    f"Cannot find {JAR_NAME}.\n\n"
                    f"Expected location:\n{JAR_PATH}"
                )

            if not jpype.isJVMStarted():
                jpype.startJVM(
                    classpath=[str(JAR_PATH)]
                )

            self.reader_class = jpype.JClass(
                "net.sf.mpxj.reader.UniversalProjectReader"
            )

            system_class = jpype.JClass("java.lang.System")
            java_version = system_class.getProperty("java.version")

            self.status_text.set(
                f"Ready. MPXJ loaded using Java {java_version}"
            )

        except Exception as exception:
            self.status_text.set("JVM initialisation failed")

            messagebox.showerror(
                "Java / MPXJ error",
                "The programme explorer could not initialise MPXJ.\n\n"
                f"{flatten_exception(exception)}\n\n"
                "Confirm that JDK 21 is active and that "
                f"{JAR_NAME} is beside this Python script."
            )

    # --------------------------------------------------------
    # MPP loading
    # --------------------------------------------------------

    def open_mpp(self):
        if self.reader_class is None:
            messagebox.showwarning(
                "MPXJ not available",
                "The MPXJ reader has not been initialised."
            )
            return

        filename = filedialog.askopenfilename(
            title="Open Microsoft Project programme",
            filetypes=[
                ("Microsoft Project files", "*.mpp"),
                ("Microsoft Project templates", "*.mpt"),
                ("Microsoft Project XML", "*.xml"),
                ("All files", "*.*")
            ]
        )

        if not filename:
            return

        self.status_text.set(f"Reading {Path(filename).name}...")
        self.root.update_idletasks()

        try:
            reader = self.reader_class()
            project = reader.read(str(filename))

            if project is None:
                raise RuntimeError(
                    "MPXJ did not return a project from the selected file."
                )

            self.project = project
            self.current_file = Path(filename)

            self.file_text.set(self.current_file.name)
            self.root.title(
                f"{APP_TITLE} - {self.current_file.name}"
            )

            self.refresh_all_views()

            self.status_text.set(
                f"Loaded {self.current_file}"
            )

        except Exception as exception:
            self.project = None
            self.status_text.set("Programme load failed")

            messagebox.showerror(
                "Could not open programme",
                f"The selected file could not be read.\n\n"
                f"{flatten_exception(exception)}"
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

        tree_components = [
            self.programme_tree_frame,
            self.task_register,
            self.milestone_tree,
            self.dependency_tree,
            self.resource_tree,
            self.assignment_tree,
            self.calendar_tree
        ]

        for component in tree_components:
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
        for task in self.get_all_tasks():
            unique_id = as_text(safe_call(task, "getUniqueID"))

            if unique_id:
                self.task_by_unique_id[unique_id] = task

        for resource in self.get_all_resources():
            unique_id = as_text(safe_call(resource, "getUniqueID"))

            if unique_id:
                self.resource_by_unique_id[unique_id] = resource

    # --------------------------------------------------------
    # Entity collection helpers
    # --------------------------------------------------------

    def get_all_tasks(self):
        if self.project is None:
            return []

        tasks = safe_call(self.project, "getTasks", None)

        if tasks is None:
            tasks = safe_call(self.project, "getAllTasks", None)

        return collection_items(tasks)

    def get_top_level_tasks(self):
        if self.project is None:
            return []

        tasks = safe_call(self.project, "getChildTasks", None)

        if tasks is not None:
            return collection_items(tasks)

        all_tasks = self.get_all_tasks()
        return [
            task for task in all_tasks
            if safe_call(task, "getParentTask", None) is None
        ]

    def get_all_resources(self):
        if self.project is None:
            return []

        resources = safe_call(self.project, "getResources", None)

        if resources is None:
            resources = safe_call(self.project, "getAllResources", None)

        return collection_items(resources)

    def get_all_calendars(self):
        if self.project is None:
            return []

        calendars = safe_call(self.project, "getCalendars", None)

        return collection_items(calendars)

    def task_children(self, task):
        return collection_items(
            safe_call(task, "getChildTasks", None)
        )

    def task_predecessors(self, task):
        return collection_items(
            safe_call(task, "getPredecessors", None)
        )

    def task_successors(self, task):
        return collection_items(
            safe_call(task, "getSuccessors", None)
        )

    def task_assignments(self, task):
        return collection_items(
            safe_call(task, "getResourceAssignments", None)
        )

    # --------------------------------------------------------
    # Task tree
    # --------------------------------------------------------

    def populate_programme_structure(self):
        top_level_tasks = self.get_top_level_tasks()

        if not top_level_tasks:
            top_level_tasks = self.get_all_tasks()

        visited = set()

        for task in top_level_tasks:
            self.insert_task_node("", task, visited)

    def insert_task_node(self, parent_tree_id, task, visited):
        if task is None:
            return

        unique_id = as_text(safe_call(task, "getUniqueID"))

        if unique_id and unique_id in visited:
            return

        if unique_id:
            visited.add(unique_id)

        name = as_text(safe_call(task, "getName", "(Unnamed task)"))
        is_summary = safe_call(task, "getSummary", False)
        is_milestone = safe_call(task, "getMilestone", False)
        is_critical = safe_call(task, "getCritical", False)
        is_active = safe_call(task, "getActive", True)

        tags = []

        if str(is_summary).lower() == "true":
            tags.append("summary")

        if str(is_milestone).lower() == "true":
            tags.append("milestone")

        if str(is_critical).lower() == "true":
            tags.append("critical")

        if str(is_active).lower() == "false":
            tags.append("inactive")

        tree_id = self.programme_tree.insert(
            parent_tree_id,
            "end",
            text=name,
            values=(
                as_text(safe_call(task, "getID")),
                as_text(safe_call(task, "getWBS")),
                as_text(safe_call(task, "getStart")),
                as_text(safe_call(task, "getFinish")),
                as_text(safe_call(task, "getDuration")),
                as_text(safe_call(task, "getPercentageComplete")),
                as_bool_text(is_milestone),
                as_bool_text(is_critical)
            ),
            tags=tuple(tags),
            open=False
        )

        self.task_by_tree_id[tree_id] = task

        child_tasks = self.task_children(task)

        for child_task in child_tasks:
            self.insert_task_node(tree_id, child_task, visited)

    def on_programme_task_selected(self, event=None):
        selection = self.programme_tree.selection()

        if not selection:
            return

        tree_id = selection[0]
        task = self.task_by_tree_id.get(tree_id)

        if task is not None:
            self.display_task_details(task)

    def on_programme_task_double_click(self, event=None):
        item_id = self.programme_tree.identify_row(event.y)

        if not item_id:
            return

        current_state = self.programme_tree.item(item_id, "open")
        self.programme_tree.item(item_id, open=not current_state)

    def display_task_details(self, task):
        self.task_general_grid.populate(
            self.get_task_general_properties(task)
        )

        self.task_schedule_grid.populate(
            self.get_task_schedule_properties(task)
        )

        self.task_cost_grid.populate(
            self.get_task_cost_properties(task)
        )

        self.populate_selected_task_relationships(task)

        notes = safe_call(task, "getNotes", "")

        self.task_notes_text.delete("1.0", "end")
        self.task_notes_text.insert("1.0", as_text(notes))

    def get_task_general_properties(self, task):
        parent_task = safe_call(task, "getParentTask", None)
        calendar = safe_call(task, "getCalendar", None)

        return [
            ("Name", safe_call(task, "getName")),
            ("ID", safe_call(task, "getID")),
            ("Unique ID", safe_call(task, "getUniqueID")),
            ("GUID", safe_call(task, "getGUID")),
            ("WBS", safe_call(task, "getWBS")),
            ("Outline Number", safe_call(task, "getOutlineNumber")),
            ("Outline Level", safe_call(task, "getOutlineLevel")),
            (
                "Parent Task",
                safe_call(parent_task, "getName") if parent_task else ""
            ),
            ("Summary Task", as_bool_text(safe_call(task, "getSummary"))),
            ("Milestone", as_bool_text(safe_call(task, "getMilestone"))),
            ("Critical", as_bool_text(safe_call(task, "getCritical"))),
            ("Active", as_bool_text(safe_call(task, "getActive"))),
            ("External Task", as_bool_text(safe_call(task, "getExternalTask"))),
            ("Subproject", as_bool_text(safe_call(task, "getSubproject"))),
            ("Task Type", safe_call(task, "getType")),
            ("Task Mode", safe_call(task, "getTaskMode")),
            ("Priority", safe_call(task, "getPriority")),
            ("Constraint Type", safe_call(task, "getConstraintType")),
            ("Constraint Date", safe_call(task, "getConstraintDate")),
            (
                "Calendar",
                safe_call(calendar, "getName") if calendar else ""
            ),
            ("Resource Names", safe_call(task, "getResourceNames")),
            ("Contact", safe_call(task, "getContact")),
            ("Hyperlink", safe_call(task, "getHyperlink")),
            ("Hyperlink Address", safe_call(task, "getHyperlinkAddress")),
            (
                "Hyperlink Sub-address",
                safe_call(task, "getHyperlinkSubAddress")
            )
        ]

    def get_task_schedule_properties(self, task):
        return [
            ("Start", safe_call(task, "getStart")),
            ("Finish", safe_call(task, "getFinish")),
            ("Duration", safe_call(task, "getDuration")),
            ("Actual Start", safe_call(task, "getActualStart")),
            ("Actual Finish", safe_call(task, "getActualFinish")),
            ("Actual Duration", safe_call(task, "getActualDuration")),
            ("Remaining Duration", safe_call(task, "getRemainingDuration")),
            ("Baseline Start", safe_call(task, "getBaselineStart")),
            ("Baseline Finish", safe_call(task, "getBaselineFinish")),
            ("Baseline Duration", safe_call(task, "getBaselineDuration")),
            ("Early Start", safe_call(task, "getEarlyStart")),
            ("Early Finish", safe_call(task, "getEarlyFinish")),
            ("Late Start", safe_call(task, "getLateStart")),
            ("Late Finish", safe_call(task, "getLateFinish")),
            ("Total Slack", safe_call(task, "getTotalSlack")),
            ("Free Slack", safe_call(task, "getFreeSlack")),
            ("% Complete", safe_call(task, "getPercentageComplete")),
            ("% Work Complete", safe_call(task, "getPercentageWorkComplete")),
            ("Deadline", safe_call(task, "getDeadline")),
            ("Stop", safe_call(task, "getStop")),
            ("Resume", safe_call(task, "getResume")),
            ("Leveling Delay", safe_call(task, "getLevelingDelay")),
            (
                "Ignore Resource Calendar",
                as_bool_text(safe_call(task, "getIgnoreResourceCalendar"))
            ),
            (
                "Estimated",
                as_bool_text(safe_call(task, "getEstimated"))
            )
        ]

    def get_task_cost_properties(self, task):
        return [
            ("Cost", safe_call(task, "getCost")),
            ("Actual Cost", safe_call(task, "getActualCost")),
            ("Remaining Cost", safe_call(task, "getRemainingCost")),
            ("Fixed Cost", safe_call(task, "getFixedCost")),
            ("Fixed Cost Accrual", safe_call(task, "getFixedCostAccrual")),
            ("Baseline Cost", safe_call(task, "getBaselineCost")),
            ("Cost Variance", safe_call(task, "getCostVariance")),
            ("Work", safe_call(task, "getWork")),
            ("Actual Work", safe_call(task, "getActualWork")),
            ("Remaining Work", safe_call(task, "getRemainingWork")),
            ("Baseline Work", safe_call(task, "getBaselineWork")),
            ("Work Variance", safe_call(task, "getWorkVariance")),
            ("Budget Cost", safe_call(task, "getBudgetCost")),
            ("Budget Work", safe_call(task, "getBudgetWork")),
            ("BCWS", safe_call(task, "getBCWS")),
            ("BCWP", safe_call(task, "getBCWP")),
            ("ACWP", safe_call(task, "getACWP")),
            ("CPI", safe_call(task, "getCPI")),
            ("SPI", safe_call(task, "getSPI")),
            ("CV", safe_call(task, "getCV")),
            ("SV", safe_call(task, "getSV")),
            ("EAC", safe_call(task, "getEAC")),
            ("VAC", safe_call(task, "getVAC")),
            ("TCPI", safe_call(task, "getTCPI"))
        ]

    # --------------------------------------------------------
    # Task register and filtering
    # --------------------------------------------------------

    def populate_task_register(self, task_filter=""):
        self.task_register.clear()

        filter_value = task_filter.strip().lower()

        for task in self.get_all_tasks():
            task_name = as_text(safe_call(task, "getName"))

            searchable = " ".join([
                task_name,
                as_text(safe_call(task, "getWBS")),
                as_text(safe_call(task, "getID")),
                as_text(safe_call(task, "getUniqueID"))
            ]).lower()

            if filter_value and filter_value not in searchable:
                continue

            predecessors = self.describe_relations(
                self.task_predecessors(task)
            )

            self.task_register.tree.insert(
                "",
                "end",
                values=(
                    as_text(safe_call(task, "getID")),
                    as_text(safe_call(task, "getUniqueID")),
                    as_text(safe_call(task, "getWBS")),
                    as_text(safe_call(task, "getOutlineLevel")),
                    task_name,
                    as_text(safe_call(task, "getStart")),
                    as_text(safe_call(task, "getFinish")),
                    as_text(safe_call(task, "getDuration")),
                    as_text(safe_call(task, "getPercentageComplete")),
                    as_bool_text(safe_call(task, "getSummary")),
                    as_bool_text(safe_call(task, "getMilestone")),
                    as_bool_text(safe_call(task, "getCritical")),
                    as_bool_text(safe_call(task, "getActive")),
                    as_text(safe_call(task, "getResourceNames")),
                    predecessors
                )
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
            values = [
                safe_call(task, "getName"),
                safe_call(task, "getWBS"),
                safe_call(task, "getID"),
                safe_call(task, "getUniqueID")
            ]

            searchable = " ".join(as_text(value) for value in values).lower()

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

        unique_id = as_text(
            self.task_register.tree.set(item_id, "Unique ID")
        )

        self.select_task_by_unique_id(unique_id)

    def select_task_by_unique_id(self, unique_id):
        for tree_id, task in self.task_by_tree_id.items():
            task_unique_id = as_text(safe_call(task, "getUniqueID"))

            if task_unique_id == unique_id:
                self.open_parent_nodes(tree_id)
                self.programme_tree.selection_set(tree_id)
                self.programme_tree.focus(tree_id)
                self.programme_tree.see(tree_id)
                self.display_task_details(task)
                self.main_notebook.select(0)
                return

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    def relation_task(self, relation, direction):
        """
        MPXJ relationship APIs have varied by version.

        Try the common methods and return whichever task is available.
        """
        method_names = []

        if direction == "predecessor":
            method_names = [
                "getTargetTask",
                "getPredecessorTask",
                "getSourceTask"
            ]
        else:
            method_names = [
                "getTargetTask",
                "getSuccessorTask",
                "getSourceTask"
            ]

        for method_name in method_names:
            value = safe_call(relation, method_name, None)

            if value is not None:
                return value

        return None

    def relation_lag(self, relation):
        lag = safe_call(relation, "getLag", None)

        if lag is None:
            lag = safe_call(relation, "getDuration", "")

        return lag

    def populate_selected_task_relationships(self, task):
        self.task_predecessor_tree.clear()
        self.task_successor_tree.clear()
        self.task_assignment_tree.clear()

        for relation in self.task_predecessors(task):
            related_task = self.relation_task(relation, "predecessor")

            self.task_predecessor_tree.tree.insert(
                "",
                "end",
                values=(
                    as_text(safe_call(related_task, "getID")),
                    as_text(safe_call(related_task, "getName")),
                    as_text(safe_call(relation, "getType")),
                    as_text(self.relation_lag(relation))
                )
            )

        for relation in self.task_successors(task):
            related_task = self.relation_task(relation, "successor")

            self.task_successor_tree.tree.insert(
                "",
                "end",
                values=(
                    as_text(safe_call(related_task, "getID")),
                    as_text(safe_call(related_task, "getName")),
                    as_text(safe_call(relation, "getType")),
                    as_text(self.relation_lag(relation))
                )
            )

        for assignment in self.task_assignments(task):
            resource = safe_call(assignment, "getResource", None)

            self.task_assignment_tree.tree.insert(
                "",
                "end",
                values=(
                    as_text(safe_call(resource, "getName")),
                    as_text(safe_call(assignment, "getUnits")),
                    as_text(safe_call(assignment, "getWork")),
                    as_text(safe_call(assignment, "getActualWork")),
                    as_text(safe_call(assignment, "getCost"))
                )
            )

    def describe_relations(self, relations):
        descriptions = []

        for relation in relations:
            related_task = self.relation_task(relation, "predecessor")
            task_id = as_text(safe_call(related_task, "getID"))
            relation_type = as_text(safe_call(relation, "getType"))

            if task_id:
                description = task_id

                if relation_type:
                    description += f" {relation_type}"

                descriptions.append(description)

        return ", ".join(descriptions)

    def populate_dependencies(self):
        for successor_task in self.get_all_tasks():
            successor_id = as_text(safe_call(successor_task, "getID"))
            successor_name = as_text(safe_call(successor_task, "getName"))

            for relation in self.task_predecessors(successor_task):
                predecessor_task = self.relation_task(
                    relation,
                    "predecessor"
                )

                self.dependency_tree.tree.insert(
                    "",
                    "end",
                    values=(
                        successor_id,
                        successor_name,
                        as_text(safe_call(predecessor_task, "getID")),
                        as_text(safe_call(predecessor_task, "getName")),
                        as_text(safe_call(relation, "getType")),
                        as_text(self.relation_lag(relation))
                    )
                )

    # --------------------------------------------------------
    # Milestones
    # --------------------------------------------------------

    def populate_milestones(self):
        for task in self.get_all_tasks():
            is_milestone = as_text(
                safe_call(task, "getMilestone")
            ).lower()

            if is_milestone != "true":
                continue

            self.milestone_tree.tree.insert(
                "",
                "end",
                values=(
                    as_text(safe_call(task, "getID")),
                    as_text(safe_call(task, "getWBS")),
                    as_text(safe_call(task, "getName")),
                    as_text(safe_call(task, "getFinish")),
                    as_text(safe_call(task, "getPercentageComplete")),
                    as_bool_text(safe_call(task, "getCritical")),
                    self.describe_relations(
                        self.task_predecessors(task)
                    ),
                    self.describe_relations(
                        self.task_successors(task)
                    )
                )
            )

    # --------------------------------------------------------
    # Resources
    # --------------------------------------------------------

    def populate_resources(self):
        for resource in self.get_all_resources():
            name = as_text(safe_call(resource, "getName"))

            if not name and not as_text(safe_call(resource, "getID")):
                continue

            calendar = safe_call(resource, "getCalendar", None)
            unique_id = as_text(safe_call(resource, "getUniqueID"))

            item_id = self.resource_tree.tree.insert(
                "",
                "end",
                values=(
                    as_text(safe_call(resource, "getID")),
                    unique_id,
                    name,
                    as_text(safe_call(resource, "getInitials")),
                    as_text(safe_call(resource, "getType")),
                    as_text(safe_call(resource, "getEmailAddress")),
                    as_text(safe_call(resource, "getGroup")),
                    as_text(safe_call(resource, "getMaxUnits")),
                    as_text(safe_call(resource, "getStandardRate")),
                    as_text(safe_call(resource, "getOvertimeRate")),
                    as_text(safe_call(resource, "getCostPerUse")),
                    as_text(safe_call(calendar, "getName"))
                )
            )

            self.resource_tree.tree.set(
                item_id,
                "Unique ID",
                unique_id
            )

    def on_resource_selected(self, event=None):
        selection = self.resource_tree.tree.selection()

        if not selection:
            return

        item_id = selection[0]
        unique_id = self.resource_tree.tree.set(item_id, "Unique ID")
        resource = self.resource_by_unique_id.get(unique_id)

        if resource is None:
            return

        calendar = safe_call(resource, "getCalendar", None)

        properties = [
            ("Name", safe_call(resource, "getName")),
            ("ID", safe_call(resource, "getID")),
            ("Unique ID", safe_call(resource, "getUniqueID")),
            ("GUID", safe_call(resource, "getGUID")),
            ("Initials", safe_call(resource, "getInitials")),
            ("Type", safe_call(resource, "getType")),
            ("Email Address", safe_call(resource, "getEmailAddress")),
            ("Group", safe_call(resource, "getGroup")),
            ("Code", safe_call(resource, "getCode")),
            ("Account", safe_call(resource, "getAccount")),
            ("Active", as_bool_text(safe_call(resource, "getActive"))),
            ("Generic", as_bool_text(safe_call(resource, "getGeneric"))),
            (
                "Resource Calendar",
                safe_call(calendar, "getName") if calendar else ""
            ),
            ("Max Units", safe_call(resource, "getMaxUnits")),
            ("Standard Rate", safe_call(resource, "getStandardRate")),
            ("Overtime Rate", safe_call(resource, "getOvertimeRate")),
            ("Cost Per Use", safe_call(resource, "getCostPerUse")),
            ("Cost", safe_call(resource, "getCost")),
            ("Actual Cost", safe_call(resource, "getActualCost")),
            ("Remaining Cost", safe_call(resource, "getRemainingCost")),
            ("Work", safe_call(resource, "getWork")),
            ("Actual Work", safe_call(resource, "getActualWork")),
            ("Remaining Work", safe_call(resource, "getRemainingWork")),
            ("Baseline Work", safe_call(resource, "getBaselineWork")),
            ("Start", safe_call(resource, "getStart")),
            ("Finish", safe_call(resource, "getFinish"))
        ]

        self.resource_detail_grid.populate(properties)

    # --------------------------------------------------------
    # Assignments
    # --------------------------------------------------------

    def populate_assignments(self):
        for task in self.get_all_tasks():
            task_id = as_text(safe_call(task, "getID"))
            task_name = as_text(safe_call(task, "getName"))

            for assignment in self.task_assignments(task):
                resource = safe_call(assignment, "getResource", None)

                self.assignment_tree.tree.insert(
                    "",
                    "end",
                    values=(
                        task_id,
                        task_name,
                        as_text(safe_call(resource, "getName")),
                        as_text(safe_call(assignment, "getStart")),
                        as_text(safe_call(assignment, "getFinish")),
                        as_text(safe_call(assignment, "getUnits")),
                        as_text(safe_call(assignment, "getWork")),
                        as_text(safe_call(assignment, "getActualWork")),
                        as_text(safe_call(assignment, "getRemainingWork")),
                        as_text(safe_call(assignment, "getCost")),
                        as_text(safe_call(assignment, "getActualCost")),
                        as_text(safe_call(assignment, "getRemainingCost"))
                    )
                )

    # --------------------------------------------------------
    # Calendars
    # --------------------------------------------------------

    def populate_calendars(self):
        for calendar in self.get_all_calendars():
            parent = safe_call(calendar, "getParent", None)
            unique_id = as_text(safe_call(calendar, "getUniqueID"))

            working_days = self.describe_calendar_days(calendar)

            item_id = self.calendar_tree.tree.insert(
                "",
                "end",
                values=(
                    unique_id,
                    as_text(safe_call(calendar, "getName")),
                    as_text(safe_call(calendar, "getType")),
                    as_text(safe_call(parent, "getName")),
                    working_days
                )
            )

            self.calendar_tree.tree.set(
                item_id,
                "Unique ID",
                unique_id
            )

    def describe_calendar_days(self, calendar):
        working_days = []

        for day_name in (
            "SUNDAY",
            "MONDAY",
            "TUESDAY",
            "WEDNESDAY",
            "THURSDAY",
            "FRIDAY",
            "SATURDAY"
        ):
            try:
                day_class = jpype.JClass("net.sf.mpxj.Day")
                day_value = getattr(day_class, day_name)
                day_type = calendar.getCalendarDayType(day_value)

                if "WORKING" in as_text(day_type).upper():
                    working_days.append(day_name.title())

            except Exception:
                continue

        return ", ".join(working_days)

    def on_calendar_selected(self, event=None):
        selection = self.calendar_tree.tree.selection()

        if not selection:
            return

        item_id = selection[0]
        selected_unique_id = self.calendar_tree.tree.set(
            item_id,
            "Unique ID"
        )

        selected_calendar = None

        for calendar in self.get_all_calendars():
            unique_id = as_text(safe_call(calendar, "getUniqueID"))

            if unique_id == selected_unique_id:
                selected_calendar = calendar
                break

        if selected_calendar is None:
            return

        parent = safe_call(selected_calendar, "getParent", None)

        properties = [
            ("Name", safe_call(selected_calendar, "getName")),
            ("Unique ID", safe_call(selected_calendar, "getUniqueID")),
            ("Type", safe_call(selected_calendar, "getType")),
            (
                "Parent Calendar",
                safe_call(parent, "getName") if parent else ""
            ),
            (
                "Working Days",
                self.describe_calendar_days(selected_calendar)
            ),
            (
                "Personal Calendar",
                as_bool_text(
                    safe_call(selected_calendar, "getPersonal")
                )
            )
        ]

        self.calendar_detail_grid.populate(properties)

    # --------------------------------------------------------
    # Project properties
    # --------------------------------------------------------

    def populate_project_properties(self):
        properties_object = safe_call(
            self.project,
            "getProjectProperties",
            None
        )

        if properties_object is None:
            properties_object = safe_call(
                self.project,
                "getProperties",
                None
            )

        if properties_object is None:
            return

        properties = [
            ("Project Title", safe_call(properties_object, "getProjectTitle")),
            ("Title", safe_call(properties_object, "getTitle")),
            ("Subject", safe_call(properties_object, "getSubject")),
            ("Author", safe_call(properties_object, "getAuthor")),
            ("Manager", safe_call(properties_object, "getManager")),
            ("Company", safe_call(properties_object, "getCompany")),
            ("Category", safe_call(properties_object, "getCategory")),
            ("Keywords", safe_call(properties_object, "getKeywords")),
            ("Comments", safe_call(properties_object, "getComments")),
            (
                "Creation Date",
                safe_call(properties_object, "getCreationDate")
            ),
            (
                "Last Saved",
                safe_call(properties_object, "getLastSaved")
            ),
            (
                "Last Author",
                safe_call(properties_object, "getLastAuthor")
            ),
            (
                "Application Version",
                safe_call(properties_object, "getApplicationVersion")
            ),
            (
                "File Application",
                safe_call(properties_object, "getFileApplication")
            ),
            (
                "File Type",
                safe_call(properties_object, "getFileType")
            ),
            (
                "Schedule From",
                safe_call(properties_object, "getScheduleFrom")
            ),
            (
                "Project Start Date",
                safe_call(properties_object, "getStartDate")
            ),
            (
                "Project Finish Date",
                safe_call(properties_object, "getFinishDate")
            ),
            (
                "Status Date",
                safe_call(properties_object, "getStatusDate")
            ),
            (
                "Current Date",
                safe_call(properties_object, "getCurrentDate")
            ),
            (
                "Default Calendar",
                safe_call(
                    safe_call(properties_object, "getDefaultCalendar", None),
                    "getName"
                )
            ),
            (
                "Minutes Per Day",
                safe_call(properties_object, "getMinutesPerDay")
            ),
            (
                "Minutes Per Week",
                safe_call(properties_object, "getMinutesPerWeek")
            ),
            (
                "Days Per Month",
                safe_call(properties_object, "getDaysPerMonth")
            ),
            (
                "Currency Symbol",
                safe_call(properties_object, "getCurrencySymbol")
            ),
            (
                "Currency Digits",
                safe_call(properties_object, "getCurrencyDigits")
            ),
            (
                "Default Task Type",
                safe_call(properties_object, "getDefaultTaskType")
            ),
            (
                "Default Fixed Cost Accrual",
                safe_call(
                    properties_object,
                    "getDefaultFixedCostAccrual"
                )
            ),
            (
                "New Tasks Estimated",
                as_bool_text(
                    safe_call(properties_object, "getNewTasksEstimated")
                )
            ),
            (
                "Auto Add New Resources and Tasks",
                as_bool_text(
                    safe_call(
                        properties_object,
                        "getAutoAddNewResourcesAndTasks"
                    )
                )
            )
        ]

        self.project_property_grid.populate(properties)

    # --------------------------------------------------------
    # Import warnings and ignored errors
    # --------------------------------------------------------

    def populate_import_messages(self):
        ignored_errors = safe_call(
            self.project,
            "getIgnoredErrors",
            None
        )

        errors = collection_items(ignored_errors)

        if not errors:
            self.import_messages_text.insert(
                "end",
                "No ignored import errors were reported by MPXJ."
            )
            return

        for index, error in enumerate(errors, start=1):
            self.import_messages_text.insert(
                "end",
                f"{index}. {as_text(error)}\n\n"
            )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    def populate_summary(self):
        tasks = self.get_all_tasks()
        resources = self.get_all_resources()

        milestones = sum(
            1 for task in tasks
            if as_text(safe_call(task, "getMilestone")).lower() == "true"
        )

        critical_tasks = sum(
            1 for task in tasks
            if as_text(safe_call(task, "getCritical")).lower() == "true"
        )

        summary_tasks = sum(
            1 for task in tasks
            if as_text(safe_call(task, "getSummary")).lower() == "true"
        )

        assignment_count = sum(
            len(self.task_assignments(task))
            for task in tasks
        )

        dependency_count = sum(
            len(self.task_predecessors(task))
            for task in tasks
        )

        dates = []

        for task in tasks:
            start = safe_call(task, "getStart", None)
            finish = safe_call(task, "getFinish", None)

            if start is not None:
                dates.append(("start", as_text(start)))

            if finish is not None:
                dates.append(("finish", as_text(finish)))

        self.summary_text.set(
            f"Tasks: {len(tasks):,}    "
            f"Summary tasks: {summary_tasks:,}    "
            f"Milestones: {milestones:,}    "
            f"Critical tasks: {critical_tasks:,}    "
            f"Dependencies: {dependency_count:,}    "
            f"Resources: {len(resources):,}    "
            f"Assignments: {assignment_count:,}"
        )

    # --------------------------------------------------------
    # Expand and collapse
    # --------------------------------------------------------

    def expand_all_tasks(self):
        self.set_tree_open_state("", True)

    def collapse_all_tasks(self):
        self.set_tree_open_state("", False)

    def set_tree_open_state(self, parent_id, open_state):
        for item_id in self.programme_tree.get_children(parent_id):
            self.programme_tree.item(item_id, open=open_state)
            self.set_tree_open_state(item_id, open_state)

    # --------------------------------------------------------
    # CSV export
    # --------------------------------------------------------

    def export_tree_to_csv(self, tree_component, default_filename):
        if self.project is None:
            messagebox.showwarning(
                "No programme",
                "Open an MPP file before exporting."
            )
            return

        filename = filedialog.asksaveasfilename(
            title="Export register",
            initialfile=default_filename,
            defaultextension=".csv",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*")
            ]
        )

        if not filename:
            return

        tree = tree_component.tree
        columns = list(tree["columns"])

        try:
            with open(
                filename,
                "w",
                newline="",
                encoding="utf-8-sig"
            ) as output_file:
                writer = csv.writer(output_file)
                writer.writerow(columns)

                for item_id in tree.get_children(""):
                    writer.writerow([
                        tree.set(item_id, column)
                        for column in columns
                    ])

            self.status_text.set(f"Exported {filename}")

            messagebox.showinfo(
                "Export complete",
                f"The register was exported successfully.\n\n{filename}"
            )

        except Exception as exception:
            messagebox.showerror(
                "Export failed",
                str(exception)
            )

    def export_tasks_csv(self):
        source_name = (
            self.current_file.stem
            if self.current_file
            else "programme"
        )

        self.export_tree_to_csv(
            self.task_register,
            f"{source_name}_tasks.csv"
        )

    def export_resources_csv(self):
        source_name = (
            self.current_file.stem
            if self.current_file
            else "programme"
        )

        self.export_tree_to_csv(
            self.resource_tree,
            f"{source_name}_resources.csv"
        )

    def export_dependencies_csv(self):
        source_name = (
            self.current_file.stem
            if self.current_file
            else "programme"
        )

        self.export_tree_to_csv(
            self.dependency_tree,
            f"{source_name}_dependencies.csv"
        )

    # --------------------------------------------------------
    # Help and shutdown
    # --------------------------------------------------------

    def show_environment_information(self):
        lines = [
            f"Python executable: {sys.executable}",
            f"Python version: {sys.version}",
            f"Application folder: {SCRIPT_DIR}",
            f"ProjectLibre JAR: {JAR_PATH}",
            f"JAR exists: {JAR_PATH.exists()}",
            f"JVM started: {jpype.isJVMStarted()}"
        ]

        if jpype.isJVMStarted():
            try:
                system_class = jpype.JClass("java.lang.System")
                lines.append(
                    "Java version: "
                    + as_text(system_class.getProperty("java.version"))
                )
                lines.append(
                    "Java home: "
                    + as_text(system_class.getProperty("java.home"))
                )
            except Exception:
                pass

        messagebox.showinfo(
            "Environment information",
            "\n".join(lines)
        )

    def show_about(self):
        messagebox.showinfo(
            "About MPP Programme Explorer",
            "MPP Programme Explorer\n\n"
            "A read-only programme browser using Python, Tkinter, "
            "JPype and the MPXJ classes bundled with ProjectLibre.\n\n"
            "The application does not modify the source MPP file."
        )

    def close_application(self):
        try:
            if jpype.isJVMStarted():
                jpype.shutdownJVM()
        except Exception:
            pass

        self.root.destroy()


# ============================================================
# Application entry point
# ============================================================

def main():
    root = tk.Tk()
    ProgrammeExplorer(root)
    root.mainloop()


if __name__ == "__main__":
    main()