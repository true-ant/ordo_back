import csv
import io
from typing import List, NamedTuple


def export_to_csv(rows: List) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    nt_class: NamedTuple = rows[0].__class__
    fieldnames = nt_class._fields
    writer.writerow(fieldnames)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()
