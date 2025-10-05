"""
Генератор CI/CD конфигураций
Поддерживает GitLab CI и GitHub Actions
"""

from typing import Dict


class CICDGenerator:
    """Генератор CI/CD pipeline конфигураций"""

    def generate_pipeline(
        self,
        platform: str,
        project_type: str,
        include_security: bool = True
    ) -> str:
        """
        Генерирует CI/CD конфигурацию

        Args:
            platform: 'gitlab' или 'github'
            project_type: Тип проекта
            include_security: Включить security scanning

        Returns:
            YAML конфигурация
        """
        if platform == "gitlab":
            return self._generate_gitlab_ci(project_type, include_security)
        elif platform == "github":
            return self._generate_github_actions(project_type, include_security)
        else:
            raise ValueError(f"Неизвестная платформа: {platform}")

    def _generate_gitlab_ci(self, project_type: str, include_security: bool) -> str:
        """Генерирует GitLab CI конфигурацию"""

        config = f"""
# MTS Deploy AI - GitLab CI/CD Pipeline
# Автоматически сгенерировано

stages:
  - build
  - test
  - security
  - deploy

variables:
  DOCKER_DRIVER: overlay2
  DOCKER_TLS_CERTDIR: ""
  IMAGE_TAG: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA

# Сборка Docker образа
build:
  stage: build
  image: docker:24.0
  services:
    - docker:24.0-dind
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker build -t $IMAGE_TAG .
    - docker push $IMAGE_TAG
  only:
    - main
    - develop

# Тесты
test:
  stage: test
  image: {self._get_test_image(project_type)}
  script:
    {self._get_test_commands(project_type)}
  coverage: '/TOTAL.*\\s+(\\d+%)/'
"""

        if include_security:
            config += """
# Security сканирование
security:trivy:
  stage: security
  image: aquasec/trivy:latest
  script:
    - trivy image --severity HIGH,CRITICAL $IMAGE_TAG
  allow_failure: false

security:secrets:
  stage: security
  image: trufflesecurity/trufflehog:latest
  script:
    - trufflehog filesystem . --only-verified
  allow_failure: true
"""

        config += """
# Деплой в Kubernetes
deploy:staging:
  stage: deploy
  image: bitnami/kubectl:latest
  script:
    - kubectl config use-context $KUBE_CONTEXT
    - kubectl apply -f output/
    - kubectl rollout status deployment/$APP_NAME -n staging
  environment:
    name: staging
    url: https://staging.mts.ru
  only:
    - develop

deploy:production:
  stage: deploy
  image: bitnami/kubectl:latest
  script:
    - kubectl config use-context $KUBE_CONTEXT
    - kubectl apply -f output/
    - kubectl rollout status deployment/$APP_NAME -n production
  environment:
    name: production
    url: https://production.mts.ru
  when: manual
  only:
    - main
"""

        return config.strip()

    def _generate_github_actions(self, project_type: str, include_security: bool) -> str:
        """Генерирует GitHub Actions конфигурацию"""

        config = f"""
# MTS Deploy AI - GitHub Actions Workflow
# Автоматически сгенерировано

name: CI/CD Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{{{ github.repository }}}}

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3

    - name: Log in to Container Registry
      uses: docker/login-action@v3
      with:
        registry: ${{{{ env.REGISTRY }}}}
        username: ${{{{ github.actor }}}}
        password: ${{{{ secrets.GITHUB_TOKEN }}}}

    - name: Build and push Docker image
      uses: docker/build-push-action@v5
      with:
        context: .
        push: true
        tags: ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}:${{{{ github.sha }}}}
        cache-from: type=gha
        cache-to: type=gha,mode=max

  test:
    runs-on: ubuntu-latest
    needs: build

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Setup {project_type} environment
      {self._get_github_setup_action(project_type)}

    - name: Run tests
      run: |
{self._get_test_commands_indented(project_type)}
"""

        if include_security:
            config += """
  security:
    runs-on: ubuntu-latest
    needs: build
    permissions:
      security-events: write

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Run Trivy vulnerability scanner
      uses: aquasecurity/trivy-action@master
      with:
        image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
        format: 'sarif'
        output: 'trivy-results.sarif'
        severity: 'CRITICAL,HIGH'

    - name: Upload Trivy results to GitHub Security
      uses: github/codeql-action/upload-sarif@v3
      with:
        sarif_file: 'trivy-results.sarif'
"""

        config += """
  deploy:
    runs-on: ubuntu-latest
    needs: [build, test]
    if: github.ref == 'refs/heads/main'

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Configure kubectl
      uses: azure/k8s-set-context@v3
      with:
        kubeconfig: ${{ secrets.KUBE_CONFIG }}

    - name: Deploy to Kubernetes
      run: |
        kubectl apply -f output/
        kubectl rollout status deployment/${{ secrets.APP_NAME }} -n production
"""

        return config.strip()

    def _get_test_image(self, project_type: str) -> str:
        """Возвращает Docker образ для тестов"""
        images = {
            "python": "python:3.11",
            "nodejs": "node:20",
            "golang": "golang:1.21",
            "java": "maven:3.9-openjdk-17",
            "telecom": "python:3.11"
        }
        return images.get(project_type, "python:3.11")

    def _get_test_commands(self, project_type: str) -> str:
        """Возвращает команды для запуска тестов"""
        commands = {
            "python": """    - pip install -r requirements.txt
    - pip install pytest pytest-cov
    - pytest --cov=. --cov-report=term""",
            "nodejs": """    - npm ci
    - npm run test
    - npm run lint""",
            "golang": """    - go mod download
    - go test ./... -v -coverprofile=coverage.out
    - go vet ./...""",
            "java": """    - mvn clean verify
    - mvn test""",
            "telecom": """    - pip install -r requirements.txt
    - pip install pytest
    - pytest tests/"""
        }
        return commands.get(project_type, commands["python"])

    def _get_test_commands_indented(self, project_type: str) -> str:
        """Возвращает команды с отступами для GitHub Actions"""
        commands = self._get_test_commands(project_type)
        lines = commands.split("\n")
        return "\n".join(f"        {line.strip('- ')}" for line in lines if line.strip())

    def _get_github_setup_action(self, project_type: str) -> str:
        """Возвращает GitHub Action для установки окружения"""
        actions = {
            "python": """uses: actions/setup-python@v5
      with:
        python-version: '3.11'""",
            "nodejs": """uses: actions/setup-node@v4
      with:
        node-version: '20'""",
            "golang": """uses: actions/setup-go@v5
      with:
        go-version: '1.21'""",
            "java": """uses: actions/setup-java@v4
      with:
        java-version: '17'
        distribution: 'temurin'""",
            "telecom": """uses: actions/setup-python@v5
      with:
        python-version: '3.11'"""
        }
        return actions.get(project_type, actions["python"])
