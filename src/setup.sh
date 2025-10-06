#!/bin/bash
# MTS Deploy AI - Автоматическая установка для Linux/Mac

set -e

echo "========================================"
echo "MTS Deploy AI - Установка"
echo "========================================"

# 1. Создать venv
echo "[1/4] Создание виртуального окружения..."
python3 -m venv venv

# 2. Активировать venv и установить зависимости
echo "[2/4] Установка зависимостей..."
source venv/bin/activate
pip install -r requirements.txt

# 3. Создать .env из примера
echo "[3/4] Создание .env файла..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "[OK] .env создан. ВАЖНО: Добавьте ваш ANTHROPIC_API_KEY!"
else
    echo "[WARN] .env уже существует, пропускаем"
fi

# 4. Запустить тесты
echo "[4/4] Запуск тестов..."
if python test_basic.py; then
    echo "[SUCCESS] Все тесты пройдены!"
else
    echo "[WARN] Тесты завершились с ошибками"
fi

echo ""
echo "========================================"
echo "Установка завершена!"
echo "========================================"
echo ""
echo "Следующие шаги:"
echo "  1. Откройте .env и добавьте ANTHROPIC_API_KEY"
echo "  2. Запустите: python -m src.mcp_server.server"
echo ""
echo "Или используйте Docker:"
echo "  docker-compose up -d"
echo ""
