from typing import List, Dict
import aiohttp

from config import WEBHOOK_TIMEOUT, log_ts


async def send_webhook(webhook_url: str, results: List[Dict]) -> None:
    """POST результатов в webhook (ТЗ: массив {id, status, description}). Ошибки только в лог."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=results,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=WEBHOOK_TIMEOUT),
            ) as response:
                if response.status != 200:
                    print(f"[{log_ts()}] Webhook вернул статус {response.status}")
    
    except Exception as e:
        print(f"[{log_ts()}] Ошибка отправки webhook: {e}")
