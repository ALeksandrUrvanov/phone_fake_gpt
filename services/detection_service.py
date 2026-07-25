import re
import asyncio
from typing import List, Tuple, Dict

from config import (
    MENU_FILTER_IOS_PROMPT,
    MENU_FILTER_SAMSUNG_PROMPT,
    IOS_DETECTION_PROMPT,
    SAMSUNG_DETECTION_PROMPT,
    BATCH_SIZE,
    BATCH_DELAY_SEC,
    log_ts,
)
from services.llm_service import load_prompt, call_llm
from services.image_service import encode_image, create_image_message


def _get_prompt_path(manufacturer: str, kind: str) -> str:
    """Путь к промпту по бренду: kind='menu' | 'detection'. Только Apple и Samsung."""
    m = manufacturer.lower()
    if m == "apple":
        return MENU_FILTER_IOS_PROMPT if kind == "menu" else IOS_DETECTION_PROMPT
    if "samsung" in m:
        return MENU_FILTER_SAMSUNG_PROMPT if kind == "menu" else SAMSUNG_DETECTION_PROMPT
    raise ValueError(f"Неподдерживаемый производитель: {manufacturer}")


def create_batches(items: List, batch_size: int) -> List[List]:
    """Разбить список на батчи заданного размера."""
    batches = []
    for i in range(0, len(items), batch_size):
        batches.append(items[i:i + batch_size])
    return batches


def encode_batch(batch: List[Tuple[str, bytes]]) -> List[dict]:
    """Кодирует батч изображений для LLM."""
    encoded_images = []
    for file_id, image_data in batch:
        encoded_images.append(create_image_message(encode_image(image_data)))
    return encoded_images


async def _run_llm_on_batch(prompt: str, batch: List[Tuple[str, bytes]]) -> str:
    """Кодирует батч и вызывает LLM."""
    return await call_llm(prompt, encode_batch(batch))


def _parse_filter_batch_result(result: str, batch: List[Tuple[str, bytes]]) -> List[Tuple[str, bytes]]:
    """Парсит ответ LLM фильтрации — список фото с меню из батча."""
    menu_photos = []
    lines = result.strip().split("\n")
    for line in lines:
        match = re.search(r"Фото\s*№?\s*(\d+):\s*(МЕНЮ|НЕ_МЕНЮ)", line, re.IGNORECASE)
        if match:
            photo_num = int(match.group(1))
            status = match.group(2).upper()
            if status == "МЕНЮ" and 1 <= photo_num <= len(batch):
                menu_photos.append(batch[photo_num - 1])
    return menu_photos


async def filter_menu_photos(
    images_data: List[Tuple[str, bytes]], manufacturer: str
) -> Tuple[List[Tuple[str, bytes]], bool, List[str]]:
    """Фильтр фото с меню. Выбор промпта по бренду. Возвращает (menu_photos, all_failed, failed_ids)."""
    prompt = load_prompt(_get_prompt_path(manufacturer, "menu"))
    total = len(images_data)
    batches = create_batches(images_data, BATCH_SIZE)
    menu_photos = []
    failed_filter_file_ids: List[str] = []
    failed_batches = 0
    for i, batch in enumerate(batches):
        if i > 0:
            await asyncio.sleep(BATCH_DELAY_SEC)
        try:
            result = await _run_llm_on_batch(prompt, batch)
            menu_photos.extend(_parse_filter_batch_result(result, batch))
        except Exception as e:
            failed_batches += 1
            failed_filter_file_ids.extend([fid for fid, _ in batch])
            print(f"[{log_ts()}] Батч фильтрации {i + 1}/{len(batches)} упал после ретраев: {e}")
    all_batches_failed = 0 < len(batches) == failed_batches
    print(f"[{log_ts()}] Отфильтровано {len(menu_photos)} фото с меню из {total}" + (f", упало батчей: {failed_batches}" if failed_batches else ""))
    return menu_photos, all_batches_failed, failed_filter_file_ids


def parse_detection_result(result: str, photo_num: int) -> Tuple[str, str]:
    """Парсит ответ LLM по одному фото. Возвращает (status, description)."""
    lines = result.strip().split('\n')
    
    for line in lines:
        if f"Фото №{photo_num}" in line or f"№{photo_num}" in line:
            if "Подделка" in line:
                description = line.split("потому что:", 1)[-1].strip() if "потому что:" in line else "Обнаружены признаки подделки"
                return "fake", description
            elif "Оригинал" in line:
                return "original", "Проверка пройдена"
            elif "Не меню" in line:
                return "unknown", "Не является меню поддерживаемого устройства"
    
    return "unknown", "Не удалось определить статус"


async def analyze_photos(menu_photos: List[Tuple[str, bytes]], manufacturer: str) -> List[Dict]:
    """Анализ фото меню на подлинность. Батчи с паузой; при падении батча — status error."""
    prompt = load_prompt(_get_prompt_path(manufacturer, "detection"))
    print(f"[{log_ts()}] Анализ {len(menu_photos)} фото ({manufacturer})")
    batches = create_batches(menu_photos, BATCH_SIZE)
    results = []
    for i, batch in enumerate(batches):
        if i > 0:
            await asyncio.sleep(BATCH_DELAY_SEC)
        try:
            llm_result = await _run_llm_on_batch(prompt, batch)
            for idx, (file_id, _) in enumerate(batch):
                photo_num = idx + 1
                status, description = parse_detection_result(llm_result, photo_num)
                results.append({"id": file_id, "status": status, "description": description})
        except Exception as e:
            for file_id, _ in batch:
                results.append({
                    "id": file_id,
                    "status": "error",
                    "description": "Ошибка анализа",
                })
            print(f"[{log_ts()}] Батч анализа {i + 1}/{len(batches)} упал после ретраев: {e}")
    return results
