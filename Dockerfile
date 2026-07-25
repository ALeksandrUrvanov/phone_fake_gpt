FROM python:3.10-slim

WORKDIR /app

# Python зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY api_server.py .
COPY models.py .
COPY config.py .
COPY api/ ./api/
COPY services/ ./services/
COPY prompts/ ./prompts/

RUN mkdir -p /data

# Переменные окружения
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEFAULT_PORT=8085

EXPOSE 8085

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8085"]
