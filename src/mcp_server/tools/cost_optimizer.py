"""
Cost Optimization Engine для K8s манифестов
Анализирует и оптимизирует стоимость deployment через LLM
"""

import json
import logging
from typing import Dict, Any, List, Optional, cast
from anthropic import AsyncAnthropic
from anthropic.types import TextBlock
import yaml

from ..config import LLMConfig

logger = logging.getLogger(__name__)


class CostOptimizer:
    """Оптимизация стоимости K8s deployments"""

    def __init__(self, claude_client: AsyncAnthropic):
        self.llm = claude_client
        self.model = LLMConfig.MODEL

        # Стоимость ресурсов МТС Cloud (приблизительно, руб/месяц)
        self.pricing = {
            "cpu_core": 1500,  # руб/месяц за 1 core
            "memory_gb": 600,  # руб/месяц за 1GB RAM
            "storage_gb": 50,  # руб/месяц за 1GB storage
            "spot_discount": 0.65  # 65% от обычной цены для Spot
        }

    async def analyze_costs(
        self,
        manifests: Dict[str, str],
        cluster_type: str = "production"
    ) -> Dict[str, Any]:
        """
        Анализирует стоимость манифестов и предлагает оптимизации

        Args:
            manifests: Словарь YAML манифестов
            cluster_type: Тип кластера (production, staging, development)

        Returns:
            Dict с анализом стоимости и рекомендациями
        """
        try:
            logger.info(f"Analyzing costs for {cluster_type} cluster")

            # 1. Рассчитать текущую стоимость
            current_cost = self._calculate_current_cost(manifests)

            # 2. LLM анализ для оптимизации
            optimization = await self._llm_optimize(manifests, cluster_type, current_cost)

            # 3. Применить оптимизации
            optimized_manifests = self._apply_optimizations(manifests, optimization)

            # 4. Рассчитать новую стоимость
            optimized_cost = self._calculate_current_cost(optimized_manifests)

            # 5. Формирование отчёта
            return {
                "status": "analyzed",
                "current_cost_monthly": current_cost,
                "optimized_cost_monthly": optimized_cost,
                "savings_monthly": current_cost - optimized_cost,
                "savings_yearly": (current_cost - optimized_cost) * 12,
                "savings_percentage": round(((current_cost - optimized_cost) / current_cost * 100), 1) if current_cost > 0 else 0,
                "optimizations": optimization.get("changes", []),
                "optimized_manifests": optimized_manifests,
                "recommendations": optimization.get("recommendations", [])
            }

        except Exception as e:
            logger.error(f"Cost analysis failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    def _calculate_current_cost(self, manifests: Dict[str, str]) -> float:
        """Рассчитывает текущую стоимость манифестов"""
        total_cost = 0.0

        for filename, content in manifests.items():
            if not filename.endswith('.yaml'):
                continue

            try:
                docs = list(yaml.safe_load_all(content))

                for doc in docs:
                    if not doc or doc.get("kind") != "Deployment":
                        continue

                    replicas = doc.get("spec", {}).get("replicas", 1)
                    containers = doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])

                    for container in containers:
                        resources = container.get("resources", {}).get("requests", {})

                        # CPU cost
                        cpu = resources.get("cpu", "100m")
                        cpu_cores = self._parse_cpu(cpu)
                        total_cost += cpu_cores * self.pricing["cpu_core"] * replicas

                        # Memory cost
                        memory = resources.get("memory", "128Mi")
                        memory_gb = self._parse_memory(memory)
                        total_cost += memory_gb * self.pricing["memory_gb"] * replicas

                    # Storage cost (PVC)
                    if doc.get("kind") == "PersistentVolumeClaim":
                        storage = doc.get("spec", {}).get("resources", {}).get("requests", {}).get("storage", "1Gi")
                        storage_gb = self._parse_memory(storage)
                        total_cost += storage_gb * self.pricing["storage_gb"]

            except Exception as e:
                logger.warning(f"Failed to parse {filename} for cost calculation: {e}")
                continue

        return round(total_cost, 2)

    def _parse_cpu(self, cpu_str: str) -> float:
        """Парсит CPU строку в cores (1000m = 1 core)"""
        if cpu_str.endswith('m'):
            return float(cpu_str[:-1]) / 1000
        return float(cpu_str)

    def _parse_memory(self, mem_str: str) -> float:
        """Парсит memory строку в GB"""
        multipliers = {
            'Ki': 1 / (1024 * 1024),
            'Mi': 1 / 1024,
            'Gi': 1,
            'Ti': 1024
        }

        for suffix, multiplier in multipliers.items():
            if mem_str.endswith(suffix):
                return float(mem_str[:-2]) * multiplier

        # Default to GB if no suffix
        return float(mem_str)

    async def _llm_optimize(
        self,
        manifests: Dict[str, str],
        cluster_type: str,
        current_cost: float
    ) -> Dict[str, Any]:
        """LLM анализирует и предлагает оптимизации"""

        # Извлечь ключевую информацию из манифестов
        summary = self._summarize_manifests(manifests)

        prompt = f"""Ты эксперт по оптимизации стоимости Kubernetes deployments с глубокими знаниями телеком-инфраструктуры и FinOps best practices.

ТЕКУЩИЕ МАНИФЕСТЫ ({cluster_type} environment):
{json.dumps(summary, indent=2, ensure_ascii=False)}

ТЕКУЩАЯ СТОИМОСТЬ: {current_cost} руб/месяц

ЗАДАЧА: Оптимизировать стоимость с учётом типа кластера И СОХРАНЕНИЕМ КРИТИЧНЫХ ПАРАМЕТРОВ для телекома.

ПРАВИЛА ОПТИМИЗАЦИИ ПО ОКРУЖЕНИЮ:

**Production (критично для бизнеса):**
- ❌ НЕ снижать надёжность
- ✅ Minimum 3 replicas для critical services (5G UPF, AMF, SMF, Billing)
- ✅ Сохранить fast-ssd для latency-sensitive (UPF)
- ✅ Сохранить CPU/Memory для high-throughput компонентов
- ✅ Можно: HPA для elastic scaling, rightsizing если overprovisioned на 50%+

**Staging (тестовое окружение):**
- ✅ Уменьшить replicas до 2 (но НЕ до 1 для HA тестирования)
- ✅ Снизить CPU/Memory на 30-50%
- ✅ Можно использовать standard storage вместо fast-ssd
- ✅ Spot instances для non-critical компонентов (скидка 35%)

**Development:**
- ✅ Минимальные resources (но достаточные для работы)
- ✅ 1 replica (HA не требуется)
- ✅ standard или slow-hdd storage
- ✅ Spot instances везде где возможно

ТЕЛЕКОМ-СПЕЦИФИКА (ВАЖНО!):

**5G UPF (User Plane):**
- Production: НЕ трогать CPU/Memory (data plane performance critical)
- Production: НЕ уменьшать replicas ниже 3 (high availability)
- Staging/Dev: Можно снизить до 2 cores, 4Gi memory

**5G AMF/SMF (Control Plane):**
- Production: Min 3 replicas (session management)
- Staging: 2 replicas OK
- Dev: 1 replica OK

**Billing:**
- Production: Min 3 replicas (финансовые данные!)
- НЕ использовать Spot instances (критичность данных)
- Сохранить database resources

ВОЗМОЖНЫЕ ОПТИМИЗАЦИИ:

1. **Rightsizing** - уменьшить overprovisioning:
   - Если utilization <30% → снизить requests на 30-50%
   - Если utilization >80% → УВЕЛИЧИТЬ (bottleneck!)

2. **Replicas optimization**:
   - Production critical: 3 (не трогать)
   - Production non-critical: можно HPA 2-5
   - Staging: 2
   - Dev: 1

3. **Storage optimization**:
   - Production latency-sensitive: fast-ssd (не трогать)
   - Production logs/backups: standard
   - Staging/Dev: standard

4. **Spot instances** (только non-critical):
   - Development: всё на spot
   - Staging: background jobs на spot
   - Production: ТОЛЬКО non-critical workloads

5. **HPA (Horizontal Pod Autoscaler)**:
   - Elastic workloads: CPU-based HPA
   - Min replicas = требования HA
   - Max replicas = cost budget

РАСЧЁТ ЭКОНОМИИ:
- CPU: 1500 руб/core/месяц
- Memory: 600 руб/GB/месяц
- Storage fast-ssd: 50 руб/GB/месяц
- Storage standard: 20 руб/GB/месяц
- Spot discount: -35%

Ответь ТОЛЬКО в JSON формате:
{{
    "changes": [
        {{
            "type": "reduce_cpu|reduce_memory|reduce_replicas|enable_spot|optimize_hpa",
            "target": "deployment_name",
            "from": "текущее значение",
            "to": "новое значение",
            "savings": <число в руб/месяц>,
            "reason": "объяснение"
        }}
    ],
    "recommendations": [
        "дополнительные рекомендации"
    ],
    "total_estimated_savings": <число>
}}"""

        try:
            response = await self.llm.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0.2,  # Консервативно для финансов
                messages=[{"role": "user", "content": prompt}]
            )

            # Извлечение текста из ответа
            content = cast(TextBlock, response.content[0]).text

            # Извлечь JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)
            logger.info(f"LLM proposed {len(result.get('changes', []))} optimizations")

            return result

        except Exception as e:
            logger.error(f"LLM optimization failed: {e}")
            return {
                "changes": [],
                "recommendations": [f"LLM анализ не удался: {str(e)}"],
                "total_estimated_savings": 0
            }

    def _summarize_manifests(self, manifests: Dict[str, str]) -> List[Dict]:
        """Создаёт краткое описание манифестов для LLM"""
        summary = []

        for filename, content in manifests.items():
            if not filename.endswith('.yaml'):
                continue

            try:
                docs = list(yaml.safe_load_all(content))

                for doc in docs:
                    if not doc:
                        continue

                    kind = doc.get("kind", "Unknown")
                    name = doc.get("metadata", {}).get("name", "unnamed")

                    info = {"kind": kind, "name": name}

                    if kind == "Deployment":
                        spec = doc.get("spec", {})
                        info["replicas"] = spec.get("replicas", 1)

                        containers = spec.get("template", {}).get("spec", {}).get("containers", [])
                        if containers:
                            resources = containers[0].get("resources", {}).get("requests", {})
                            info["cpu"] = resources.get("cpu", "N/A")
                            info["memory"] = resources.get("memory", "N/A")

                    summary.append(info)

            except Exception as e:
                logger.warning(f"Failed to summarize {filename}: {e}")
                continue

        return summary

    def _apply_optimizations(
        self,
        manifests: Dict[str, str],
        optimization: Dict[str, Any]
    ) -> Dict[str, str]:
        """Применяет оптимизации к манифестам"""

        optimized = manifests.copy()
        changes = optimization.get("changes", [])

        for change in changes:
            change_type = change.get("type")
            target = change.get("target")
            new_value = change.get("to")

            for filename, content in optimized.items():
                if not filename.endswith('.yaml'):
                    continue

                try:
                    docs = list(yaml.safe_load_all(content))
                    modified = False

                    for doc in docs:
                        if not doc or doc.get("metadata", {}).get("name") != target:
                            continue

                        # Применить изменение
                        if change_type == "reduce_replicas" and doc.get("kind") == "Deployment":
                            doc["spec"]["replicas"] = int(new_value)
                            modified = True

                        elif change_type == "reduce_cpu" and doc.get("kind") == "Deployment":
                            containers = doc["spec"]["template"]["spec"]["containers"]
                            for container in containers:
                                container.setdefault("resources", {}).setdefault("requests", {})["cpu"] = new_value
                            modified = True

                        elif change_type == "reduce_memory" and doc.get("kind") == "Deployment":
                            containers = doc["spec"]["template"]["spec"]["containers"]
                            for container in containers:
                                container.setdefault("resources", {}).setdefault("requests", {})["memory"] = new_value
                            modified = True

                    if modified:
                        # Сохранить обратно в YAML
                        optimized[filename] = yaml.dump_all(docs, default_flow_style=False)

                except Exception as e:
                    logger.warning(f"Failed to apply optimization to {filename}: {e}")
                    continue

        return optimized
