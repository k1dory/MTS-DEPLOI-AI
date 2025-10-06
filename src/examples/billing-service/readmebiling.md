# Billing Service Deployment Example

Пример развертывания биллинговой системы с PostgreSQL и Redis.

## Промпт

```
Create billing system with PostgreSQL database, Redis cache, and RabbitMQ queue. 3 replicas for high availability
```

## Сгенерированные файлы

- `deployment.yaml` - Deployment биллингового сервиса
- `service.yaml` - Service
- `hpa.yaml` - HorizontalPodAutoscaler
- `secret.yaml` - Secrets для credentials
- `configmap.yaml` - Конфигурация приложения

## Характеристики

- **Replicas**: 3 (high availability)
- **CPU**: 1-4 cores per pod
- **Memory**: 2-8Gi per pod
- **Dependencies**: PostgreSQL, Redis, RabbitMQ
- **Critical**: Yes

## Deployment

```bash
# 1. Создать namespace
kubectl create namespace telecom

# 2. Обновить secrets (ВАЖНО!)
# Отредактировать secret.yaml и добавить реальные credentials

# 3. Применить манифесты
kubectl apply -f secret.yaml
kubectl apply -f configmap.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f hpa.yaml

# 4. Проверка
kubectl get pods -n telecom -l app=billing
kubectl logs -f deployment/billing -n telecom
```

## Интеграция

### PostgreSQL
```bash
# Connection string
postgresql://billing_user:password@postgres:5432/billing_db
```

### Redis
```bash
# Connection string
redis://redis-service:6379
```

### RabbitMQ
```bash
# Connection string
amqp://billing_user:password@rabbitmq:5672/
```

## Метрики

- Время генерации: 2-3 минуты
- Экономия vs ручной работы: ~95%
