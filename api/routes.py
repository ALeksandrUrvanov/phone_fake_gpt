import os
import asyncio
import json
from datetime import datetime
import aiohttp

from fastapi import APIRouter, HTTPException, Header, Depends, Request
from fastapi.responses import JSONResponse

from config import CHECK_MAX_CONCURRENT, log_ts
from models import CheckRequest, CheckResponse, ErrorResult, ModelType
from services.image_service import download_image
from services.detection_service import filter_menu_photos, analyze_photos
from services.webhook_service import send_webhook
from services.supported_models_csv import append_supported_models
from services.unsupported_models_csv import append_unsupported_models


router = APIRouter()
_check_semaphore = asyncio.Semaphore(CHECK_MAX_CONCURRENT)

_last_test_result = None
_requests_total = 0


async def _respond_unsupported(
    start_time: datetime,
    request: CheckRequest,
    error_code: str,
    error_description: str,
) -> JSONResponse:
    """400 + запись в unsupported_models.csv только для phone (не для не‑phone)."""
    body = CheckResponse(
        ok=False,
        result=ErrorResult(error_code=error_code, error_description=error_description),
    )
    print(f"[{log_ts()}] /check 400: {error_code} — {error_description}")
    if request.model_type == ModelType.phone:
        try:
            await append_unsupported_models(start_time, request)
        except Exception as e:
            print(f"[{log_ts()}] Ошибка записи unsupported_models.csv: {e}")
    return JSONResponse(status_code=400, content=body.model_dump())


def _finalize_missing_files(results: list, all_file_ids: list) -> None:
    """Добавить статус 'unknown' для необработанных файлов."""
    processed_ids = {r["id"] for r in results}
    for file_id in all_file_ids:
        if file_id not in processed_ids:
            results.append({"id": file_id, "status": "unknown", "description": "Меню настроек не обнаружено"})


async def finalize_and_send_results(
    webhook_url: str,
    results: list,
    all_file_ids: list = None,
    request=None,
    start_time=None,
):
    """Финализация: supported_models.csv, сортировка, webhook."""
    if all_file_ids:
        _finalize_missing_files(results, all_file_ids)
    if request is not None and start_time is not None:
        try:
            await append_supported_models(start_time, request, results)
        except Exception as e:
            print(f"[{log_ts()}] Ошибка записи supported_models.csv: {e}")
    results.sort(key=lambda x: x["id"])
    await send_webhook(webhook_url, results)


def _add_missing_results(results: list, file_ids: list, status: str, description: str) -> None:
    """Добавить в results отсутствующие file_ids."""
    for fid in file_ids:
        if not any(r["id"] == fid for r in results):
            results.append({"id": fid, "status": status, "description": description})


async def verify_token(authorization: str = Header(...)):
    """Проверка Bearer-токена (env: API_TOKEN)."""
    expected_token = os.getenv("API_TOKEN")
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Неверный формат авторизации. Используйте Bearer <token>"
        )
    token = authorization[7:].strip()
    if token != expected_token:
        raise HTTPException(status_code=401, detail="Неверный токен")
    return True


@router.get("/health")
async def health_check():
    """Health check."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@router.get("/stats")
async def get_stats():
    """Количество принятых запросов /check (счётчик с последнего запуска)."""
    return {"requests_total": _requests_total}


@router.post("/test-webhook")
async def test_webhook_receive(request: Request):
    """Приём тестовых результатов (JSON-массив)."""
    global _last_test_result
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = []
    if not isinstance(body, list):
        body = [body] if body is not None else []
    _last_test_result = body
    return {"ok": True}


@router.get("/test-result")
async def test_result_get():
    """Последний результат теста (после /test-webhook)."""
    global _last_test_result
    result = _last_test_result
    _last_test_result = None
    return result if result is not None else []


@router.post("/check", response_model=CheckResponse, status_code=201)
async def check_device(
    request: CheckRequest,
    authorized: bool = Depends(verify_token)
):
    """Проверка подлинности телефона. Результаты уходят в webhook."""
    start_time = datetime.now()
    
    try:
        if request.model_type != ModelType.phone:
            return await _respond_unsupported(
                start_time,
                request,
                "UNSUPPORTED_DEVICE_TYPE",
                f"Поддерживаются только phone, получено: {request.model_type}",
            )
        manufacturer = request.model_param.manufacturer
        model = (request.model_param.model or "").strip()
        if manufacturer.lower() not in ["apple", "samsung"]:
            return await _respond_unsupported(
                start_time,
                request,
                "UNSUPPORTED_MANUFACTURER",
                f"Поддерживаются только Apple и Samsung, получено: {manufacturer}",
            )
        model_upper = model.upper()
        if "samsung" in manufacturer.lower():
            if "S24" not in model_upper and "S25" not in model_upper:
                return await _respond_unsupported(
                    start_time,
                    request,
                    "UNSUPPORTED_SAMSUNG_MODEL",
                    "Поддерживаются только Samsung Galaxy S24 и S25 серии (S24, S24+, S24 Ultra, S25, S25+, S25 Ultra). Получено: "
                    + (model or "(пусто)"),
                )
        elif manufacturer.lower() == "apple":
            if "IPHONE 15" not in model_upper and "IPHONE 16" not in model_upper and "IPHONE 17" not in model_upper:
                return await _respond_unsupported(
                    start_time,
                    request,
                    "UNSUPPORTED_IPHONE_MODEL",
                    "Поддерживаются только iPhone 15, 16 и 17 серии (15/15 Plus/15 Pro/15 Pro Max, 16/16 Plus/16 Pro/16 Pro Max, 17/17 Air/17 Pro/17 Pro Max). Получено: "
                    + (model or "(пусто)"),
                )
        print(f"[{log_ts()}] Получен запрос: {manufacturer} {model}, {len(request.files)} фото")
        global _requests_total
        _requests_total += 1
        asyncio.create_task(process_check_async(request, request.webhook_url, start_time))
        return CheckResponse(ok=True, result=None)
    except Exception as e:
        print(f"[{log_ts()}] Ошибка обработки запроса: {e}")
        body = CheckResponse(ok=False, result=ErrorResult(
            error_code="INTERNAL_ERROR",
            error_description=str(e)
        ))
        return JSONResponse(status_code=500, content=body.model_dump())


async def process_check_async(request: CheckRequest, webhook_url: str, start_time: datetime):
    """Обработка проверки (лимит CHECK_MAX_CONCURRENT)."""
    async with _check_semaphore:
        global _last_test_result
        _last_test_result = None
        results = []

        try:
            async with aiohttp.ClientSession() as session:
                download_tasks = [
                    download_image(session, file_item.url, file_item.id)
                    for file_item in request.files
                ]
                images_data = await asyncio.gather(*download_tasks, return_exceptions=True)
            valid_images = []
            for idx, result in enumerate(images_data):
                if isinstance(result, Exception):
                    file_id = request.files[idx].id
                    results.append({
                        "id": file_id,
                        "status": "error",
                        "description": f"Ошибка загрузки: {result}"
                    })
                else:
                    valid_images.append(result)
            all_file_ids = [f.id for f in request.files]
            if not valid_images:
                await finalize_and_send_results(webhook_url, results, all_file_ids, request, start_time)
                return
            valid_file_ids = [fid for fid, _ in valid_images]
            menu_photos, all_filter_batches_failed, failed_filter_file_ids = await filter_menu_photos(
                valid_images, request.model_param.manufacturer
            )
            if all_filter_batches_failed:
                _add_missing_results(results, valid_file_ids, "error", "Ошибка фильтрации меню")
                print(f"[{log_ts()}] Анализ завершен за {(datetime.now() - start_time).total_seconds():.1f}с (все батчи фильтра упали)")
                await finalize_and_send_results(webhook_url, results, all_file_ids, request, start_time)
                return
            _add_missing_results(results, failed_filter_file_ids, "error", "Ошибка фильтрации меню")
            if menu_photos:
                analysis_results = await analyze_photos(menu_photos, request.model_param.manufacturer)
                results.extend(analysis_results)
            processing_time = (datetime.now() - start_time).total_seconds()
            print(f"[{log_ts()}] Анализ завершен за {processing_time:.1f}с")
            await finalize_and_send_results(webhook_url, results, all_file_ids, request, start_time)
        except Exception as e:
            print(f"[{log_ts()}] Критическая ошибка обработки: {e}")
            all_file_ids = [f.id for f in request.files]
            _add_missing_results(
                results, all_file_ids,
                "error", f"Ошибка обработки: {str(e)}"
            )
            await finalize_and_send_results(webhook_url, results, all_file_ids, request, start_time)
