@echo off
REM MTS Deploy AI - Автоматическая установка для Windows
echo ========================================
echo MTS Deploy AI - Установка
echo ========================================

REM 1. Создать venv
echo [1/4] Создание виртуального окружения...
python -m venv venv
if errorlevel 1 (
    echo [ERROR] Не удалось создать venv. Проверьте что Python установлен.
    exit /b 1
)

REM 2. Активировать venv и установить зависимости
echo [2/4] Установка зависимостей...
call venv\Scripts\activate.bat
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Не удалось установить зависимости
    exit /b 1
)

REM 3. Создать .env из примера
echo [3/4] Создание .env файла...
if not exist .env (
    copy .env.example .env
    echo [OK] .env создан. ВАЖНО: Добавьте ваш ANTHROPIC_API_KEY!
) else (
    echo [WARN] .env уже существует, пропускаем
)

REM 4. Запустить тесты
echo [4/4] Запуск тестов...
python test_basic.py
if errorlevel 1 (
    echo [WARN] Тесты завершились с ошибками
) else (
    echo [SUCCESS] Все тесты пройдены!
)

echo.
echo ========================================
echo Установка завершена!
echo ========================================
echo.
echo Следующие шаги:
echo   1. Откройте .env и добавьте ANTHROPIC_API_KEY
echo   2. Запустите: python -m src.mcp_server.server
echo.
echo Или используйте Docker:
echo   docker-compose up -d
echo.
pause
