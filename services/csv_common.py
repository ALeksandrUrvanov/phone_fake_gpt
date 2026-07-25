"""Общие поля для supported_models / unsupported_models CSV (без дублирования парсинга id)."""
from models import CheckRequest


def csv_proposal_id(request: CheckRequest) -> str:
    if not request.files:
        return ""
    return (request.files[0].id.split("_", 1)[0] or "").strip()


def csv_file_id_suffix(composite_id: str) -> str:
    return composite_id.split("_", 1)[-1] if "_" in composite_id else composite_id


def csv_manufacturer_model(request: CheckRequest) -> tuple[str, str]:
    p = request.model_param
    return (p.manufacturer or "").strip(), (p.model or "").strip()
