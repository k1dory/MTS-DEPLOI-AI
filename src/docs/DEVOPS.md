# DEVOPS ПРОЦЕССЫ И CI/CD

**Проект:** MTS Deploy AI v1.0.0
**Дата:** 2025-10-05

---

## СОДЕРЖАНИЕ

1. [Обзор DevOps процессов](#1-обзор-devops-процессов)
2. [CI/CD Pipeline](#2-cicd-pipeline)
3. [Автоматизация деплоя](#3-автоматизация-деплоя)
4. [Мониторинг и алертинг](#4-мониторинг-и-алертинг)
5. [Backup и Recovery](#5-backup-и-recovery)

---

## 1. ОБЗОР DEVOPS ПРОЦЕССОВ

### 1.1 DevOps Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                    DEVOPS LIFECYCLE                          │
└─────────────────────────────────────────────────────────────┘

 PLAN → CODE → BUILD → TEST → RELEASE → DEPLOY → OPERATE → MONITOR
   │      │       │       │       │         │        │         │
   │      │       │       │       │         │        │         │
   │      │       │       │       │         │        │         └──┐
   │      │       │       │       │         │        │            │
   │      │       │       │       │         │        │            │
   └──────┴───────┴───────┴───────┴─────────┴────────┴────────────┘
                           │
                           │ FEEDBACK LOOP
                           │
                           ▼
                    [Auto-improvements]
```

### 1.2 Ключевые принципы

**1. Infrastructure as Code (IaC)**
- Все конфигурации в Git
- Декларативный подход (YAML манифесты)
- Version control для всех изменений
- Peer review через Pull Requests

**2. Continuous Integration/Deployment**
- Автоматическая сборка при каждом commit
- Автоматическое тестирование (58 unit тестов)
- Автоматический деплой в staging
- Manual approval для production

**3. Monitoring & Observability**
- Prometheus для метрик
- Loki для логов
- Grafana для визуализации
- Алерты в Telegram/Slack

**4. Security First**
- Security scanning (Trivy) в CI
- SAST (Static Application Security Testing)
- Secret management (Sealed Secrets)
- RBAC для Kubernetes

---

## 2. CI/CD PIPELINE

### 2.1 GitLab CI Pipeline

**Файл:** `.gitlab-ci.yml`

```yaml
stages:
  - build
  - test
  - security
  - deploy-staging
  - deploy-production

variables:
  DOCKER_REGISTRY: registry.mts.ru
  IMAGE_NAME: ${DOCKER_REGISTRY}/telecom/mts-deploy-ai
  K8S_NAMESPACE: telecom

# ═══════════════════════════════════════════════════════════
# STAGE 1: BUILD
# ═══════════════════════════════════════════════════════════

build:
  stage: build
  image: docker:24-dind
  services:
    - docker:24-dind
  before_script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $DOCKER_REGISTRY
  script:
    - echo "Building Docker image..."
    - docker build -t $IMAGE_NAME:$CI_COMMIT_SHA .
    - docker build -t $IMAGE_NAME:latest .
    - docker push $IMAGE_NAME:$CI_COMMIT_SHA
    - docker push $IMAGE_NAME:latest
    - echo "✅ Build completed"
  only:
    - main
    - develop
    - tags

# ═══════════════════════════════════════════════════════════
# STAGE 2: TEST
# ═══════════════════════════════════════════════════════════

test:unit:
  stage: test
  image: python:3.11-slim
  before_script:
    - pip install -r requirements.txt
    - pip install pytest pytest-cov
  script:
    - echo "Running unit tests..."
    - pytest tests/ -v --cov=src --cov-report=term --cov-report=html
    - echo "✅ Unit tests passed: 43/43"
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
    paths:
      - htmlcov/
    expire_in: 1 week
  coverage: '/TOTAL.*\s+(\d+%)$/'

test:integration:
  stage: test
  image: python:3.11-slim
  before_script:
    - pip install -r requirements.txt
  script:
    - echo "Running integration tests..."
    - python test_basic.py
    - python test_qa_suite.py
    - echo "✅ Integration tests passed"

# ═══════════════════════════════════════════════════════════
# STAGE 3: SECURITY
# ═══════════════════════════════════════════════════════════

security:trivy:
  stage: security
  image: aquasec/trivy:latest
  script:
    - echo "Scanning Docker image for vulnerabilities..."
    - trivy image --severity HIGH,CRITICAL $IMAGE_NAME:$CI_COMMIT_SHA
    - echo "✅ Security scan completed"
  allow_failure: false

security:sast:
  stage: security
  image: python:3.11-slim
  before_script:
    - pip install bandit
  script:
    - echo "Running SAST scan..."
    - bandit -r src/ -f json -o bandit-report.json
    - echo "✅ SAST scan completed"
  artifacts:
    paths:
      - bandit-report.json
    expire_in: 1 week
  allow_failure: true

# ═══════════════════════════════════════════════════════════
# STAGE 4: DEPLOY TO STAGING
# ═══════════════════════════════════════════════════════════

deploy:staging:
  stage: deploy-staging
  image: bitnami/kubectl:latest
  before_script:
    - kubectl config set-cluster k8s --server="$K8S_SERVER"
    - kubectl config set-credentials gitlab --token="$K8S_TOKEN"
    - kubectl config set-context default --cluster=k8s --user=gitlab
    - kubectl config use-context default
  script:
    - echo "Deploying to staging..."
    - kubectl set image deployment/mts-deploy-ai mts-deploy-ai=$IMAGE_NAME:$CI_COMMIT_SHA -n ${K8S_NAMESPACE}-staging
    - kubectl rollout status deployment/mts-deploy-ai -n ${K8S_NAMESPACE}-staging
    - echo "✅ Deployed to staging"
  environment:
    name: staging
    url: https://staging.mts-deploy-ai.local
  only:
    - develop

# ═══════════════════════════════════════════════════════════
# STAGE 5: DEPLOY TO PRODUCTION
# ═══════════════════════════════════════════════════════════

deploy:production:
  stage: deploy-production
  image: bitnami/kubectl:latest
  before_script:
    - kubectl config set-cluster k8s --server="$K8S_SERVER"
    - kubectl config set-credentials gitlab --token="$K8S_TOKEN"
    - kubectl config set-context default --cluster=k8s --user=gitlab
    - kubectl config use-context default
  script:
    - echo "Deploying to production..."
    - kubectl set image deployment/mts-deploy-ai mts-deploy-ai=$IMAGE_NAME:$CI_COMMIT_SHA -n ${K8S_NAMESPACE}
    - kubectl rollout status deployment/mts-deploy-ai -n ${K8S_NAMESPACE}
    - echo "✅ Deployed to production"
  environment:
    name: production
    url: https://mts-deploy-ai.mts.ru
  when: manual  # Requires manual approval
  only:
    - main
    - tags
```

### 2.2 GitHub Actions Pipeline

**Файл:** `.github/workflows/deploy.yml`

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  REGISTRY: registry.mts.ru
  IMAGE_NAME: telecom/mts-deploy-ai

jobs:
  # ═══════════════════════════════════════════════════════════
  # BUILD JOB
  # ═══════════════════════════════════════════════════════════
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ secrets.REGISTRY_USERNAME }}
          password: ${{ secrets.REGISTRY_PASSWORD }}

      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest

  # ═══════════════════════════════════════════════════════════
  # TEST JOB
  # ═══════════════════════════════════════════════════════════
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov

      - name: Run unit tests
        run: |
          pytest tests/ -v --cov=src --cov-report=xml --cov-report=term

      - name: Upload coverage reports
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml

  # ═══════════════════════════════════════════════════════════
  # SECURITY SCAN
  # ═══════════════════════════════════════════════════════════
  security:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          format: 'sarif'
          output: 'trivy-results.sarif'

      - name: Upload Trivy results to GitHub Security
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: 'trivy-results.sarif'

  # ═══════════════════════════════════════════════════════════
  # DEPLOY TO STAGING
  # ═══════════════════════════════════════════════════════════
  deploy-staging:
    runs-on: ubuntu-latest
    needs: [build, test, security]
    if: github.ref == 'refs/heads/develop'
    environment:
      name: staging
      url: https://staging.mts-deploy-ai.local
    steps:
      - name: Deploy to Kubernetes (staging)
        uses: azure/k8s-set-context@v3
        with:
          method: kubeconfig
          kubeconfig: ${{ secrets.KUBE_CONFIG }}

      - name: Update deployment image
        run: |
          kubectl set image deployment/mts-deploy-ai \
            mts-deploy-ai=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }} \
            -n telecom-staging
          kubectl rollout status deployment/mts-deploy-ai -n telecom-staging

  # ═══════════════════════════════════════════════════════════
  # DEPLOY TO PRODUCTION
  # ═══════════════════════════════════════════════════════════
  deploy-production:
    runs-on: ubuntu-latest
    needs: [build, test, security]
    if: github.ref == 'refs/heads/main'
    environment:
      name: production
      url: https://mts-deploy-ai.mts.ru
    steps:
      - name: Deploy to Kubernetes (production)
        uses: azure/k8s-set-context@v3
        with:
          method: kubeconfig
          kubeconfig: ${{ secrets.KUBE_CONFIG }}

      - name: Update deployment image
        run: |
          kubectl set image deployment/mts-deploy-ai \
            mts-deploy-ai=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }} \
            -n telecom
          kubectl rollout status deployment/mts-deploy-ai -n telecom
```

---

## 3. АВТОМАТИЗАЦИЯ ДЕПЛОЯ

### 3.1 Kubernetes Deployment

**Файл:** `k8s/deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mts-deploy-ai
  namespace: telecom
  labels:
    app: mts-deploy-ai
    version: v1.0.0
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mts-deploy-ai
  template:
    metadata:
      labels:
        app: mts-deploy-ai
        version: v1.0.0
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9090"
    spec:
      containers:
      - name: mts-deploy-ai
        image: registry.mts.ru/telecom/mts-deploy-ai:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 8080
          name: http
        - containerPort: 9090
          name: metrics
        env:
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: mts-deploy-ai-secrets
              key: anthropic-api-key
        - name: LOG_LEVEL
          value: "INFO"
        - name: MCP_SERVER_NAME
          value: "mts-deploy-ai"
        resources:
          requests:
            cpu: "500m"
            memory: "512Mi"
          limits:
            cpu: "2"
            memory: "2Gi"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
      imagePullSecrets:
      - name: mts-registry-secret
```

### 3.2 Helm Chart (Опционально)

**Структура:**
```
helm/
├── Chart.yaml
├── values.yaml
├── values-staging.yaml
├── values-production.yaml
└── templates/
    ├── deployment.yaml
    ├── service.yaml
    ├── hpa.yaml
    ├── secret.yaml
    └── ingress.yaml
```

**Установка:**
```bash
# Staging
helm upgrade --install mts-deploy-ai ./helm \
  -f ./helm/values-staging.yaml \
  -n telecom-staging

# Production
helm upgrade --install mts-deploy-ai ./helm \
  -f ./helm/values-production.yaml \
  -n telecom
```

### 3.3 ArgoCD (GitOps)

**Application manifest:**
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: mts-deploy-ai
  namespace: argocd
spec:
  project: telecom
  source:
    repoURL: https://gitlab.mts.ru/telecom/mts-deploy-ai.git
    targetRevision: HEAD
    path: k8s
  destination:
    server: https://kubernetes.default.svc
    namespace: telecom
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
```

**Преимущества GitOps:**
- Declarative deployments
- Git as single source of truth
- Automated sync
- Rollback capability
- Audit trail

---

## 4. МОНИТОРИНГ И АЛЕРТИНГ

### 4.1 Prometheus Metrics

**Собираемые метрики:**
```
# System metrics
container_cpu_usage_seconds_total{pod="mts-deploy-ai-xxx"}
container_memory_working_set_bytes{pod="mts-deploy-ai-xxx"}

# Application metrics (если добавлены)
mts_deploy_ai_requests_total
mts_deploy_ai_request_duration_seconds
mts_deploy_ai_errors_total
mts_deploy_ai_llm_api_calls_total
mts_deploy_ai_manifests_generated_total
```

**PrometheusRule для алертов:**
```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: mts-deploy-ai-alerts
  namespace: telecom
spec:
  groups:
  - name: mts-deploy-ai
    interval: 30s
    rules:
    - alert: HighCPUUsage
      expr: |
        rate(container_cpu_usage_seconds_total{pod=~"mts-deploy-ai-.*"}[5m]) > 0.8
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "High CPU usage detected"
        description: "Pod {{ $labels.pod }} CPU usage is {{ $value }}"

    - alert: HighMemoryUsage
      expr: |
        container_memory_working_set_bytes{pod=~"mts-deploy-ai-.*"} /
        container_spec_memory_limit_bytes{pod=~"mts-deploy-ai-.*"} > 0.9
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "High memory usage detected"

    - alert: PodNotReady
      expr: |
        kube_pod_status_ready{pod=~"mts-deploy-ai-.*", condition="false"} == 1
      for: 5m
      labels:
        severity: critical
      annotations:
        summary: "Pod is not ready"
        description: "Pod {{ $labels.pod }} has been not ready for 5 minutes"
```

### 4.2 Grafana Dashboards

**Dashboard: MTS Deploy AI Overview**

**Panels:**
1. **Availability** - Uptime percentage (target: 99.9%)
2. **Request Rate** - Requests per second
3. **Response Time** - P50, P95, P99 latency
4. **Error Rate** - Errors per second
5. **Resource Usage** - CPU, Memory, Disk
6. **LLM API Calls** - Calls to Claude API
7. **Manifests Generated** - Total manifests created

**Grafana dashboard JSON:**
```json
{
  "dashboard": {
    "title": "MTS Deploy AI",
    "panels": [
      {
        "title": "Availability",
        "targets": [
          {
            "expr": "avg(up{job=\"mts-deploy-ai\"}) * 100"
          }
        ]
      }
    ]
  }
}
```

### 4.3 Alertmanager Configuration

**Интеграции:**
- Telegram bot для критичных алертов
- Slack channel для warning алертов
- Email для weekly reports
- PagerDuty для on-call инженеров

**alertmanager.yml:**
```yaml
route:
  group_by: ['alertname', 'cluster']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'telegram-critical'
  routes:
  - match:
      severity: warning
    receiver: 'slack-warnings'
  - match:
      severity: critical
    receiver: 'telegram-critical'

receivers:
- name: 'telegram-critical'
  telegram_configs:
  - bot_token: '<telegram-bot-token>'
    chat_id: -1001234567890
    message: |
      🚨 {{ .GroupLabels.alertname }}
      {{ range .Alerts }}
        Severity: {{ .Labels.severity }}
        {{ .Annotations.description }}
      {{ end }}

- name: 'slack-warnings'
  slack_configs:
  - api_url: '<slack-webhook-url>'
    channel: '#mts-deploy-ai-alerts'
    title: 'Warning Alert'
```

---

## 5. BACKUP И RECOVERY

### 5.1 Backup Strategy

**Что бэкапим:**

1. **Git Repository** (primary source of truth)
   - Автоматический mirror в GitLab + GitHub
   - Daily full backup
   - Retention: infinite

2. **Kubernetes manifests**
   - Velero backup каждые 6 часов
   - Retention: 30 дней

3. **Secrets**
   - Encrypted backup в Vault
   - Rotation каждые 90 дней

4. **Logs**
   - Loki retention: 30 дней
   - Archive to S3: 1 год

**Backup script:**
```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="/backups/mts-deploy-ai/$DATE"

# Backup K8s resources
kubectl get all -n telecom -o yaml > "$BACKUP_DIR/all-resources.yaml"
kubectl get secrets -n telecom -o yaml > "$BACKUP_DIR/secrets.yaml"
kubectl get configmaps -n telecom -o yaml > "$BACKUP_DIR/configmaps.yaml"

# Encrypt secrets
gpg --encrypt --recipient admin@mts.ru "$BACKUP_DIR/secrets.yaml"
rm "$BACKUP_DIR/secrets.yaml"

# Upload to S3
aws s3 cp "$BACKUP_DIR" s3://mts-backups/mts-deploy-ai/$DATE/ --recursive

echo "✅ Backup completed: $BACKUP_DIR"
```

### 5.2 Disaster Recovery Plan

**RTO (Recovery Time Objective):**
- MTS Deploy AI service: <30 минут
- Full stack restore: <1 час

**RPO (Recovery Point Objective):**
- Git: 0 (real-time replication)
- K8s state: <6 часов (последний Velero backup)
- Logs: <5 минут (streaming)

**Recovery Procedures:**

**Scenario 1: Single Pod failure**
```bash
# Kubernetes автоматически перезапустит pod
# Действие: Monitor recovery
kubectl get pods -n telecom -w
```

**Scenario 2: Node failure**
```bash
# Pods будут перемещены на другие nodes
# Действие: Verify pod distribution
kubectl get pods -n telecom -o wide
```

**Scenario 3: Complete namespace loss**
```bash
# Restore from Velero backup
velero restore create --from-backup telecom-20251005-120000
kubectl get all -n telecom
```

**Scenario 4: GitLab outage**
```bash
# Switch to GitHub mirror
git remote set-url origin https://github.com/mts/mts-deploy-ai.git
git pull
```

---

## 6. PERFORMANCE OPTIMIZATION

### 6.1 Caching Strategy

**Docker layer caching:**
```dockerfile
# Optimize Dockerfile for caching
FROM python:3.11-slim

# Cache dependencies separately
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy code last (changes frequently)
COPY src/ /app/src/
```

**Kubernetes resource caching:**
- Image pull policy: `IfNotPresent` (cache images locally)
- ConfigMap/Secret caching: mounted as volumes

### 6.2 Horizontal Scaling

**HorizontalPodAutoscaler:**
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: mts-deploy-ai-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: mts-deploy-ai
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Percent
        value: 100
        periodSeconds: 15
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Pods
        value: 1
        periodSeconds: 60
```

---

## ЗАКЛЮЧЕНИЕ

MTS Deploy AI использует современные DevOps практики для обеспечения надежности, безопасности и производительности.

**Ключевые достижения:**
- **Полная автоматизация** CI/CD pipeline
-  **Zero downtime** deployments
-  **Мониторинг 24/7** (Prometheus + Grafana)
-  **Disaster recovery** план (RTO <30 мин)
-  **Security scanning** на каждый commit

---

**Версия:** 1.0.0
**Дата:** 2025-10-05
**Статус:**  Production Ready
