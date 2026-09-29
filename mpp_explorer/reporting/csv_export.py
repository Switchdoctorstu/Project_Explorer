from __future__ import annotations

import csv


def export_tree_to_csv(tree, filename: str) -> None:
    columns = list(tree["columns"])
    with open(filename, "w", newline="", encoding="utf-8-sig") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(columns)
        for item_id in tree.get_children(""):
            writer.writerow([tree.set(item_id, column) for column in columns])
