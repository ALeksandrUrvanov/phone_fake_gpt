import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).parent
MSK_TZ = ZoneInfo("Europe/Moscow")
UTC_TZ = ZoneInfo("UTC")


def log_ts() -> str:
    """Текущее время в МСК для логов."""
    return datetime.now(MSK_TZ).strftime("%Y-%m-%d %H:%M:%S MSK")


def created_at_csv_msk(dt: datetime) -> str:
    """Дата/время для колонки created_at в CSV (МСК, без суффикса MSK)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC_TZ).astimezone(MSK_TZ)
    else:
        dt = dt.astimezone(MSK_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


PROMPTS_DIR = BASE_DIR / "prompts"


def _prompt_path(name: str) -> str:
    """Путь к промпту (Docker /app/prompts или локально)."""
    docker_path = f"/app/prompts/{name}.md"
    return docker_path if os.path.exists(docker_path) else str(PROMPTS_DIR / f"{name}.md")


MENU_FILTER_IOS_PROMPT = _prompt_path("menu_filter_ios")
MENU_FILTER_SAMSUNG_PROMPT = _prompt_path("menu_filter_samsung")
IOS_DETECTION_PROMPT = _prompt_path("ios_detection")
SAMSUNG_DETECTION_PROMPT = _prompt_path("samsung_detection")

MAX_LONG_SIDE = 2200
MAX_TOKENS = 8192
TEMPERATURE = 0.3
# Модель OpenRouter по умолчанию — GPT (переопределить через OPENROUTER_MODEL в .env при необходимости)
MODEL_NAME = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.6")
# Reasoning отключён по умолчанию (включить через OPENROUTER_REASONING=1 в .env при необходимости)
OPENROUTER_REASONING = os.getenv("OPENROUTER_REASONING", "0").lower() in ("1", "true", "yes")

BATCH_SIZE = 3
BATCH_DELAY_SEC = int(os.getenv("BATCH_DELAY_SEC", "2"))
CHECK_MAX_CONCURRENT = int(os.getenv("CHECK_MAX_CONCURRENT", "5"))

DOWNLOAD_TIMEOUT = 30
WEBHOOK_TIMEOUT = 30

# CSV в /data (том с хоста): допущенные заявки; все отклонённые (UNSUPPORTED_*) — для будущего обучения
SUPPORTED_MODELS_CSV_PATH = "/data/supported_models.csv"
UNSUPPORTED_MODELS_CSV_PATH = "/data/unsupported_models.csv"
