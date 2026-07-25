"""Уникальные строки из unsupported_models.csv (без повторов по заявке или по модели)."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    ap = argparse.ArgumentParser(
        description="Оставить уникальные записи из unsupported_models.csv",
    )
    ap.add_argument(
        "-i",
        "--input",
        default="unsupported_models.csv",
        help="Входной CSV",
    )
    ap.add_argument(
        "-o",
        "--output",
        default="unsupported_models_unique.csv",
        help="Выходной CSV",
    )
    ap.add_argument(
        "--by",
        choices=("proposal_id", "model"),
        default="proposal_id",
        help="proposal_id — одна строка на заявку; model — уникальные manufacturer+model",
    )
    a = ap.parse_args()

    path = Path(a.input)
    if not path.is_file():
        print(f"Нет файла: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    fieldnames = list(rows[0].keys()) if rows else []

    seen: set[str] = set()
    out: list[dict] = []

    for row in rows:
        if a.by == "proposal_id":
            key = (row.get("proposal_id") or "").strip()
        else:
            mfg = (row.get("manufacturer") or "").strip()
            mdl = (row.get("model") or "").strip()
            key = f"{mfg}\t{mdl}"
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(row)

    with open(a.output, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)

    print(f"Вход: {len(rows)} строк, уникальных ({a.by}): {len(out)}, файл: {a.output}")


if __name__ == "__main__":
    main()
