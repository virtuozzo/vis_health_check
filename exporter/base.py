import csv
import json
from pathlib import Path

class BaseExporter:
    filename = "base"

    def __init__(self, export_dir, ctx=None):
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.ctx = ctx

    @property
    def filepath(self):
        return self.export_dir / self.filename

    def collect(self):
        raise NotImplementedError


class CSVExporter(BaseExporter):
    filename = "base.csv"


    def write(self, headers, rows):
        filepath = self.export_dir / self.filename

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

    def collect(self):
        raise NotImplementedError

class JSONExporter(BaseExporter):
    filename = "base.json"

    def write(self, data):
        with open(self.filepath, "w") as f:
            json.dump(data, f, indent=2)


class TextExporter(BaseExporter):
    filename = "base.txt"

    def write(self, text):
        with open(self.filepath, "w") as f:
            f.write(text)