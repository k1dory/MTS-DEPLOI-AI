# MTS Deploy AI - Docker Image
FROM python:3.11-slim

# Метаданные
LABEL maintainer="MTS Engineering HACK Team"
LABEL description="AI-powered deployment assistant for telecom infrastructure"
LABEL version="1.0.0"

# Рабочая директория
WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код проекта
COPY src/ ./src/
COPY templates/ ./templates/
COPY .env.example ./.env.example

# Создаем директорию для вывода
RUN mkdir -p /app/output

# Создаем непривилегированного пользователя для безопасности
RUN useradd -m -u 1000 -s /bin/bash mtsuser && \
    chown -R mtsuser:mtsuser /app

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Порт для REST API (опционально)
EXPOSE 8000

# Переключаемся на непривилегированного пользователя
USER mtsuser

# Точка входа
CMD ["python", "-m", "src.mcp_server.server"]
