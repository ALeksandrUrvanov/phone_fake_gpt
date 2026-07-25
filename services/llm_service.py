import os
import asyncio
from functools import lru_cache
from typing import List, Optional
from openai import AsyncOpenAI

from config import MODEL_NAME, MAX_TOKENS, TEMPERATURE, OPENROUTER_REASONING, log_ts

LLM_RETRY_ATTEMPTS = 3
LLM_RETRY_DELAY_SEC = 5

# Глобальный клиент (singleton)
_client: Optional[AsyncOpenAI] = None


def get_client() -> AsyncOpenAI:
    """Получить глобальный клиент OpenRouter (создаётся один раз)."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            default_headers={
                "HTTP-Referer": "http://phone_fake",
                "X-Title": "True Device",
            },
        )
    return _client


async def close_client() -> None:
    """Закрыть клиент при shutdown приложения."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
        print(f"[{log_ts()}] LLM клиент закрыт")


@lru_cache(maxsize=None)
def load_prompt(prompt_path: str) -> str:
    """Загрузить промпт из .md файла (с кешированием)."""
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read().strip()


_RETRYABLE_PHRASES = ("provider returned error", "failed_precondition", "400", "429", "rate limit")


def _is_retryable_llm_error(e: Exception) -> bool:
    """Провайдерская ошибка — ретраим."""
    msg = str(e).lower()
    return any(p in msg for p in _RETRYABLE_PHRASES)


def _extract_message_text(message) -> str:
    """Извлечь текст из ответа (content, reasoning или reasoning_details)."""
    if message.content:
        return message.content
    if getattr(message, "reasoning", None):
        return message.reasoning
    for detail in getattr(message, "reasoning_details", None) or []:
        if detail.get("type") == "reasoning.summary" and detail.get("summary"):
            return detail["summary"]
    raise Exception("Не удалось извлечь текст из ответа API")


async def call_llm(prompt: str, encoded_images: List[dict],
                   max_tokens: int = MAX_TOKENS,
                   temperature: float = TEMPERATURE) -> str:
    """Вызов LLM (OpenRouter). До 3 ретраев при ошибке провайдера."""
    chat_messages = [{
        "role": "user",
        "content": [{"type": "text", "text": prompt}] + encoded_images
    }]
    kwargs = {
        "model": MODEL_NAME,
        "messages": chat_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if OPENROUTER_REASONING:
        kwargs["extra_body"] = {"reasoning": {"enabled": True}}

    for attempt in range(LLM_RETRY_ATTEMPTS + 1):
        try:
            client = get_client()
            response = await client.chat.completions.create(**kwargs)
            if not response.choices:
                raise Exception("API вернул пустой ответ")
            return _extract_message_text(response.choices[0].message)
        except Exception as e:
            if attempt < LLM_RETRY_ATTEMPTS and _is_retryable_llm_error(e):
                retry_num = attempt + 1
                print(f"[{log_ts()}] Ошибка LLM, ретрай {retry_num}/{LLM_RETRY_ATTEMPTS} через {LLM_RETRY_DELAY_SEC} с: {e}")
                await asyncio.sleep(LLM_RETRY_DELAY_SEC)
            else:
                raise
