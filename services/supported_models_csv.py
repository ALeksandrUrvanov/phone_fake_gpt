"""Лог допущенных заявок: created_at, proposal_id, file_id, manufacturer, model, url, data."""
import asyncio
import csv
import json
import os
from datetime import datetime
from typing import List, Tuple

from config import SUPPORTED_MODELS_CSV_PATH, created_at_csv_msk, log_ts
from models import CheckRequest
from services.csv_common import csv_file_id_suffix, csv_manufacturer_model, csv_proposal_id

_HEADER = "created_at,proposal_id,file_id,manufacturer,model,url,data"
_write_lock = asyncio.Lock()


def _write_rows_sync(
    path: str,
    created_at: str,
    proposal_id: str,
    manufacturer: str,
    model: str,
    rows_data: List[Tuple[str, str, str]],
) -> None:
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        if write_header:
            writer.writerow(_HEADER.split(","))
        for file_id, url, data_json in rows_data:
            writer.writerow([created_at, proposal_id, file_id, manufacturer, model, url, data_json])


async def append_supported_models(dt: datetime, request: CheckRequest, results: list) -> None:
    proposal_id = csv_proposal_id(request)
    manufacturer, model = csv_manufacturer_model(request)
    result_by_id = {r["id"]: r for r in results}
    created_at = created_at_csv_msk(dt)
    rows_data = []
    for f in request.files:
        res = result_by_id.get(f.id, {"status": "unknown", "description": ""})
        fid = csv_file_id_suffix(f.id)
        data_json = json.dumps({"status": res["status"], "description": res.get("description", "")}, ensure_ascii=False)
        rows_data.append((fid, f.url, data_json))
    if not rows_data:
        return
    async with _write_lock:
        try:
            await asyncio.to_thread(
                _write_rows_sync,
                SUPPORTED_MODELS_CSV_PATH,
                created_at,
                proposal_id,
                manufacturer,
                model,
                rows_data,
            )
        except Exception as e:
            print(f"[{log_ts()}] Ошибка записи supported_models.csv: {e}")
