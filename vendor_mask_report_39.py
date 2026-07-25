"""Отчёт по mask: объединение ID из proposal_id.csv и unsupported_models_unique.csv (39 шт) — формат как vendor_mask_report.py."""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

PIGNUS_BASE = os.getenv("PIGNUS_BASE", "https://pignus.fun")
TOKEN_URL = f"{PIGNUS_BASE}/api/token/"
DETAIL_URL = f"{PIGNUS_BASE}/api/estimator/proposal"

DELAY = 0.15


def load_vendor_ids(path: str) -> list[int]:
    """ID из колонки ID или proposal_id (как в proposal_id.csv)."""
    ids: list[int] = []
    with open(path, encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        key = next(
            (k for k in (r.fieldnames or []) if (k or "").strip().lower() in ("id", "proposal_id")),
            "ID",
        )
        for row in r:
            v = (row.get(key) or "").strip()
            if v.isdigit():
                ids.append(int(v))
    return ids


def get_token(user: str, pwd: str) -> str:
    r = requests.post(
        TOKEN_URL,
        json={"username": user, "password": pwd},
        timeout=15,
    )
    if r.status_code != 200:
        print(f"Ошибка авторизации {r.status_code}: {r.text[:200]}")
        sys.exit(1)
    return r.json()["access"]


def get_detail(token: str, pid: int) -> dict | None:
    r = requests.get(
        f"{DETAIL_URL}/{pid}/",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        print(f"Ошибка {pid}: HTTP {r.status_code}")
        return None
    return r.json()


def bit(mask: int, n: int) -> int:
    return 1 if (mask & (1 << n)) else 0


def mask_bin8(mask: int) -> str:
    return f"0b{(mask & 0xFF):08b}"


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    ap = argparse.ArgumentParser(
        description=(
            "Отчёт mask: union ID из proposal_id (поддерживаемые эталонные) "
            "и unsupported_models_unique (уникальные отклонённые), сортировка по возрастанию"
        ),
    )
    ap.add_argument(
        "--proposal-id",
        dest="proposal_csv",
        default="proposal_id.csv",
        help="Эталонные поддерживаемые (колонка ID / proposal_id)",
    )
    ap.add_argument(
        "--unsupported",
        dest="unsupported_csv",
        default="unsupported_models_unique.csv",
        help="Уникальные unsupported (колонка proposal_id); если файла нет — только proposal_id",
    )
    ap.add_argument(
        "-o",
        "--out",
        default="vendor_mask_report_39.csv",
        help="Выходной CSV",
    )
    a = ap.parse_args()

    u = os.getenv("PIGNUS_USER")
    pw = os.getenv("PIGNUS_PASSWORD")
    if not u or not pw:
        print("Нужны PIGNUS_USER и PIGNUS_PASSWORD в .env")
        sys.exit(1)

    ids_prop = load_vendor_ids(a.proposal_csv)
    n_prop = len(ids_prop)

    ids_unsup: list[int] = []
    if Path(a.unsupported_csv).is_file():
        ids_unsup = load_vendor_ids(a.unsupported_csv)
    else:
        print(f"(файл {a.unsupported_csv} не найден — только ID из proposal_id)")

    merged = sorted(set(ids_prop) | set(ids_unsup))
    if not merged:
        print("Нет ни одного числового ID")
        sys.exit(1)

    n_unsup = len(set(ids_unsup))
    print(
        f"proposal_id: {n_prop} ID, unsupported (уник.): {n_unsup} ID, "
        f"всего уникальных: {len(merged)}"
    )

    vendor_ids = merged

    token = get_token(u, pw)

    rows: list[dict] = []

    print()
    print(
        f"{'ID':<8}  {'mask':<6}  {'bin':<12}  "
        f"{'b0':<3}{'b1':<3}{'b2':<3}{'b3':<3}{'b4':<3}{'b5':<3}{'b6':<3}{'b7':<3}  "
        f"{'status':<24}  {'title'}"
    )
    print("-" * 138)

    for pid in vendor_ids:
        d = get_detail(token, pid)
        if not d:
            print(f"{pid:<8}  (нет данных)")
            time.sleep(DELAY)
            continue

        mask = int(d.get("mask") or 0)
        status_name = (d.get("_status") or {}).get("name", "")
        title = d.get("title") or (d.get("link_data") or {}).get("title", "")
        mb = mask_bin8(mask)

        row = {
            "proposal_id": pid,
            "title": title,
            "created_at": d.get("created_at", ""),
            "status_name": status_name,
            "mask": mask,
            "mask_bin": mb,
            "bit0": bit(mask, 0),
            "bit1": bit(mask, 1),
            "bit2": bit(mask, 2),
            "bit3": bit(mask, 3),
            "bit4": bit(mask, 4),
            "bit5": bit(mask, 5),
            "bit6": bit(mask, 6),
            "bit7": bit(mask, 7),
        }
        rows.append(row)

        print(
            f"{pid:<8}  {mask:<6}  {mb:<12}  "
            f"{row['bit0']:<3}{row['bit1']:<3}{row['bit2']:<3}{row['bit3']:<3}"
            f"{row['bit4']:<3}{row['bit5']:<3}{row['bit6']:<3}{row['bit7']:<3}  "
            f"{status_name[:24]:<24}  {title[:40]}"
        )
        time.sleep(DELAY)

    print()
    print()

    fieldnames = [
        "proposal_id",
        "title",
        "created_at",
        "status_name",
        "mask",
        "mask_bin",
        "bit0",
        "bit1",
        "bit2",
        "bit3",
        "bit4",
        "bit5",
        "bit6",
        "bit7",
    ]
    with open(a.out, "w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
