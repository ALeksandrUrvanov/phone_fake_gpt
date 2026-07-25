"""Отклонённые заявки (UNSUPPORTED_*): created_at, proposal_id, file_id, manufacturer, model, url."""
import asyncio
import csv
import os
from datetime import datetime

from config import UNSUPPORTED_MODELS_CSV_PATH, created_at_csv_msk, log_ts
from models import CheckRequest
from services.csv_common import csv_file_id_suffix, csv_manufacturer_model, csv_proposal_id

_HEADER = "created_at,proposal_id,file_id,manufacturer,model,url"
_write_lock = asyncio.Lock()


def _write_unsupported_sync(path: str, rows: list) -> None:
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        if write_header:
            writer.writerow(_HEADER.split(","))
        writer.writerows(rows)


async def append_unsupported_models(dt: datetime, request: CheckRequest) -> None:
    if not request.files:
        return
    proposal_id = csv_proposal_id(request)
    manufacturer, model = csv_manufacturer_model(request)
    created_at = created_at_csv_msk(dt)
    rows = [
        [created_at, proposal_id, csv_file_id_suffix(f.id), manufacturer, model, f.url]
        for f in request.files
    ]
    async with _write_lock:
        try:
            await asyncio.to_thread(_write_unsupported_sync, UNSUPPORTED_MODELS_CSV_PATH, rows)
        except Exception as e:
            print(f"[{log_ts()}] Ошибка записи unsupported_models.csv: {e}")
