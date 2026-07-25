from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field


class ModelType(str, Enum):
    """Тип устройства."""
    phone = "phone"
    tablet = "tablet"
    smart_watch = "smart_watch"


class FileItem(BaseModel):
    """Файл для проверки (id, url)."""
    id: str
    url: str


class ModelParam(BaseModel):
    """Производитель и модель устройства."""
    manufacturer: str
    model: str


class CheckRequest(BaseModel):
    """Запрос на проверку (Pignus)."""
    env: str
    webhook_url: str
    model_type: ModelType
    model_param: ModelParam
    files: List[FileItem] = Field(..., min_length=1, max_length=12)


class ErrorResult(BaseModel):
    """Код и описание ошибки."""
    error_code: str
    error_description: str


class CheckResponse(BaseModel):
    """Ответ /check (ok + опциональная ошибка)."""
    ok: bool
    result: Optional[ErrorResult] = None

