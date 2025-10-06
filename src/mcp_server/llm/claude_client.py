"""
Claude API клиент для интеллектуальной генерации конфигураций
Использует LLM для анализа промптов и создания оптимальных манифестов
"""

import json
import logging
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path

try:
    from anthropic import Anthropic, AsyncAnthropic
    from anthropic.types import Message, TextBlock
except ImportError:
    logging.error("anthropic не установлен! Выполните: pip install anthropic")
    Anthropic = None
    AsyncAnthropic = None
    Message = None
    TextBlock = None

from ..tools.telecom_generator import TelecomGenerator, TELECOM_COMPONENTS
from ..config import LLMConfig
from .prompt_contexts import get_full_context, CONTEXT_5G_ARCHITECTURE, CONTEXT_KUBERNETES_BEST_PRACTICES

logger = logging.getLogger(__name__)


# Timeout wrapper для LLM вызовов
async def with_timeout(coro, timeout: float = 30.0):
    """Wrapper для добавления timeout к async операциям"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise RuntimeError(f"LLM request timeout after {timeout}s")


class ClaudeClient:
    """
    Клиент для работы с Claude API
    Генерирует телеком-конфигурации используя LLM
    """

    def __init__(self, api_key: Optional[str] = None):
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY обязателен!")

        if not AsyncAnthropic:
            raise ImportError("Установите anthropic: pip install anthropic")

        self.client = AsyncAnthropic(api_key=api_key)
        self.telecom_gen = TelecomGenerator()
        self.model = LLMConfig.MODEL

    def _extract_code_block(self, content: str, lang: str | None = None) -> str:
        """Извлекает код из markdown блока"""
        if lang and f"```{lang}" in content:
            return content.split(f"```{lang}")[1].split("```")[0].strip()
        elif "```" in content:
            return content.split("```")[1].split("```")[0].strip()
        return content.strip()

    async def generate_telecom_deployment(
        self,
        prompt: str,
        output_dir: str = "./output"
    ) -> Dict[str, Any]:
        """
        Главная функция: генерирует полный деплоймент по промпту

        Args:
            prompt: Описание что нужно задеплоить
            output_dir: Директория для сохранения

        Returns:
            {
                'manifests': {...},
                'documentation': '...',
                'analysis': '...'
            }
        """
        logger.info(f"🤖 Анализ промпта: {prompt}")

        # Шаг 1: Анализ промпта
        analysis = await self._analyze_prompt(prompt)
        logger.info(f"📊 Определен компонент: {analysis.get('component_type')}")

        # Шаг 2: Генерация параметров
        params = await self._generate_parameters(prompt, analysis)
        logger.info(f"⚙️  Параметры: {params.get('service_name')}")

        # Шаг 3: Генерация манифестов (используем шаблоны)
        component_type = analysis.get("component_type", "generic")
        service_name = params.get("service_name", "telecom-service")

        manifests = self.telecom_gen.generate_full_stack(
            component_type=component_type,
            service_name=service_name,
            namespace=params.get("namespace", "telecom")
        )

        # Шаг 4: Оптимизация манифестов через LLM
        optimized_manifests = {}
        for filename, content in manifests.items():
            logger.info(f" Оптимизация {filename}...")
            optimized = await self._optimize_manifest(content, prompt, component_type)
            optimized_manifests[filename] = optimized

        # Шаг 5: Генерация документации
        documentation = await self._generate_documentation(
            component_type=component_type,
            service_name=service_name,
            manifests=optimized_manifests,
            prompt=prompt
        )

        return {
            "manifests": optimized_manifests,
            "documentation": documentation,
            "analysis": json.dumps(analysis, indent=2, ensure_ascii=False)
        }

    async def _analyze_prompt(self, prompt: str) -> Dict[str, Any]:
        """
        LLM анализирует промпт и определяет компонент

        Returns:
            {
                'component_type': '5g_upf',
                'region': 'moscow',
                'requirements': [...],
                'service_name': 'moscow-upf'
            }
        """
        # Получить ПОЛНЫЙ контекст для максимальной точности
        full_context = get_full_context()

        system_prompt = f"""
Ты эксперт по телеком-инфраструктуре МТС и Kubernetes с глубокими знаниями 5G архитектуры.

{full_context}

Доступные телеком-компоненты:
{self._format_components_list()}

Проанализируй запрос пользователя с учётом ВСЕЙ вышеуказанной информации о 5G протоколах, архитектуре и best practices.

Определи:
1. **component_type** - какой компонент нужно задеплоить (5g_upf, 5g_amf, 5g_smf, billing, etc.)
2. **service_name** - имя сервиса (lowercase, через дефис, с регионом если указан)
3. **region** - регион если указан (moscow, spb, ekb, etc.)
4. **namespace** - kubernetes namespace (default: telecom)
5. **network_interfaces** - какие 5G интерфейсы нужны (N1-N7), пустой массив если не 5G
6. **special_requirements** - особые требования:
   - high_throughput (>10Gbps)
   - low_latency (<10ms)
   - high_availability (3+ replicas)
   - stateful (требует StatefulSet)
   - database_required
   - cache_required
   - queue_required
7. **resource_estimate** - оценка ресурсов на основе компонента и требований
8. **security_level** - critical|high|medium|low
9. **node_selector** - требования к нодам (если есть)

Ответь ТОЛЬКО в формате JSON без дополнительного текста.

Пример для "Deploy 5G UPF for Moscow with 10Gbps throughput":
{{
  "component_type": "5g_upf",
  "service_name": "moscow-upf",
  "region": "moscow",
  "namespace": "telecom",
  "network_interfaces": ["n3", "n4", "n6"],
  "special_requirements": ["high_throughput", "high_availability", "low_latency"],
  "resource_estimate": {{
    "cpu": "8",
    "memory": "16Gi",
    "storage": "100Gi",
    "storage_class": "fast-ssd"
  }},
  "security_level": "critical",
  "node_selector": {{
    "mts.ru/node-type": "telecom-workload",
    "mts.ru/zone": "moscow"
  }}
}}
"""

        try:
            response = await with_timeout(
                self.client.messages.create(
                    model=self.model,
                    max_tokens=LLMConfig.TOKENS_ANALYSIS,
                    temperature=LLMConfig.TEMP_BALANCED,
                    system=system_prompt,
                    messages=[{
                        "role": "user",
                        "content": f"Запрос: {prompt}"
                    }]
                ),
                timeout=30.0
            )

            # Безопасное извлечение текста из ответа
            if not response.content:
                raise ValueError("Empty response from Claude API")

            first_block = response.content[0]
            if hasattr(first_block, 'text'):
                content = first_block.text.strip()
            else:
                raise ValueError(f"Unexpected content type: {type(first_block)}")

            # Извлечь JSON из ответа
            content = self._extract_code_block(content, "json")

            analysis = json.loads(content)
            return analysis

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON от LLM: {e}")
            logger.debug(f"Полученный контент: {content[:200] if 'content' in locals() else 'N/A'}")
            # Fallback: простая эвристика
            component_type = self.telecom_gen.identify_component(prompt)
            return {
                "component_type": component_type,
                "service_name": f"{component_type}-service",
                "namespace": "telecom",
                "special_requirements": []
            }
        except Exception as e:
            logger.error(f"Критическая ошибка анализа промпта: {e}", exc_info=True)
            logger.warning("Переключение на fallback режим")
            # Fallback: простая эвристика
            component_type = self.telecom_gen.identify_component(prompt)
            return {
                "component_type": component_type,
                "service_name": f"{component_type}-service",
                "namespace": "telecom",
                "special_requirements": [],
                "error": str(e)
            }

    async def _generate_parameters(
        self,
        prompt: str,
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        LLM генерирует оптимальные параметры для компонента

        Returns:
            {
                'service_name': 'moscow-upf',
                'replicas': 5,
                'namespace': 'telecom',
                'custom_params': {...}
            }
        """
        component_type = analysis.get("component_type", "generic")
        base_config = TELECOM_COMPONENTS.get(component_type, {})

        system_prompt = f"""
Ты эксперт по Kubernetes и телеком-инфраструктуре МТС с глубокими знаниями 5G.

{CONTEXT_5G_ARCHITECTURE}
{CONTEXT_KUBERNETES_BEST_PRACTICES}

Компонент: {component_type}

Базовая конфигурация:
{json.dumps(base_config, indent=2, ensure_ascii=False)}

На основе запроса пользователя и результатов анализа, определи ОПТИМАЛЬНЫЕ параметры с учётом:

1. **replicas** - количество реплик:
   - Critical services (UPF, AMF, SMF, Billing): минимум 3 для HA
   - High load: 5-10 для throughput
   - Development: 1-2 для экономии

2. **namespace** - Kubernetes namespace (default: telecom)

3. **resource_overrides** - корректировка CPU/Memory если базовая конфигурация не подходит:
   - High throughput (>10Gbps): увеличить CPU/Memory
   - Low latency (<10ms): fast-ssd storage
   - Database workload: больше Memory для кэша

4. **special_config** - дополнительные параметры:
   - network_interfaces: для 5G компонентов (N1-N7)
   - node_affinity: для размещения на специализированных нодах
   - tolerations: если нужны tainted nodes
   - priority_class: system-cluster-critical для critical компонентов

5. **hpa_config** - HorizontalPodAutoscaler настройки если нужен autoscaling

Ответь в формате JSON с конкретными значениями, готовыми к применению.
"""

        try:
            response = await with_timeout(
                self.client.messages.create(
                    model=self.model,
                    max_tokens=LLMConfig.TOKENS_PARAMETERS,
                    temperature=LLMConfig.TEMP_BALANCED,
                    system=system_prompt,
                    messages=[{
                        "role": "user",
                        "content": f"Запрос: {prompt}\n\nАнализ: {json.dumps(analysis, ensure_ascii=False)}"
                    }]
                ),
                timeout=30.0
            )

            # Безопасное извлечение текста
            if not response.content:
                raise ValueError("Empty response from Claude API")

            first_block = response.content[0]
            if hasattr(first_block, 'text'):
                content = first_block.text.strip()
            else:
                raise ValueError(f"Unexpected content type: {type(first_block)}")

            # Извлечь JSON
            content = self._extract_code_block(content, "json")

            params = json.loads(content)

            # Добавить service_name из analysis
            params["service_name"] = analysis.get("service_name", "telecom-service")
            params["namespace"] = params.get("namespace", "telecom")

            return params

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON параметров: {e}")
            logger.debug(f"Полученный контент: {content[:200] if 'content' in locals() else 'N/A'}")
            return {
                "service_name": analysis.get("service_name", "telecom-service"),
                "replicas": base_config.get("replicas", 3),
                "namespace": "telecom"
            }
        except Exception as e:
            logger.error(f"Критическая ошибка генерации параметров: {e}", exc_info=True)
            logger.warning(f"Использование базовой конфигурации для {component_type}")
            return {
                "service_name": analysis.get("service_name", "telecom-service"),
                "replicas": base_config.get("replicas", 3),
                "namespace": "telecom",
                "error": str(e)
            }

    async def _optimize_manifest(
        self,
        manifest: str,
        context: str,
        component_type: str
    ) -> str:
        """
        LLM оптимизирует сгенерированный манифест

        Args:
            manifest: YAML манифест
            context: Контекст (оригинальный промпт)
            component_type: Тип компонента

        Returns:
            Оптимизированный YAML
        """
        system_prompt = f"""
Ты эксперт по Kubernetes для телеком-инфраструктуры МТС с глубокими знаниями 5G и cloud-native best practices.

{CONTEXT_KUBERNETES_BEST_PRACTICES}

Компонент: {component_type}
Контекст: {context}

Проанализируй и ОПТИМИЗИРУЙ манифест согласно МТС Cloud стандартам:

1. **Labels** - добавь ОБЯЗАТЕЛЬНЫЕ МТС labels:
   - app: <name>
   - component: <type>
   - tier: control-plane|user-plane|backend
   - mts.ru/team: telecom
   - mts.ru/criticality: critical|high|medium|low
   - version: <semantic-version>

2. **Annotations** - добавь для observability:
   - mts.ru/owner: telecom-team@mts.ru
   - prometheus.io/scrape: "true"
   - prometheus.io/port: "8080"
   - prometheus.io/path: "/metrics"

3. **Security Context** - убедись что:
   - runAsNonRoot: true (кроме UPF)
   - readOnlyRootFilesystem: true (где возможно)
   - capabilities: drop ALL, add только необходимые
   - seccompProfile: RuntimeDefault

4. **Health Checks** - проверь корректность:
   - livenessProbe с правильными intervals
   - readinessProbe для LB
   - startupProbe для медленного старта

5. **Resource Limits** - проверь:
   - requests заданы
   - limits = requests * 1.5
   - Для critical: гарантированный QoS

6. **High Availability** - добавь если critical:
   - PodAntiAffinity для разных нод
   - topologySpreadConstraints

7. **Node Placement** - добавь селекторы:
   - nodeSelector для специализированных нод
   - tolerations если нужны

ВАЖНО:
- Верни ТОЛЬКО валидный YAML без дополнительного текста и markdown блоков
- НЕ УДАЛЯЙ существующие важные настройки (Multus CNI, volumes, env vars)
- СОХРАНИ все комментарии если они есть
- Если манифест уже оптимален - верни его как есть
"""

        try:
            response = await with_timeout(
                self.client.messages.create(
                    model=self.model,
                    max_tokens=LLMConfig.TOKENS_OPTIMIZATION,
                    temperature=LLMConfig.TEMP_DETERMINISTIC,
                    system=system_prompt,
                    messages=[{
                        "role": "user",
                        "content": f"Контекст: {context}\n\nМанифест:\n```yaml\n{manifest}\n```"
                    }]
                ),
                timeout=30.0
            )

            # Безопасное извлечение текста
            if not response.content:
                raise ValueError("Empty response from Claude API")

            first_block = response.content[0]
            if hasattr(first_block, 'text'):
                optimized = first_block.text.strip()
            else:
                raise ValueError(f"Unexpected content type: {type(first_block)}")

            # Извлечь YAML
            optimized = self._extract_code_block(optimized, "yaml")

            return optimized

        except Exception as e:
            logger.warning(f"Ошибка оптимизации манифеста: {e}. Возвращаю оригинал.")
            return manifest

    async def _generate_documentation(
        self,
        component_type: str,
        service_name: str,
        manifests: Dict[str, str],
        prompt: str
    ) -> str:
        """
        LLM генерирует runbook (документацию по деплою)

        Returns:
            Markdown документация
        """
        config = TELECOM_COMPONENTS.get(component_type, {})

        system_prompt = """
Ты технический писатель для МТС, специализирующийся на документации деплоев.

Создай RUNBOOK (пошаговую инструкцию) для production деплоя.

Структура:
1. **Описание компонента** - что делает, зачем нужен
2. **Prerequisites** - что нужно перед деплоем
3. **Deployment Steps** - пошаговые инструкции
4. **Verification** - как проверить что работает
5. **Monitoring** - что мониторить
6. **Troubleshooting** - частые проблемы и решения
7. **Rollback Procedure** - как откатить изменения

Формат: Markdown
Стиль: Четкий, конкретный, для инженеров МТС
"""

        manifests_text = "\n\n".join([
            f"### {filename}\n```yaml\n{content[:500]}...\n```"
            for filename, content in list(manifests.items())[:3]
        ])

        try:
            response = await with_timeout(
                self.client.messages.create(
                    model=self.model,
                    max_tokens=LLMConfig.TOKENS_DOCUMENTATION,
                    temperature=LLMConfig.TEMP_CREATIVE,
                    system=system_prompt,
                    messages=[{
                        "role": "user",
                        "content": f"""
Компонент: {component_type}
Имя сервиса: {service_name}
Описание: {config.get('description', 'N/A')}

Оригинальный запрос: {prompt}

Манифесты (частично):
{manifests_text}

Создай runbook для этого деплоя.
"""
                    }]
                ),
                timeout=30.0
            )

            # Безопасное извлечение текста
            if not response.content:
                raise ValueError("Empty response from Claude API")

            first_block = response.content[0]
            if hasattr(first_block, 'text'):
                docs = first_block.text.strip()
            else:
                raise ValueError(f"Unexpected content type: {type(first_block)}")

            return docs

        except Exception as e:
            logger.error(f"Ошибка генерации документации: {e}")
            return self._generate_fallback_documentation(
                component_type, service_name, config
            )

    async def generate_documentation(
        self,
        component_type: str,
        manifests: Dict[str, str]
    ) -> str:
        """Генерирует документацию (обертка для _generate_documentation)"""
        return await self._generate_documentation(
            component_type=component_type,
            service_name=f"{component_type}-service",
            manifests=manifests,
            prompt=""
        )

    async def generate_cicd(
        self,
        platform: str,
        project_type: str,
        include_security: bool = True
    ) -> str:
        """
        Генерирует CI/CD pipeline используя LLM

        Args:
            platform: 'gitlab' или 'github'
            project_type: Тип проекта
            include_security: Включить security сканирование

        Returns:
            YAML конфигурация
        """
        system_prompt = f"""
Ты DevOps эксперт для МТС.

Создай CI/CD pipeline для {platform} ({project_type} проект).

Требования:
1. Stages: build, test, {'security, ' if include_security else ''}deploy
2. Docker сборка с кэшированием
3. Автотесты с coverage
4. {'Security сканирование (Trivy)' if include_security else ''}
5. Деплой в K8s (staging + production)
6. Интеграция с MTS Cloud registry

Формат: YAML для {platform}
Стиль: Production-ready, с комментариями
"""

        try:
            response = await with_timeout(
                self.client.messages.create(
                    model=self.model,
                    max_tokens=LLMConfig.TOKENS_CICD,
                    temperature=LLMConfig.TEMP_BALANCED,
                    system=system_prompt,
                    messages=[{
                        "role": "user",
                        "content": f"Создай CI/CD для {platform}, проект: {project_type}"
                    }]
                ),
                timeout=30.0
            )

            # Безопасное извлечение текста
            if not response.content:
                raise ValueError("Empty response from Claude API")

            first_block = response.content[0]
            if hasattr(first_block, 'text'):
                config = first_block.text.strip()
            else:
                raise ValueError(f"Unexpected content type: {type(first_block)}")

            # Извлечь YAML
            config = self._extract_code_block(config, "yaml")

            return config

        except Exception as e:
            logger.error(f"Ошибка генерации CI/CD через LLM: {e}", exc_info=True)
            logger.warning("Переключение на шаблонный генератор")
            # Fallback на шаблонный генератор
            try:
                from ..tools.cicd_generator import CICDGenerator
                gen = CICDGenerator()
                return gen.generate_pipeline(platform, project_type, include_security)
            except Exception as fallback_error:
                logger.error(f"Критическая ошибка fallback генератора: {fallback_error}", exc_info=True)
                raise RuntimeError(f"Не удалось сгенерировать CI/CD конфигурацию: {fallback_error}")

    def _format_components_list(self) -> str:
        """Форматирует список компонентов для LLM"""
        lines = []
        for comp_type, config in TELECOM_COMPONENTS.items():
            desc = config.get("description", "")
            lines.append(f"- {comp_type}: {desc}")
        return "\n".join(lines)

    def _generate_fallback_documentation(
        self,
        component_type: str,
        service_name: str,
        config: Dict[str, Any]
    ) -> str:
        """Генерирует базовую документацию (fallback)"""
        return f"""# Runbook: {service_name}

## Описание
Компонент: {component_type}
{config.get('description', 'Телеком-компонент')}

## Prerequisites
- Kubernetes cluster (МТС Cloud)
- kubectl настроен
- Доступ к namespace `telecom`

## Deployment
```bash
# Применить манифесты
kubectl apply -f output/

# Проверить статус
kubectl get pods -n telecom -l app={service_name}
kubectl rollout status deployment/{service_name} -n telecom
```

## Verification
```bash
# Проверить health
kubectl exec -n telecom deployment/{service_name} -- curl localhost:8080/health

# Проверить logs
kubectl logs -n telecom deployment/{service_name} --tail=50
```

## Monitoring
- Prometheus metrics: http://prometheus.mts.ru
- Grafana dashboard: http://grafana.mts.ru

## Rollback
```bash
# Откат к предыдущей версии
kubectl rollout undo deployment/{service_name} -n telecom
```
"""
