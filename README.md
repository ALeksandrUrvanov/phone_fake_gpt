# Phone Fake Detection

FastAPI-сервис: по фото устройства отбирает кадры меню настроек и через LLM классифицирует original / fake / unknown.

## Stack

- Python, FastAPI, Uvicorn, Pydantic, Pillow, aiohttp, requests
- OpenRouter LLM (default `anthropic/claude-sonnet-4.6`)
- Docker, порт `8085`
- Результат: CSV в `/data` + webhook

## Pipeline

1. `POST /check` (Bearer) — валидация бренда/модели (Apple iPhone 15–17, Samsung S24/S25).
2. Скачивание изображений по URL.
3. LLM-фильтр меню (батчи по 3).
4. LLM-детект original/fake/unknown.
5. CSV-лог + `webhook_url`.

## Run

```bash
pip install -r requirements.txt
export API_TOKEN=... OPENROUTER_API_KEY=...
uvicorn api_server:app --host 0.0.0.0 --port 8085
```

## Config

| Variable | Required | Notes |
|----------|----------|-------|
| `API_TOKEN` | yes | Bearer для `/check` |
| `OPENROUTER_API_KEY` | yes | |
| `OPENROUTER_MODEL` | no | Claude Sonnet 4.6 |
| `OPENROUTER_REASONING` | no | `0/1` |
| `CHECK_MAX_CONCURRENT` | no | `5` |

## Notes

- Обучающие фото и CSV-дампы в репозиторий не входят.
- Промпты: `prompts/*_filter_*.md`, `prompts/*_detection.md`.
