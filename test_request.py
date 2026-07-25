"""Тестовый запрос на /check по заявке из list_photos.csv. Результаты — /test-webhook → /test-result.

  python test_request.py 602110

Webhook по умолчанию http://127.0.0.1:8085/test-webhook — адрес ВНУТРИ контейнера/процесса API.
С публичным IP (178.../test-webhook) из Docker часто не коннектится (hairpin). Результаты забираются
с вашего ПК через GET <TEST_SERVER>/test-result.

Переменные (.env):
  API_TOKEN — обязательно
  TEST_SERVER — с ПК: http://localhost:8085 (куда слать /check и откуда читать /test-result)
  TEST_WEBHOOK_URL — если нужен другой webhook (например ngrok на ваш ПК)

Опционально proposal_id.csv: ID, Залог. Иначе Apple + iPhone 16 Pro Max.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
LIST_PHOTOS_CSV = BASE_DIR / "list_photos.csv"
PROPOSAL_ID_CSV = BASE_DIR / "proposal_id.csv"

DEFAULT_SERVER = os.getenv("TEST_SERVER", "http://localhost:8085").rstrip("/")
# Внутри контейнера API и /test-webhook — один процесс; не использовать публичный IP в webhook
DEFAULT_WEBHOOK_INSIDE = "http://127.0.0.1:8085/test-webhook"
_env_wh = os.getenv("TEST_WEBHOOK_URL", "").strip()
API_TOKEN = os.getenv("API_TOKEN")
POLL_INTERVAL = 3
POLL_TIMEOUT = 300
DEFAULT_PROPOSAL_ID = "602110"


def load_photos_for_proposal(proposal_id: str) -> list[tuple[str, str]]:
    """(file_id, url) по заявке из list_photos.csv."""
    if not LIST_PHOTOS_CSV.exists():
        return []
    import csv

    with open(LIST_PHOTOS_CSV, encoding="utf-8", newline="") as f:
        rows = []
        for row in csv.DictReader(f):
            if (row.get("proposal_id") or "").strip() != proposal_id:
                continue
            fid = (row.get("file_id") or "").strip()
            url = (row.get("url") or "").strip()
            if fid and url:
                rows.append((fid, url))
    return rows


def load_proposal_device(proposal_id: str) -> tuple[str, str]:
    """manufacturer, model из proposal_id.csv или значения по умолчанию."""
    manufacturer, model = "Apple", "iPhone 16 Pro Max"
    if not PROPOSAL_ID_CSV.exists():
        return manufacturer, model
    import csv

    with open(PROPOSAL_ID_CSV, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("ID") or "").strip() != proposal_id:
                continue
            zalog = (row.get("Залог") or "").strip()
            if zalog:
                parts = zalog.split(None, 1)
                if len(parts) >= 2:
                    manufacturer, model = parts[0], parts[1]
                elif parts:
                    manufacturer = parts[0]
            break
    return manufacturer, model


def wait_and_print_results(server_base: str) -> None:
    result_url = f"{server_base.rstrip('/')}/test-result"
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        try:
            r = requests.get(result_url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                    return
        except (requests.RequestException, json.JSONDecodeError):
            pass
        time.sleep(POLL_INTERVAL)
    print("Таймаут: результаты не получены (проверьте TEST_WEBHOOK_URL и что сервис принимает webhook).")


def send_test_request(proposal_id: str, server_base: str, webhook_url: str) -> None:
    if not API_TOKEN:
        print("Задайте API_TOKEN в .env")
        sys.exit(1)
    photos = load_photos_for_proposal(proposal_id)
    if not photos:
        print(f"В {LIST_PHOTOS_CSV} нет строк с proposal_id={proposal_id}")
        sys.exit(1)
    manufacturer, model = load_proposal_device(proposal_id)
    files = [{"id": f"{proposal_id}_{fid}", "url": url} for fid, url in photos]
    payload = {
        "env": "test0",
        "webhook_url": webhook_url,
        "model_type": "phone",
        "model_param": {"manufacturer": manufacturer, "model": model},
        "files": files,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_TOKEN}"}
    check_url = f"{server_base.rstrip('/')}/check"
    print(f"POST {check_url} — заявка {proposal_id}, {len(files)} фото, {manufacturer} {model}")
    try:
        response = requests.post(check_url, json=payload, headers=headers, timeout=60)
        print(f"Статус: {response.status_code}")
        try:
            print(response.json())
        except json.JSONDecodeError:
            print(response.text[:500])
        if response.status_code == 201:
            wait_and_print_results(server_base)
    except requests.RequestException as e:
        print(f"Ошибка: {e}")
        sys.exit(1)


def main() -> None:
    p = argparse.ArgumentParser(description="Тест /check по list_photos.csv")
    p.add_argument("proposal_id", nargs="?", default=DEFAULT_PROPOSAL_ID, help="Номер заявки")
    p.add_argument("--server", default=DEFAULT_SERVER, help="Базовый URL API")
    p.add_argument("--webhook", default="", help=f"Иначе {DEFAULT_WEBHOOK_INSIDE} (для Docker на сервере)")
    args = p.parse_args()
    pid = (args.proposal_id or DEFAULT_PROPOSAL_ID).strip() or DEFAULT_PROPOSAL_ID
    base = args.server.rstrip("/")
    webhook = _env_wh or args.webhook.strip() or DEFAULT_WEBHOOK_INSIDE
    send_test_request(pid, base, webhook)


if __name__ == "__main__":
    main()
