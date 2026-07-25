"""
Конвертация xlsx в CSV (только stdlib).
Запуск:
  python xlsx_to_csv.py [файл.xlsx]   # по умолчанию ai_error.xlsx -> ai_error.csv
"""
import csv
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
BASE_DIR = Path(__file__).parent


def col_ref_to_index(ref: str) -> int:
    """A->0, B->1, ..., Z->25, AA->26."""
    i = 0
    for c in ref.upper():
        if "A" <= c <= "Z":
            i = i * 26 + (ord(c) - ord("A") + 1)
    return i - 1


def parse_cell_ref(ref: str) -> tuple[int, int]:
    """'A1' -> (0, 0), 'B2' -> (1, 1)."""
    m = re.match(r"^([A-Z]+)(\d+)$", ref.upper())
    if not m:
        return -1, -1
    col = col_ref_to_index(m.group(1))
    row = int(m.group(2)) - 1
    return row, col


def load_shared_strings(zipf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zipf.namelist():
        return []
    with zipf.open("xl/sharedStrings.xml") as f:
        root = ET.parse(f).getroot()
    strings = []
    for si in root.findall("main:si", NS):
        t = si.find("main:t", NS)
        if t is not None:
            strings.append(t.text or "")
        else:
            parts = []
            for e in si.iter():
                if "}" in e.tag and e.tag.split("}")[1] == "t":
                    parts.append(e.text or "")
            strings.append("".join(parts))
    return strings


def load_sheet_rows(zipf: zipfile.ZipFile, shared_strings: list[str]) -> list[list[str]]:
    with zipf.open("xl/worksheets/sheet1.xml") as f:
        root = ET.parse(f).getroot()
    # Собираем ячейки по (row, col); row/c из тега main:row и main:c
    grid: dict[tuple[int, int], str] = {}
    for row_elem in root.findall(".//main:row", NS):
        row_num = int(row_elem.get("r", 0)) - 1
        for c in row_elem.findall("main:c", NS):
            ref = c.get("r", "")
            _, col = parse_cell_ref(ref)
            if col < 0:
                continue
            t = c.get("t")
            v = c.find("main:v", NS)
            val = (v.text or "").strip() if v is not None and v.text else ""
            if t == "s" and val.isdigit():
                idx = int(val)
                val = shared_strings[idx] if idx < len(shared_strings) else val
            grid[(row_num, col)] = val
    if not grid:
        return []
    max_row = max(r for r, _ in grid)
    max_col = max(c for _, c in grid)
    rows = []
    for r in range(max_row + 1):
        row = []
        for c in range(max_col + 1):
            row.append(grid.get((r, c), ""))
        rows.append(row)
    return rows


def main():
    xlsx_name = (sys.argv[1] if len(sys.argv) > 1 else "ai_error.xlsx").strip()
    if not xlsx_name.lower().endswith(".xlsx"):
        xlsx_name = xlsx_name + ".xlsx"
    xlsx_path = BASE_DIR / xlsx_name
    csv_path = BASE_DIR / (xlsx_path.stem + ".csv")
    if not xlsx_path.exists():
        print(f"Файл не найден: {xlsx_path}")
        return
    with zipfile.ZipFile(xlsx_path) as z:
        shared = load_shared_strings(z)
        rows = load_sheet_rows(z, shared)
    if not rows:
        print("Лист пуст или не удалось прочитать.")
        return
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        for row in rows:
            writer.writerow(row)
    print(f"Записано {len(rows)} строк в {csv_path}")


if __name__ == "__main__":
    main()
