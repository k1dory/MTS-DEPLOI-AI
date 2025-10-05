# АРХИТЕКТУРА И ИНФРАСТРУКТУРА

**Проект:** MTS Deploy AI v1.0.0
**Дата:** 2025-10-05
**Статус:** Production Ready

---

## СОДЕРЖАНИЕ

1. [Обзор архитектуры](#1-обзор-архитектуры)
2. [Компоненты системы](#2-компоненты-системы)
3. [Инфраструктура](#3-инфраструктура)
4. [Потоки данных](#4-потоки-данных)
5. [Безопасность](#5-безопасность)
6. [Масштабируемость](#6-масштабируемость)

---

## 1. ОБЗОР АРХИТЕКТУРЫ

### 1.1 Высокоуровневая архитектура

```
┌──────────────────────────────────────────────────────────────────────┐
│                         УРОВЕНЬ КЛИЕНТОВ                              │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │    Claude    │  │    Cursor    │  │   Другие     │               │
│  │   Desktop    │  │     IDE      │  │ MCP-клиенты  │               │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘               │
│         │                 │                 │                        │
│         └─────────────────┴─────────────────┘                        │
│                           │                                          │
└───────────────────────────┼──────────────────────────────────────────┘
                            │
                            │ MCP Protocol (stdio/JSON-RPC)
                            │
┌───────────────────────────▼──────────────────────────────────────────┐
│                    УРОВЕНЬ ПРИЛОЖЕНИЯ                                │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │              MTS DEPLOY AI MCP SERVER                       │     │
│  │                (src/mcp_server/server.py)                   │     │
│  └────────────────────────────────────────────────────────────┘     │
│                            │                                         │
│         ┌──────────────────┼──────────────────┐                     │
│         │                  │                  │                     │
│         ▼                  ▼                  ▼                     │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐              │
│  │   8 TOOLS   │   │ LLM CLIENT  │   │   CONFIG    │              │
│  │  (Генераторы│   │   (Claude)  │   │ & UTILS     │              │
│  │   и Анализ) │   └─────────────┘   └─────────────┘              │
│  └─────────────┘                                                    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
                            │
                ┌───────────┼───────────┐
                │           │           │
                ▼           ▼           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    УРОВЕНЬ ИНТЕГРАЦИЙ                                │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  Anthropic   │  │  Kubernetes  │  │  File System │              │
│  │  Claude API  │  │  (kubectl)   │  │   (YAML)     │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.2 Принципы архитектуры

**Модульность:**
- Четкое разделение на инструменты (tools)
- Каждый tool - отдельная ответственность
- Легко добавлять новые tools

**Расширяемость:**
- Plugin-based архитектура для новых компонентов
- Шаблонная система (Jinja2) для гибкой кастомизации
- Конфигурируемые параметры через .env

**Надежность:**
- 58/58 тестов (100% coverage критических функций)
- Валидация всех входных данных
- Graceful error handling

**Производительность:**
- Генерация манифестов: ~1.3 мс на файл
- Full stack (5 файлов): ~6.5 мс
- Все компоненты (23 файла): 30 мс

---

## 2. КОМПОНЕНТЫ СИСТЕМЫ

### 2.1 MCP Server (server.py)

**Назначение:** Главный сервер, реализующий MCP протокол

**8 Инструментов (Tools):**

1. **generate_telecom_manifest** - Генерация манифестов для телеком-компонентов (5G, биллинг)
2. **generate_k8s_manifest** - Базовые K8s манифесты для любых сервисов
3. **generate_cicd_pipeline** - CI/CD конфигурации (GitLab CI, GitHub Actions)
4. **generate_documentation** - Автоматическая документация (Runbooks)
5. **troubleshoot_deployment** - Диагностика проблем деплоя
6. **apply_auto_fix** - Применение автоматических исправлений
7. **analyze_cost** - Анализ и оптимизация стоимости
8. **analyze_security** - Анализ безопасности манифестов

### 2.2 Телеком-компоненты

**Поддерживаемые типы:**

| Компонент | Описание | Ресурсы | Особенности |
|-----------|----------|---------|-------------|
| **5g_upf** | User Plane Function | 4-8 CPU, 8-16Gi | Multus CNI (N3,N4,N6) |
| **5g_amf** | Access Mobility | 2-4 CPU, 4-8Gi | Multus CNI (N1,N2) |
| **5g_smf** | Session Management | 2-4 CPU, 4-8Gi | Multus CNI (N4,N7) |
| **billing** | Биллинг | 1-4 CPU, 2-8Gi | DB, Cache, Queue |
| **rabbitmq** | Message Broker | 1-2 CPU, 2-4Gi | StatefulSet, 100Gi |
| **redis** | Cache | 0.5-2 CPU, 1-4Gi | StatefulSet, 20Gi |

### 2.3 LLM Integration

**Модель:** Claude 3.5 Sonnet (claude-3-5-sonnet-20241022)

**Использование:**
- Генерация манифестов на основе естественного языка
- Анализ проблем deployment
- Генерация рекомендаций по оптимизации
- Создание документации

**Токены:**
- Средний запрос: 500-2000 токенов
- Средний ответ: 1000-3000 токенов
- Стоимость: ~$0.003-0.015 per запрос

---

## 3. ИНФРАСТРУКТУРА

### 3.1 Production Deployment

```
┌────────────────────────────────────────────────────────────────┐
│                      МТС CLOUD KUBERNETES                       │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  NAMESPACE: telecom                                            │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                                                          │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │  │
│  │  │   5G UPF     │  │   5G AMF     │  │   5G SMF     │  │  │
│  │  │  (3 replicas)│  │  (3 replicas)│  │  (3 replicas)│  │  │
│  │  └───────┬──────┘  └───────┬──────┘  └───────┬──────┘  │  │
│  │          │                 │                 │          │  │
│  │          │   Multus CNI (N3, N4, N6, N7)    │          │  │
│  │          └─────────────────┴─────────────────┘          │  │
│  │                                                          │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │  │
│  │  │   Billing    │  │   RabbitMQ   │  │    Redis     │  │  │
│  │  │  (3 replicas)│  │(StatefulSet) │  │(StatefulSet) │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │  │
│  │                                                          │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  STORAGE:                                                      │
│  • fast-ssd (NVMe для 5G, RabbitMQ, Redis)                    │
│  • standard (HDD для логов)                                   │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### 3.2 Networking (5G Interfaces)

**Multus CNI для множественных интерфейсов:**

- **N1** - UE ↔ AMF (control plane)
- **N2** - AMF ↔ gNodeB (control plane)
- **N3** - gNodeB ↔ UPF (user data)
- **N4** - SMF ↔ UPF (control plane)
- **N6** - UPF ↔ Data Network (internet)
- **N7** - SMF ↔ PCF (policy control)

**NetworkAttachmentDefinition:**
```yaml
apiVersion: k8s.cni.cncf.io/v1
kind: NetworkAttachmentDefinition
metadata:
  name: n3-network
spec:
  config: |
    {
      "cniVersion": "0.3.1",
      "type": "macvlan",
      "master": "eth1",
      "ipam": {
        "type": "host-local",
        "subnet": "10.100.0.0/24",
        "rangeStart": "10.100.0.10",
        "rangeEnd": "10.100.0.100"
      }
    }
```

### 3.3 Storage

| Компонент | Size | StorageClass | IOPS |
|-----------|------|--------------|------|
| 5G UPF | 100Gi | fast-ssd | 10,000+ |
| RabbitMQ | 100Gi | fast-ssd | 10,000+ |
| Redis | 20Gi | fast-ssd | 10,000+ |
| Logs | 50Gi | standard | 500 |

### 3.4 Resource Allocation

**Production deployment:**

```yaml
# 5G UPF (высоконагруженный)
resources:
  requests:
    cpu: "4"
    memory: "8Gi"
  limits:
    cpu: "8"
    memory: "16Gi"

# Billing (средняя нагрузка)
resources:
  requests:
    cpu: "1"
    memory: "2Gi"
  limits:
    cpu: "4"
    memory: "8Gi"
```

**Стоимость (МТС Cloud):**
- 5G UPF: 32,400₽/мес
- Billing: 14,400₽/мес
- Redis: 4,200₽/мес
- **Total: ~51,000₽/мес**

---

## 4. ПОТОКИ ДАННЫХ

### 4.1 Генерация манифестов

```
[Пользователь]
    │
    │ "Deploy 5G UPF with HA"
    ▼
[Claude Desktop]
    │
    │ MCP call: generate_telecom_manifest()
    ▼
[MTS Deploy AI]
    │
    ├─► Identify component (5g_upf)
    ├─► Load config
    ├─► Render Jinja2 templates
    ├─► Validate YAML
    ├─► Security check
    └─► Write files to output/
    │
    ▼
[Result: 5 files created]
```

### 4.2 Auto-Troubleshooting

```
[Пользователь]
    │
    │ "Troubleshoot test-upf"
    ▼
[MTS Deploy AI]
    │
    ├─► kubectl get pods
    ├─► kubectl describe deployment
    ├─► kubectl logs
    │
    ├─► Send to Claude API
    │   "Analyze this K8s issue..."
    │
    └─► Receive diagnosis:
        • Problem: ImagePullBackOff
        • Fix: kubectl set image...
    │
    ▼
[Formatted response to user]
```

### 4.3 Cost Optimization

```
[Пользователь]
    │
    │ "Analyze cost"
    ▼
[MTS Deploy AI]
    │
    ├─► Load YAML files
    ├─► Parse resources
    ├─► Calculate cost:
    │   CPU: 2,500₽ × cores
    │   Memory: 1,000₽ × Gi
    │
    ├─► Identify optimizations:
    │   • Overprovisioned resources
    │   • Spot instances eligible
    │   • HPA tuning
    │
    └─► Generate report
    │
    ▼
[Cost report with savings]
```

---

## 5. БЕЗОПАСНОСТЬ

### 5.1 Security Layers

**1. Input Validation**
- RFC 1123 validation для K8s имен
- Injection protection (SQL, command, path)
- Length limits (max 253 chars)

**2. API Security**
- API key валидация
- .env storage (not in code)
- .gitignore protection

**3. Manifest Security**
- No hardcoded secrets
- Placeholder-based credentials
- Security contexts (runAsNonRoot)
- Resource limits

**4. Execution Security**
- Dry-run mode by default
- kubectl command validation
- No destructive operations

### 5.2 Compliance

| Стандарт | Статус |
|----------|--------|
| Pod Security Baseline | ✅ Полное соответствие |
| Pod Security Restricted | ⚠️ Частично (5G требует привилегий) |
| Zero Trust Ready | ✅ Network segmentation |
| GDPR | ✅ Placeholders для sensitive data |

---

## 6. МАСШТАБИРУЕМОСТЬ

### 6.1 HorizontalPodAutoscaler

```yaml
spec:
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        averageUtilization: 70
  behavior:
    scaleUp:
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
```

**Поведение:**
- Scale up: +50% каждые 60s
- Scale down: -10% каждые 60s
- Stabilization: 300s

### 6.2 Multi-Region (Future)

```
Moscow (Primary) ←→ SPb (DR) ←→ Kazan (Edge)
    Full 5G         Full 5G       UPF only
```

**Latency targets:**
- Moscow-SPb: <5ms
- Moscow-Kazan: <15ms

---

## 7. МОНИТОРИНГ

### 7.1 Metrics (Prometheus)

**Auto-annotations:**
```yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "9090"
  prometheus.io/path: "/metrics"
```

**Key metrics:**
- `container_cpu_usage_seconds_total`
- `container_memory_working_set_bytes`
- `kube_pod_status_phase`

### 7.2 Logging (Loki)

**Log format:**
```json
{
  "timestamp": "2025-10-05T10:30:00Z",
  "level": "INFO",
  "service": "billing",
  "message": "Transaction processed"
}
```

---

## ЗАКЛЮЧЕНИЕ

MTS Deploy AI - решение для автоматизации деплоя телеком-инфраструктуры с AI.

---

**Версия:** 1.0.0
**Дата:** 2025-05-10
**Статус:** ✅ Production Ready

