from __future__ import annotations

import argparse
import csv
import json
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
ITEM_PHONE = 49
MASK_TD_MIN = 12  # биты 2+3: TD прошёл; фильтр mask >= 12
DELAY = 0.15
TOKEN_LIFETIME = 240

# Как в api/routes.py: строка title проверяется на подстроки
SUPPORTED_MODELS = {
    "apple": ("IPHONE 15", "IPHONE 16", "IPHONE 17"),
    "samsung": ("S24", "S25"),
}

CSV_FIELDS = [
    "proposal_id",
    "created_at",
    "title",
    "mask",
    "status_name",
    "td_fake",
    "td_original",
    "td_unknown",
    "td_label",
    "conflict_type",
    "td_descriptions",
]


def conflict_type_label() -> str:
    return f"TD=подделка, mask>={MASK_TD_MIN}"


class TokenManager:
    def __init__(self, user: str, pwd: str):
        self.user = user
        self.pwd = pwd
        self.token: str | None = None
        self.expires = 0.0

    def get(self) -> str:
        if not self.token or time.time() >= self.expires:
            r = requests.post(
                TOKEN_URL,
                json={"username": self.user, "password": self.pwd},
                timeout=15,
            )
            if r.status_code != 200:
                print(f"Ошибка авторизации {r.status_code}: {r.text[:200]}")
                sys.exit(1)
            self.token = r.json()["access"]
            self.expires = time.time() + TOKEN_LIFETIME
            print("Токен обновлён")
        return self.token

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.get()}"}


def get_detail(tm: TokenManager, pid: int) -> dict | None:
    try:
        r = requests.get(f"{DETAIL_URL}/{pid}/", headers=tm.headers, timeout=30)
    except requests.RequestException:
        return {"_error": "request"}
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        return {"_error": r.status_code}
    return r.json()


def date_only(s: str) -> str:
    return (s or "")[:10]


def is_supported_model(title: str) -> bool:
    """Совпадает с логикой api/routes.py по подстрокам в model/title."""
    t = title.upper()

    if "APPLE" in t or "IPHONE" in t:
        return any(m in t for m in SUPPORTED_MODELS["apple"])

    if "SAMSUNG" in t:
        return any(m in t for m in SUPPORTED_MODELS["samsung"])

    return False


def _file_truedevice(f: dict) -> dict | None:
    data = f.get("data")
    td = None
    if isinstance(data, dict):
        td = data.get("truedevice")
    if not isinstance(td, dict):
        td = f.get("truedevice")
    return td if isinstance(td, dict) else None


def td_info(files: list) -> tuple[int, int, int, str, str]:
    nf = no = nu = 0
    descs = []

    for f in files or []:
        td = _file_truedevice(f)
        if not td:
            continue

        st = (td.get("status") or "").lower()
        if st == "fake":
            nf += 1
            desc = td.get("description") or ""
            if desc:
                descs.append(desc)
        elif st == "original":
            no += 1
        elif st == "unknown":
            nu += 1

    if nf > 0:
        label = "подделка"
    elif no > 0:
        label = "оригинал"
    elif nu > 0:
        label = "неизвестно"
    else:
        label = ""

    return nf, no, nu, label, " | ".join(descs)


def row_from_detail(d: dict) -> tuple[dict, dict]:
    files = d.get("files") or []
    nf, no, nu, td_label, descs = td_info(files)
    mask = int(d.get("mask") or 0)
    ct = (
        conflict_type_label()
        if td_label == "подделка" and mask >= MASK_TD_MIN
        else ""
    )

    row = {
        "proposal_id": d.get("id", ""),
        "created_at": d.get("created_at", ""),
        "title": d.get("title") or (d.get("link_data") or {}).get("title", ""),
        "mask": mask,
        "status_name": (d.get("_status") or {}).get("name", ""),
        "td_fake": nf,
        "td_original": no,
        "td_unknown": nu,
        "td_label": td_label,
        "conflict_type": ct,
        "td_descriptions": descs,
    }

    dump = {
        "proposal_id": d.get("id"),
        "created_at": d.get("created_at"),
        "mask": d.get("mask"),
        "status_name": (d.get("_status") or {}).get("name"),
        "files": [
            {
                "file_id": f.get("id"),
                "url": f.get("url"),
                "truedevice": _file_truedevice(f),
            }
            for f in files
        ],
    }
    return row, dump


def save_csv(rows: list[dict], out: str) -> None:
    with open(out, "w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def json_sidecar_path(csv_path: str) -> str:
    p = Path(csv_path)
    return str(p.with_name(p.stem + "_files").with_suffix(".json"))


def scan_conflicts(
    tm: TokenManager,
    id_from: int,
    id_to: int,
    date_from: str,
    date_to: str,
    out: str,
    with_json: bool,
) -> None:
    rows = []
    dumps = []

    checked = found = closed = phones = in_dates = 0
    with_td = conflicts = supported = skipped_model = 0
    ct_label = conflict_type_label()

    print(f"ID: {id_from}..{id_to}")
    print(f"Даты: {date_from}..{date_to}")
    print("Модели: Apple iPhone 15/16/17, Samsung Galaxy S24/S25 (как в api/routes.py)")
    print(
        f"Фильтр: закрытые телефоны, TD=подделка, mask>={MASK_TD_MIN}, поддерживаемые модели"
    )

    for pid in range(id_from, id_to + 1):
        checked += 1
        d = get_detail(tm, pid)

        if not d or "_error" in d:
            time.sleep(DELAY)
            continue

        found += 1

        if not d.get("is_closed", False):
            time.sleep(DELAY)
            continue
        closed += 1

        item_id = (d.get("item") or {}).get("id")
        if item_id != ITEM_PHONE:
            time.sleep(DELAY)
            continue
        phones += 1

        created = date_only(d.get("created_at", ""))
        if not (date_from <= created <= date_to):
            time.sleep(DELAY)
            continue
        in_dates += 1

        row, dump = row_from_detail(d)

        if not row["td_label"]:
            time.sleep(DELAY)
            continue
        with_td += 1

        if row["conflict_type"] != ct_label:
            time.sleep(DELAY)
            continue

        conflicts += 1

        title = row["title"] or ""
        if not is_supported_model(title):
            skipped_model += 1
            time.sleep(DELAY)
            continue

        supported += 1
        rows.append(row)
        if with_json:
            dumps.append(dump)

        print(
            f"+ {row['proposal_id']} [{row['status_name']}] "
            f"m={row['mask']} td=f{row['td_fake']}/o{row['td_original']} "
            f"| {title[:40]}"
        )

        if checked % 500 == 0:
            save_csv(rows, out)
            print(
                f"--- checked={checked} found={found} closed={closed} "
                f"phones={phones} in_dates={in_dates} td={with_td} "
                f"conflicts={conflicts} supported={supported} skipped_model={skipped_model}"
            )

        time.sleep(DELAY)

    save_csv(rows, out)
    print("\nГотово")
    print(
        f"checked={checked}, found={found}, closed={closed}, phones={phones}, "
        f"in_dates={in_dates}, td={with_td}, conflicts={conflicts}, "
        f"supported={supported}, skipped_model={skipped_model}"
    )
    print(f"CSV: {out}")

    if with_json and dumps:
        jp = json_sidecar_path(out)
        with open(jp, "w", encoding="utf-8") as fp:
            json.dump(dumps, fp, ensure_ascii=False, indent=2)
        print(f"JSON: {jp}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Конфликтные TD-заявки: TD=подделка, mask>=12, модели как в API"
    )
    ap.add_argument("--id-from", type=int, required=True)
    ap.add_argument("--id-to", type=int, required=True)
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
    ap.add_argument("-o", "--out", default="conflicts.csv")
    ap.add_argument("--with-json", action="store_true")
    a = ap.parse_args()

    u = os.getenv("PIGNUS_USER")
    pw = os.getenv("PIGNUS_PASSWORD")
    if not u or not pw:
        print("Нужны PIGNUS_USER и PIGNUS_PASSWORD в .env")
        sys.exit(1)

    tm = TokenManager(u, pw)
    scan_conflicts(tm, a.id_from, a.id_to, a.date_from, a.date_to, a.out, a.with_json)


if __name__ == "__main__":
    main()
