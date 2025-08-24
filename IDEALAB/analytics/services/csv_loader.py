# analytics/services/csv_loader.py
import csv
from typing import Dict, Iterator, Optional

def read_csv_rows(path: str, encoding: str = "cp949") -> Iterator[Dict[str, str]]:
    with open(path, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}


def to_decimal_safe(val: Optional[str]):
    if val in (None, "", "NULL", "NaN", "nan"):
        return None
    try:
        # 콤마/공백 제거
        s = str(val).replace(",", "").strip()
        return s
    except Exception:
        return None
