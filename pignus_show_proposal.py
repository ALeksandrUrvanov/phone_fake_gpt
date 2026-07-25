"""Вывод в консоль данных заявки Pignus по ID (как в API detail)."""

from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from pignus_conflicts import (  # noqa: E402
    TokenManager,
    _file_truedevice,
    get_detail,
)


def _mask_bits(mask: int) -> str:
    return " ".join("1" if mask & (1 << b) else "0" for b in range(8))


def print_proposal(d: dict, full: bool) -> None:
    if full:
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return

    pid = d.get("id")
    title = d.get("title") or (d.get("link_data") or {}).get("title", "")
    mask = int(d.get("mask") or 0)
    status = (d.get("_status") or {}).get("name", "")
    item = (d.get("item") or {}).get("name") or (d.get("item") or {}).get("id")

    print(f"id:           {pid}")
    print(f"title:        {title}")
    print(f"created_at:   {d.get('created_at', '')}")
    print(f"is_closed:    {d.get('is_closed')}")
    print(f"status:       {status}")
    print(f"item:         {item}")
    print(f"mask:         {mask}  (0b{mask:08b})  bits[0..7]: {_mask_bits(mask)}")
    print(f"(mask & 144) == 144:  {(mask & 144) == 144}")
    print()

    files = d.get("files") or []
    print(f"files: {len(files)}")
    for i, f in enumerate(files, 1):
        fid = f.get("id")
        url = (f.get("url") or "")[:80]
        td = _file_truedevice(f)
        if td:
            st = (td.get("status") or "")
            desc = (td.get("description") or "")[:200]
            print(f"  [{i}] file_id={fid}")
            print(f"      url: {url}{'...' if len(f.get('url') or '') > 80 else ''}")
            print(f"      truedevice.status: {st}")
            if desc:
                print(f"      truedevice.description: {desc}{'...' if len(td.get('description') or '') > 200 else ''}")
        else:
            print(f"  [{i}] file_id={fid}  (нет truedevice)")
            print(f"      url: {url}{'...' if len(f.get('url') or '') > 80 else ''}")
        print()


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    ap = argparse.ArgumentParser(description="Показать заявку Pignus в консоли")
    ap.add_argument("proposal_id", type=int, help="Номер заявки, напр. 602109")
    ap.add_argument(
        "--full",
        action="store_true",
        help="Полный JSON ответа API",
    )
    a = ap.parse_args()

    u = os.getenv("PIGNUS_USER")
    pw = os.getenv("PIGNUS_PASSWORD")
    if not u or not pw:
        print("Нужны PIGNUS_USER и PIGNUS_PASSWORD в .env", file=sys.stderr)
        sys.exit(1)

    tm = TokenManager(u, pw)
    d = get_detail(tm, a.proposal_id)

    if d is None:
        print(f"Заявка {a.proposal_id}: не найдена (404)", file=sys.stderr)
        sys.exit(1)
    if "_error" in d:
        print(f"Ошибка: {d}", file=sys.stderr)
        sys.exit(1)

    print_proposal(d, a.full)


if __name__ == "__main__":
    main()
