"""
csv_log.py — Append trade events to a local CSV file.
"""

import csv
import os
from config import CSV_COLUMNS


class CSVLogger:

    def __init__(self, filepath: str):
        self.filepath = filepath
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        self._init_file()

    def _init_file(self):
        """Create file with header row if it doesn't exist."""
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                writer.writeheader()

    def write(self, row: dict):
        """Append a single row to the CSV."""
        with open(self.filepath, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS,
                                    extrasaction="ignore")
            writer.writerow(row)
