import logging
import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import uvicorn
from dotenv import load_dotenv

from api.routes import router
from config import log_ts
from services.llm_service import close_client

load_dotenv()


class SkipPathFilter(logging.Filter):
    """Не логировать access-запросы по заданным путям."""
    def __init__(self, paths_to_skip: list):
        super().__init__()
        self.paths_to_skip = paths_to_skip

    def filter(self, record: logging.LogRecord) -> bool:
        return not any(p in (record.getMessage() or "") for p in self.paths_to_skip)


logging.getLogger("uvicorn.access").addFilter(SkipPathFilter(["/test-result"]))

app = FastAPI(title="Phone Fake Detection Service", version="3.0")


def _error_response(status_code: int, error_code: str, error_description: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "result": {"error_code": error_code, "error_description": error_description}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    """422 → 400 в формате ТЗ: {ok, result}."""
    msg = "Ошибка валидации запроса"
    if exc.errors():
        parts = [f"{e.get('loc', [])}: {e.get('msg', '')}" for e in exc.errors()[:3]]
        msg = "; ".join(parts) if parts else msg
    print(f"[{log_ts()}] /check 400: INVALID_REQUEST — {msg}")
    return _error_response(400, "INVALID_REQUEST", msg)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    """401 в формате ТЗ: {ok, result}. Остальные HTTPException — стандартный {detail}."""
    if exc.status_code == 401:
        detail = exc.detail
        if isinstance(detail, list):
            detail = detail[0].get("msg", "Неверный токен") if detail else "Неверный токен"
        return _error_response(401, "UNAUTHORIZED", str(detail))
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(router)


@app.on_event("shutdown")
async def shutdown_event():
    """Graceful shutdown: закрытие ресурсов."""
    print(f"[{log_ts()}] Остановка сервера...")
    await close_client()


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8085"))
    
    print(f"[{log_ts()}] Phone Fake Detection Service запущен")
    print(f"[{log_ts()}] URL: http://{host}:{port}")
    print()
    
    uvicorn.run(app, host=host, port=port)
