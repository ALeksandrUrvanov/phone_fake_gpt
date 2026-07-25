"""Глубокое сравнение: эталон proposal_id vs остальные строки в conflicts_supported."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter


def load_vendor_ids(path: str) -> set[int]:
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


def load_rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_json(path: str) -> dict[int, dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    out: dict[int, dict] = {}
    for d in data:
        pid = d.get("proposal_id")
        if isinstance(pid, int):
            out[pid] = d
        elif isinstance(pid, str) and pid.isdigit():
            out[int(pid)] = d
    return out


def print_section(title: str) -> None:
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")


def print_counter(title: str, rows: list[dict], key: str) -> None:
    c = Counter(str(row.get(key) or "").strip() for row in rows)
    print(f"\n  {title}:")
    if not rows:
        print("    (нет строк)")
        return
    for k, v in c.most_common():
        pct = v * 100 / len(rows)
        print(f"    {k or '(пусто)':<35} {v:>3}  ({pct:.0f}%)")


def analyze_td_details(title: str, rows: list[dict]) -> None:
    print(f"\n  {title}:")

    for row in rows:
        pid_raw = row.get("proposal_id") or ""
        if not pid_raw.isdigit():
            continue
        pid = int(pid_raw)
        nf = int(row.get("td_fake") or 0)
        no = int(row.get("td_original") or 0)
        nu = int(row.get("td_unknown") or 0)
        total_files = nf + no + nu
        fake_ratio = nf / total_files if total_files > 0 else 0.0

        print(
            f"    {pid}  m={str(row.get('mask', '')):<4} "
            f"f={nf} o={no} u={nu} "
            f"ratio={fake_ratio:.0%}  "
            f"[{row.get('status_name', '')}]  "
            f"{str(row.get('title', ''))[:35]}"
        )


def analyze_fake_ratio(title: str, rows: list[dict]) -> None:
    ratios: list[float] = []
    for row in rows:
        nf = int(row.get("td_fake") or 0)
        no = int(row.get("td_original") or 0)
        nu = int(row.get("td_unknown") or 0)
        total = nf + no + nu
        if total > 0:
            ratios.append(nf / total)

    if not ratios:
        print(f"\n  {title}: (нет данных)")
        return

    avg = sum(ratios) / len(ratios)
    mn = min(ratios)
    mx = max(ratios)

    print(f"\n  {title}:")
    print(f"    avg fake ratio: {avg:.0%}")
    print(f"    min: {mn:.0%}, max: {mx:.0%}")

    buckets: Counter[str] = Counter()
    for r in ratios:
        if r <= 0.2:
            buckets["0-20%"] += 1
        elif r <= 0.4:
            buckets["21-40%"] += 1
        elif r <= 0.6:
            buckets["41-60%"] += 1
        elif r <= 0.8:
            buckets["61-80%"] += 1
        else:
            buckets["81-100%"] += 1

    for bucket in ["0-20%", "21-40%", "41-60%", "61-80%", "81-100%"]:
        cnt = buckets.get(bucket, 0)
        pct = cnt * 100 / len(ratios)
        bar = "█" * int(pct / 5)
        print(f"    {bucket:<8} {cnt:>3}  ({pct:>4.0f}%) {bar}")


def analyze_file_counts(title: str, rows: list[dict], json_data: dict[int, dict]) -> None:
    counts: list[int] = []
    for row in rows:
        pid_raw = row.get("proposal_id") or ""
        if not pid_raw.isdigit():
            continue
        pid = int(pid_raw)
        jd = json_data.get(pid, {})
        files = jd.get("files") or []
        counts.append(len(files))

    if not counts:
        print(f"\n  {title}: (нет JSON или нет файлов — пропуск)")
        return

    print(f"\n  {title}:")
    print(f"    avg files: {sum(counts)/len(counts):.1f}")
    print(f"    min: {min(counts)}, max: {max(counts)}")

    c = Counter(counts)
    for n, cnt in sorted(c.items()):
        print(f"    {n} файлов: {cnt} заявок")


def analyze_descriptions_detail(title: str, rows: list[dict]) -> None:
    print(f"\n  {title}:")

    all_descs: list[str] = []
    for row in rows:
        descs = row.get("td_descriptions", "")
        parts = [p.strip() for p in descs.split(" | ") if p.strip()]
        all_descs.extend(parts)

    if all_descs:
        lens = [len(d) for d in all_descs]
        print(f"    Всего fake-фрагментов: {len(all_descs)}")
        print(f"    Средняя длина: {sum(lens)/len(lens):.0f}")
        print(f"    Min: {min(lens)}, Max: {max(lens)}")
    else:
        print("    (нет описаний)")

    keywords: Counter[str] = Counter()
    kw_list = [
        "версия", "имя", "модель", "прошивка", "аккумулятор",
        "face id", "sim", "imei", "блокировка", "оператор",
        "настроек", "меню", "пункт", "заголовок", "формулировк",
        "регистр", "порядок", "отсутств", "обрезан", "эталон",
    ]
    for desc in all_descs:
        dl = desc.lower()
        for kw in kw_list:
            if kw in dl:
                keywords[kw] += 1

    if keywords and all_descs:
        print("\n    Ключевые слова в описаниях:")
        total = len(all_descs)
        for kw, cnt in keywords.most_common():
            pct = cnt * 100 / total
            print(f"      {kw:<20} {cnt:>3}  ({pct:.0f}%)")


def analyze_models(title: str, rows: list[dict]) -> None:
    print(f"\n  {title}:")

    apple = 0
    samsung = 0
    for row in rows:
        t = (row.get("title") or "").upper()
        if "APPLE" in t or "IPHONE" in t:
            apple += 1
        elif "SAMSUNG" in t:
            samsung += 1

    print(f"    Apple: {apple}, Samsung: {samsung}")

    c = Counter((row.get("title") or "").strip() for row in rows)
    for model, cnt in c.most_common():
        print(f"    {model:<45} {cnt}")


def time_stats(title: str, rows: list[dict]) -> None:
    hours: list[int] = []
    dates: Counter[str] = Counter()
    for row in rows:
        ca = row.get("created_at", "") or ""
        if len(ca) >= 13:
            try:
                h = int(ca[11:13])
                hours.append(h)
            except ValueError:
                pass
        if len(ca) >= 10:
            dates[ca[:10]] += 1

    print(f"\n  {title}:")
    if hours:
        print(f"    Средний час: {sum(hours)/len(hours):.1f}")
        print(f"    Min час: {min(hours)}, Max час: {max(hours)}")
        hc = Counter(hours)
        for h in sorted(hc):
            print(f"      {h:02d}:xx  {hc[h]:>3}")
    else:
        print("    (нет времени)")
    if dates:
        print("    По датам:")
        for d, cnt in sorted(dates.items()):
            print(f"      {d}  {cnt}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Глубокое сравнение эталона и лишних в выгрузке")
    ap.add_argument("--vendor", default="proposal_id.csv", help="Эталонные ID")
    ap.add_argument("--conflicts", default="conflicts_supported.csv", help="Выгрузка конфликтов")
    ap.add_argument(
        "--json",
        default="conflicts_supported_files.json",
        help="JSON-сайдкар (опционально)",
    )
    a = ap.parse_args()

    vendor_ids = load_vendor_ids(a.vendor)
    all_rows = load_rows(a.conflicts)
    json_data = load_json(a.json)

    vendor_rows: list[dict] = []
    extra_rows: list[dict] = []

    for row in all_rows:
        pid_raw = (row.get("proposal_id") or "").strip()
        if not pid_raw.isdigit():
            continue
        pid = int(pid_raw)
        if pid in vendor_ids:
            vendor_rows.append(row)
        else:
            extra_rows.append(row)

    print(f"Файл эталона: {a.vendor}  (ID: {len(vendor_ids)})")
    print(f"Выгрузка:    {a.conflicts}  (строк: {len(all_rows)})")
    print(f"JSON:        {a.json}  (заявок в индексе: {len(json_data)})")
    print(f"Эталонных в выгрузке: {len(vendor_rows)}")
    print(f"Лишних:               {len(extra_rows)}")

    print_section("1. СТАТУСЫ")
    print_counter("Эталон", vendor_rows, "status_name")
    print_counter("Лишние", extra_rows, "status_name")

    print_section("2. МАСКИ")
    print_counter("Эталон", vendor_rows, "mask")
    print_counter("Лишние", extra_rows, "mask")

    print_section("3. МОДЕЛИ")
    analyze_models("Эталон", vendor_rows)
    analyze_models("Лишние", extra_rows)

    print_section("4. TD ДЕТАЛИ (каждая заявка)")
    analyze_td_details("Эталон", vendor_rows)
    analyze_td_details("Лишние", extra_rows)

    print_section("5. ДОЛЯ FAKE от проверенных файлов")
    analyze_fake_ratio("Эталон", vendor_rows)
    analyze_fake_ratio("Лишние", extra_rows)

    print_section("6. КОЛИЧЕСТВО ФАЙЛОВ В ЗАЯВКЕ")
    analyze_file_counts("Эталон", vendor_rows, json_data)
    analyze_file_counts("Лишние", extra_rows, json_data)

    print_section("7. ОПИСАНИЯ FAKE")
    analyze_descriptions_detail("Эталон", vendor_rows)
    analyze_descriptions_detail("Лишние", extra_rows)

    print_section("8. ВРЕМЯ СОЗДАНИЯ")
    time_stats("Эталон", vendor_rows)
    time_stats("Лишние", extra_rows)

    print_section("9. ИТОГ")
    print("""
  Если метрики похожи — «лишние» неотличимы от эталона по этим полям API.

  Если что-то заметно расходится — возможный кандидат на скрытый отбор вендора
  (или нужны другие поля из API / ручная выборка).
    """)


if __name__ == "__main__":
    main()
