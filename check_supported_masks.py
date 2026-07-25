"""Проверка mask в conflicts_supported.csv: биты 4/7 и (mask & 144) == 144, vendor vs extra."""

from __future__ import annotations

import argparse
import csv
from collections import Counter

MASK_VENDOR_HUMAN = 144  # биты 4 (16) и 7 (128)


def load_ids(path: str) -> set[int]:
    ids: set[int] = set()
    with open(path, encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        key = next(
            (k for k in (r.fieldnames or []) if (k or "").strip().lower() in ("id", "proposal_id")),
            "ID",
        )
        for row in r:
            v = (row.get(key) or "").strip()
            if v.isdigit():
                ids.add(int(v))
    return ids


def main() -> None:
    ap = argparse.ArgumentParser(description="Анализ mask в выгрузке конфликтов")
    ap.add_argument("--conflicts", default="conflicts_supported.csv", help="CSV выгрузки")
    ap.add_argument("--vendor", default="proposal_id.csv", help="Эталонные ID (vendor)")
    a = ap.parse_args()

    vendor_ids = load_ids(a.vendor)

    with open(a.conflicts, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    print(f"Файл: {a.conflicts}")
    print(f"Эталон: {a.vendor}  (ID: {len(vendor_ids)})")
    print(f"Строк: {len(rows)}")
    print()

    print(
        f"{'ID':<8} {'mask':<6} {'bin':<12} {'bit4':<5} {'bit7':<5} "
        f"{'(m&144)==144':<13} {'grp':<7} {'status':<24} {'title'}"
    )
    print("-" * 130)

    mask_counter: Counter[int] = Counter()
    by_group: Counter[tuple[str, int]] = Counter()
    cnt_144 = 0
    cnt_bit4 = 0
    cnt_bit7 = 0

    for row in rows:
        pid = int(row["proposal_id"])
        mask = int(row.get("mask") or 0)
        bit4 = 1 if (mask & 16) else 0
        bit7 = 1 if (mask & 128) else 0
        ok144 = 1 if ((mask & MASK_VENDOR_HUMAN) == MASK_VENDOR_HUMAN) else 0
        grp = "vendor" if pid in vendor_ids else "extra"

        print(
            f"{pid:<8} {mask:<6} 0b{mask:08b}   "
            f"{bit4:<5} {bit7:<5} {('YES' if ok144 else 'no'):<13} "
            f"{grp:<7} {(row.get('status_name') or '')[:24]:<24} "
            f"{(row.get('title') or '')[:40]}"
        )

        mask_counter[mask] += 1
        by_group[(grp, mask)] += 1
        cnt_144 += ok144
        cnt_bit4 += bit4
        cnt_bit7 += bit7

    print("\n" + "=" * 70)
    print("ИТОГО")
    print("=" * 70)
    print(f"Всего строк: {len(rows)}")
    print(f"bit4=1: {cnt_bit4}")
    print(f"bit7=1: {cnt_bit7}")
    print(f"(mask & {MASK_VENDOR_HUMAN}) == {MASK_VENDOR_HUMAN}: {cnt_144}")

    print("\nРаспределение mask:")
    for m, c in sorted(mask_counter.items()):
        print(f"  mask={m:<4} count={c}")

    print("\nРаспределение mask по группам:")
    for (grp, m), c in sorted(by_group.items()):
        print(f"  {grp:<7} mask={m:<4} count={c}")

    print("\nВывод:")
    if cnt_144 == 0:
        print("  Ни одна заявка из выгрузки не удовлетворяет условию (mask & 144) == 144.")
        print("  Правило вендора не бьётся с полем mask в этом CSV.")
    else:
        print("  Есть заявки, удовлетворяющие (mask & 144) == 144.")


if __name__ == "__main__":
    main()
