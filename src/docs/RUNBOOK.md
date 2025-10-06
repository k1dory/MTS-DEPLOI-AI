# Runbook: MTS Deploy AI

**Операционное руководство для деплоя и эксплуатации**

---

## 📋 Содержание

1. [Предварительные требования](#предварительные-требования)
2. [Установка](#установка)
3. [Конфигурация](#конфигурация)
4. [Deployment](#deployment)
5. [Верификация](#верификация)
6. [Мониторинг](#мониторинг)
7. [Troubleshooting](#troubleshooting)
8. [Rollback процедуры](#rollback-процедуры)
9. [Maintenance](#maintenance)

---

## 🔧 Предварительные требования

### Software Requirements

| Компонент | Версия | Назначение |
|-----------|--------|------------|
| Python | 3.11+ | Runtime для MCP сервера |
| pip | 23.0+ | Управление зависимостями |
| Docker | 24.0+ | Контейнеризация (опционально) |
| Git | 2.40+ | Version control |
| kubectl | 1.28+ | Kubernetes CLI (опционально) |

### API Keys

- **ANTHROPIC_API_KEY** - обязателен для LLM генерации
  - Получить: https://console.anthropic.com/
  - Минимальный баланс: $5

### Системные требования

- **OS**: Windows 10/11, Linux, macOS
- **RAM**: Минимум 2GB, рекомендуется 4GB
- **Disk**: 500MB свободного места
- **Network**: Интернет для Anthropic API

---

## 📥 Установка

### ⚡ Быстрая установка (3 команды, < 5 минут)

#### Автоматическая установка

**Windows:**
```bash
git clone <repo-url> && cd mts-deploy-ai && setup.bat
echo ANTHROPIC_API_KEY=sk-ant-your-key >> .env
python test_simple.py
```

**Linux/Mac:**
```bash
git clone <repo-url> && cd mts-deploy-ai && bash setup.sh
echo "ANTHROPIC_API_KEY=sk-ant-your-key" >> .env
python test_simple.py
```

**Ожидаемый вывод:**
```
[SUCCESS] ВСЕ ТЕСТЫ УСПЕШНО ПРОЙДЕНЫ!
```

---

### Вариант 1: Python venv (детальная инструкция)

```bash
# 1. Клонировать репозиторий
git clone <your-gitlab-repo>
cd mts-deploy-ai

# 2. Запустить автоустановку
setup.bat  # Windows
bash setup.sh  # Linux/Mac

# 3. Добавить API ключ
echo ANTHROPIC_API_KEY=sk-ant-key >> .env

# 4. Проверить
python test_simple.py
```

**Что делает setup скрипт:**
1. Создает venv
2. Устанавливает зависимости
3. Создает .env из примера
4. Запускает тесты

### Вариант 2: Docker (рекомендуется для production)

```bash
# 1. Создать .env файл
cp .env.example .env
# Отредактировать .env, добавить ANTHROPIC_API_KEY

# 2. Собрать образ
docker-compose build

# 3. Запустить контейнер
docker-compose up -d

# 4. Проверить статус
docker-compose ps
docker-compose logs -f
```

**Ожидаемый вывод:**
```
mts-deploy-ai  Up  0.0.0.0:8000->8000/tcp
```

---

## ⚙️ Конфигурация

### Шаг 1: Environment Variables

```bash
# Создать .env из шаблона
cp .env.example .env
```

**Редактировать .env:**
```bash
# ОБЯЗАТЕЛЬНО
ANTHROPIC_API_KEY=sk-ant-api03-...  # Ваш API ключ

# ОПЦИОНАЛЬНО
MCP_SERVER_NAME=mts-deploy-ai
MCP_SERVER_VERSION=1.0.0
LOG_LEVEL=INFO
MTS_CLOUD_REGISTRY=registry.mts.ru
MTS_CLOUD_REGION=moscow
```

### Шаг 2: Валидация конфигурации

```bash
# Проверить что .env загружается
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('ANTHROPIC_API_KEY')[:20])"
```

**Ожидаемый вывод:** `sk-ant-api03-...` (первые 20 символов)

### Шаг 3: Claude Desktop интеграция (опционально)

**Для Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**Для macOS:**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Содержимое:**
```json
{
  "mcpServers": {
    "mts-deploy-ai": {
      "command": "python",
      "args": ["-m", "src.mcp_server.server"],
      "cwd": "C:\\Users\\Пользователь\\mts-deploy-ai",
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-api03-..."
      }
    }
  }
}
```

**Применить конфигурацию:**
1. Сохранить файл
2. Перезапустить Claude Desktop
3. Проверить: должны появиться 4 новых tools

---

## 🚀 Deployment

### Pre-deployment Checklist

- [ ] Python зависимости установлены
- [ ] `.env` файл создан и заполнен
- [ ] ANTHROPIC_API_KEY валиден
- [ ] Интернет соединение активно
- [ ] `output/` директория создана (или будет создана автоматически)

### Deployment Steps

#### Локальный запуск (для тестирования)

```bash
# 1. Активировать venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# 2. Запустить MCP сервер
python -m src.mcp_server.server

# Ожидаемый вывод:
# 🚀 Запуск MTS Deploy AI MCP Server...
# 📍 Версия: 1.0.0
# 🔑 API ключ: ✅ установлен
# ✅ Все компоненты инициализированы
# ✅ MCP Server запущен и готов к работе!
```

#### Docker deployment

```bash
# 1. Убедиться что .env создан
ls -la .env

# 2. Запустить
docker-compose up -d

# 3. Проверить логи
docker-compose logs -f mts-deploy-ai

# 4. Health check
curl http://localhost:8000/health  # Если REST API включен
```

#### Production deployment (Kubernetes)

```bash
# 1. Создать namespace
kubectl create namespace mts-deploy-ai

# 2. Создать Secret с API ключом
kubectl create secret generic anthropic-api-key \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-... \
  -n mts-deploy-ai

# 3. Применить манифесты
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# 4. Проверить статус
kubectl get pods -n mts-deploy-ai
kubectl logs -f deployment/mts-deploy-ai -n mts-deploy-ai
```

---

## ✅ Верификация

### Тест 1: Базовая генерация (без LLM)

```bash
python test_basic.py
```

**Ожидаемый результат:**
```
🧪 Тестируем базовую генерацию...
📡 Тест 1: Генерация 5G UPF манифестов
✅ Сгенерировано 5 файлов для UPF:
   • deployment.yaml
   • service.yaml
   • hpa.yaml
   • pvc.yaml
   • network-attachment.yaml

💰 Тест 2: Генерация Billing манифестов
✅ Сгенерировано 4 файлов для Billing

🎉 Все базовые тесты успешно завершены!
```

### Тест 2: LLM генерация

```bash
python test_llm.py
```

**Ожидаемый результат:**
```
🤖 Тестируем Claude API интеграцию...
✅ API ключ найден
✅ Claude клиент успешно инициализирован
📡 Тест 1: Генерация 5G UPF deployment
✅ Генерация завершена успешно!
📁 Манифестов: 5
📄 Документация: Да (4523 символов)
🎉 Все LLM тесты успешно завершены!
```

### Тест 3: MCP интеграция (через Claude Desktop)

**В Claude Desktop:**
```
Промпт: Deploy 5G UPF for Moscow region with high availability
```

**Ожидаемый результат:**
- ✅ Генерация занимает 2-3 минуты
- ✅ Создается 5-6 файлов в `output/`
- ✅ Создается `RUNBOOK.md`
- ✅ Все YAML файлы валидны

### Тест 4: YAML валидация

```bash
# Проверка синтаксиса YAML
python -c "import yaml; yaml.safe_load(open('output/deployment.yaml'))"

# Kubernetes dry-run (если kubectl настроен)
kubectl apply --dry-run=client -f output/

# Ожидаемый вывод:
# deployment.apps/moscow-upf created (dry run)
# service/moscow-upf-service created (dry run)
# ...
```

---

## 📊 Мониторинг

### Logs

**Локальный запуск:**
```bash
# Логи выводятся в stdout
python -m src.mcp_server.server
```

**Docker:**
```bash
# Просмотр логов
docker-compose logs -f

# Последние 100 строк
docker-compose logs --tail=100

# Логи за последние 5 минут
docker-compose logs --since 5m
```

**Kubernetes:**
```bash
# Логи pod
kubectl logs -f deployment/mts-deploy-ai -n mts-deploy-ai

# Логи с меткой времени
kubectl logs --timestamps=true deployment/mts-deploy-ai -n mts-deploy-ai

# Последние 50 строк
kubectl logs --tail=50 deployment/mts-deploy-ai -n mts-deploy-ai
```

### Метрики

**Ключевые метрики для отслеживания:**

| Метрика | Норма | Критично |
|---------|-------|----------|
| Время генерации (LLM) | 2-3 мин | > 5 мин |
| Время генерации (без LLM) | < 5 сек | > 30 сек |
| API errors | < 1% | > 5% |
| Успешные генерации | > 95% | < 80% |

**Prometheus metrics (если настроено):**
```
# Количество генераций
mts_deploy_ai_generations_total

# Latency
mts_deploy_ai_generation_duration_seconds

# Ошибки
mts_deploy_ai_errors_total
```

### Health Checks

**Docker:**
```bash
# Health check статус
docker inspect mts-deploy-ai | grep -A 5 Health
```

**Kubernetes:**
```yaml
livenessProbe:
  exec:
    command: ["python", "-c", "import sys; sys.exit(0)"]
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  exec:
    command: ["python", "-c", "from src.mcp_server import server; sys.exit(0)"]
  initialDelaySeconds: 10
  periodSeconds: 5
```

---

## 🔍 Troubleshooting

### Проблема 1: ModuleNotFoundError: No module named 'mcp'

**Симптомы:**
```
ModuleNotFoundError: No module named 'mcp'
```

**Причина:** Зависимости не установлены

**Решение:**
```bash
pip install -r requirements.txt
```

---

### Проблема 2: ANTHROPIC_API_KEY not set

**Симптомы:**
```
❌ ОШИБКА: ANTHROPIC_API_KEY не установлен!
```

**Причина:** `.env` файл отсутствует или пустой

**Решение:**
```bash
# 1. Создать .env
cp .env.example .env

# 2. Добавить API ключ
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env

# 3. Проверить
cat .env | grep ANTHROPIC_API_KEY
```

---

### Проблема 3: Claude Desktop не видит MCP сервер

**Симптомы:**
- Tools не появляются в Claude Desktop
- Ошибки в логах Claude Desktop

**Диагностика:**
```bash
# 1. Проверить пути в claude_desktop_config.json
cat "%APPDATA%\Claude\claude_desktop_config.json"  # Windows
cat "~/Library/Application Support/Claude/claude_desktop_config.json"  # macOS

# 2. Проверить логи Claude Desktop
# Windows: %APPDATA%\Claude\logs\
# macOS: ~/Library/Logs/Claude/

# 3. Тест локального запуска
python -m src.mcp_server.server
```

**Решение:**
1. Убедиться что `cwd` путь правильный (абсолютный путь)
2. Убедиться что Python в PATH
3. Перезапустить Claude Desktop
4. Проверить что venv активирован (если используется)

---

### Проблема 4: LLM generation timeout

**Симптомы:**
```
TimeoutError: Request to Anthropic API timed out
```

**Причина:** Медленное интернет соединение или высокая нагрузка на API

**Решение:**
```python
# В claude_client.py увеличить timeout
response = await self.client.messages.create(
    model=self.model,
    max_tokens=4000,
    timeout=120.0  # Увеличить с 60 до 120 секунд
)
```

---

### Проблема 5: YAML generation errors

**Симптомы:**
```
yaml.scanner.ScannerError: mapping values are not allowed here
```

**Причина:** LLM сгенерировал некорректный YAML

**Решение:**
1. Проверить `optimized_manifests` в логах
2. Использовать fallback (без LLM оптимизации):
```bash
# Использовать generate_k8s_manifest вместо generate_telecom_manifest
```

3. Или исправить вручную через Edit

---

### Проблема 6: Docker контейнер не запускается

**Симптомы:**
```
Error response from daemon: Container exited with code 1
```

**Диагностика:**
```bash
# Проверить логи
docker-compose logs

# Проверить .env
docker-compose config

# Пересобрать образ
docker-compose build --no-cache
```

**Решение:**
1. Убедиться что `.env` файл существует
2. Проверить ANTHROPIC_API_KEY в `.env`
3. Проверить Docker Compose version (должен быть 2.0+)

---

### Проблема 7: Permission denied (output directory)

**Симптомы:**
```
PermissionError: [Errno 13] Permission denied: './output'
```

**Решение:**
```bash
# Создать директорию с правами
mkdir -p output
chmod 755 output

# Или в Docker
docker-compose run --user $(id -u):$(id -g) mts-deploy-ai
```

---

## 🔄 Rollback процедуры

### Rollback локального деплоя

```bash
# 1. Остановить сервер (Ctrl+C)

# 2. Откатить на предыдущую версию
git log --oneline  # Найти предыдущий commit
git checkout <commit-hash>

# 3. Переустановить зависимости (если изменились)
pip install -r requirements.txt

# 4. Перезапустить
python -m src.mcp_server.server
```

### Rollback Docker деплоя

```bash
# 1. Остановить текущий контейнер
docker-compose down

# 2. Откатить на предыдущий образ
docker images | grep mts-deploy-ai  # Найти предыдущий tag
docker tag mts-deploy-ai:previous mts-deploy-ai:latest

# 3. Перезапустить
docker-compose up -d
```

### Rollback Kubernetes деплоя

```bash
# 1. Проверить историю деплоев
kubectl rollout history deployment/mts-deploy-ai -n mts-deploy-ai

# 2. Откатить на предыдущую версию
kubectl rollout undo deployment/mts-deploy-ai -n mts-deploy-ai

# 3. Откатить на конкретную ревизию
kubectl rollout undo deployment/mts-deploy-ai --to-revision=2 -n mts-deploy-ai

# 4. Проверить статус
kubectl rollout status deployment/mts-deploy-ai -n mts-deploy-ai
```

---

## 🛠️ Maintenance

### Регулярные задачи

#### Ежедневно
- Проверка логов на ошибки
- Мониторинг API usage Anthropic
- Проверка disk space (output/)

#### Еженедельно
- Обновление зависимостей (pip)
- Очистка старых output/ файлов
- Backup конфигураций

#### Ежемесячно
- Обновление Python packages
- Security scan (Trivy)
- Performance review

### Обновление зависимостей

```bash
# 1. Проверить устаревшие пакеты
pip list --outdated

# 2. Обновить requirements.txt
pip install --upgrade -r requirements.txt
pip freeze > requirements.txt

# 3. Тестирование после обновления
python test_basic.py
python test_llm.py
```

### Очистка output директории

```bash
# Удалить файлы старше 7 дней
find output/ -type f -mtime +7 -delete

# Или через скрипт
python -c "
import os, time, shutil
for item in os.listdir('output'):
    path = os.path.join('output', item)
    if time.time() - os.path.getmtime(path) > 7*86400:
        os.remove(path)
"
```

### Backup

```bash
# Backup конфигураций
tar -czf backup-$(date +%Y%m%d).tar.gz \
  .env \
  templates/ \
  docs/ \
  examples/

# Backup в S3 (опционально)
aws s3 cp backup-$(date +%Y%m%d).tar.gz s3://mts-backups/
```

---

## 📞 Контакты и эскалация

### Уровни поддержки

| Level | Тип проблемы | Ответственный |
|-------|--------------|---------------|
| L1 | Установка, базовые вопросы | DevOps team |
| L2 | Конфигурация, troubleshooting | Backend team |
| L3 | LLM issues, архитектура | ML/AI team |

### Полезные ссылки

- **MCP Specification**: https://spec.modelcontextprotocol.io/
- **Anthropic Docs**: https://docs.anthropic.com/
- **Kubernetes Docs**: https://kubernetes.io/docs/
- **Project GitLab**: <your-repo-url>

---

## 📈 Performance Tuning

### Оптимизация LLM вызовов

```python
# В claude_client.py

# 1. Уменьшить max_tokens для более быстрых ответов
max_tokens=2000  # вместо 4000

# 2. Увеличить temperature для более креативных ответов
temperature=0.5  # вместо 0.3

# 3. Использовать кэширование промптов (если доступно)
```

### Оптимизация генерации

```python
# Параллельная оптимизация манифестов
import asyncio

tasks = [
    self._optimize_manifest(content, prompt, component_type)
    for filename, content in manifests.items()
]
optimized = await asyncio.gather(*tasks)
```

---

**Runbook версия 1.0.0 | Последнее обновление: 2025-10-04** 📋
