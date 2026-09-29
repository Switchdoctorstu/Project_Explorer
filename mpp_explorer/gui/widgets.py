from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def as_text(value) -> str:
    if value is None:
        return ""
    return str(value)


class ScrollableTree(ttk.Frame):
    def __init__(self, parent, columns, headings=None, tree_column=True):
        super().__init__(parent)

        show_mode = "tree headings" if tree_column else "headings"
        self.tree = ttk.Treeview(self, columns=columns, show=show_mode, selectmode="browse")

        vertical_scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        horizontal_scrollbar = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical_scrollbar.set, xscrollcommand=horizontal_scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical_scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal_scrollbar.grid(row=1, column=0, sticky="ew")

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        headings = headings or {}
        for column in columns:
            title = headings.get(column, column)
            self.tree.heading(column, text=title, command=lambda c=column: self.sort_by_column(c, False))

    def clear(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def sort_by_column(self, column, descending):
        rows = []
        for item_id in self.tree.get_children(""):
            rows.append((self.tree.set(item_id, column), item_id))

        def sort_key(item):
            value = item[0]
            try:
                return 0, float(value.replace("%", "").replace(",", ""))
            except Exception:
                return 1, value.lower()

        rows.sort(key=sort_key, reverse=descending)
        for index, (_, item_id) in enumerate(rows):
            self.tree.move(item_id, "", index)

        self.tree.heading(column, command=lambda: self.sort_by_column(column, not descending))


class PropertyGrid(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.tree_frame = ScrollableTree(self, columns=("Value",), headings={"Value": "Value"}, tree_column=True)
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
            self.tree.insert("", "end", text=property_name, values=(as_text(value),))
