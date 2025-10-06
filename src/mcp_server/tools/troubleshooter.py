"""
Auto-troubleshooting для Kubernetes deployments
Автоматическая диагностика и исправление проблем с помощью LLM
"""

import json
import subprocess
import logging
from typing import Dict, Any, Optional, cast
from anthropic import AsyncAnthropic
from anthropic.types import TextBlock
from ..config import LLMConfig
from ..utils.validation import validate_k8s_resource_name, validate_k8s_namespace

logger = logging.getLogger(__name__)

# Whitelist разрешенных kubectl команд для безопасности
ALLOWED_KUBECTL_COMMANDS = [
    "get",
    "describe",
    "patch",
    "scale",
    "rollout",
    "restart",
    "delete",
    "apply",
    "edit"
]


class TroubleshooterTool:
    """Автоматическая диагностика и исправление deployment проблем"""

    def __init__(self, claude_client: AsyncAnthropic):
        self.llm = claude_client
        self.model = LLMConfig.MODEL
        self.max_tokens = LLMConfig.TOKENS_ANALYSIS

    def _validate_kubectl_command(self, command: str) -> bool:
        """
        Валидирует kubectl команду для предотвращения command injection

        Args:
            command: Команда для валидации

        Returns:
            True если команда безопасна

        Raises:
            ValueError: Если команда не прошла валидацию
        """
        parts = command.split()

        if len(parts) < 2:
            raise ValueError("Invalid command format: too few arguments")

        if parts[0] != "kubectl":
            raise ValueError(f"Only kubectl commands allowed, got: {parts[0]}")

        kubectl_action = parts[1]
        if kubectl_action not in ALLOWED_KUBECTL_COMMANDS:
            raise ValueError(
                f"kubectl command '{kubectl_action}' not whitelisted. "
                f"Allowed: {', '.join(ALLOWED_KUBECTL_COMMANDS)}"
            )

        # Дополнительная проверка на опасные флаги
        dangerous_flags = ["--insecure", "--token=", "--certificate-authority="]
        for flag in dangerous_flags:
            if any(flag in part for part in parts):
                raise ValueError(f"Dangerous flag detected: {flag}")

        logger.info(f"Command validated: {command}")
        return True

    async def diagnose_deployment(
        self,
        namespace: str,
        deployment_name: str
    ) -> Dict[str, Any]:
        """
        Диагностирует проблемы с deployment

        Args:
            namespace: Kubernetes namespace
            deployment_name: Имя deployment для диагностики

        Returns:
            Dict с диагнозом и предложенным решением
        """
        try:
            # Валидация K8s имен (защита от injection)
            namespace = validate_k8s_namespace(namespace)
            deployment_name = validate_k8s_resource_name(deployment_name, "deployment")

            logger.info(f"Начинаем диагностику {namespace}/{deployment_name}")

            # 1. Собрать данные из K8s
            k8s_data = self._collect_k8s_data(namespace, deployment_name)

            if k8s_data.get("error"):
                return {
                    "status": "error",
                    "error": k8s_data["error"]
                }

            # 2. LLM анализ проблемы
            diagnosis = await self._llm_analyze(k8s_data)

            # 3. Сгенерировать fix
            fix = await self._generate_fix(diagnosis, namespace, deployment_name)

            return {
                "status": "analyzed",
                "problem": diagnosis.get("problem", "Unknown"),
                "root_cause": diagnosis.get("root_cause", "Unknown"),
                "severity": diagnosis.get("severity", "medium"),
                "fix_command": fix.get("command", ""),
                "fix_explanation": fix.get("explanation", ""),
                "auto_fixable": fix.get("safe_to_auto_apply", False),
                "k8s_data": k8s_data
            }

        except Exception as e:
            logger.error(f"Ошибка диагностики: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    def _collect_k8s_data(
        self,
        namespace: str,
        deployment_name: str
    ) -> Dict[str, Any]:
        """Собирает данные из Kubernetes"""
        try:
            data = {
                "namespace": namespace,
                "deployment": deployment_name
            }

            # Получить статус deployment
            result = subprocess.run(
                ["kubectl", "get", "deployment", deployment_name, "-n", namespace, "-o", "json"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return {"error": f"Deployment не найден: {result.stderr}"}

            deployment_info = json.loads(result.stdout)
            data["deployment_status"] = {
                "replicas": deployment_info["spec"]["replicas"],
                "available": deployment_info["status"].get("availableReplicas", 0),
                "ready": deployment_info["status"].get("readyReplicas", 0),
                "updated": deployment_info["status"].get("updatedReplicas", 0)
            }

            # Получить поды
            result = subprocess.run(
                ["kubectl", "get", "pods", "-n", namespace,
                 "-l", f"app={deployment_name}", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                pods_info = json.loads(result.stdout)
                data["pods"] = []

                for pod in pods_info.get("items", []):
                    pod_name = pod["metadata"]["name"]
                    pod_status = {
                        "name": pod_name,
                        "phase": pod["status"].get("phase", "Unknown"),
                        "conditions": pod["status"].get("conditions", []),
                        "container_statuses": []
                    }

                    # Статусы контейнеров
                    for container in pod["status"].get("containerStatuses", []):
                        pod_status["container_statuses"].append({
                            "name": container["name"],
                            "ready": container.get("ready", False),
                            "state": container.get("state", {})
                        })

                    data["pods"].append(pod_status)

                    # Получить логи последнего failing пода
                    if pod["status"].get("phase") != "Running":
                        log_result = subprocess.run(
                            ["kubectl", "logs", pod_name, "-n", namespace,
                             "--tail=50", "--all-containers=true"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if log_result.returncode == 0:
                            pod_status["logs"] = log_result.stdout

            # Получить events
            result = subprocess.run(
                ["kubectl", "get", "events", "-n", namespace,
                 "--sort-by=.lastTimestamp", "--field-selector",
                 f"involvedObject.name={deployment_name}"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                data["events"] = result.stdout

            return data

        except subprocess.TimeoutExpired:
            return {"error": "Timeout при сборе данных из K8s"}
        except Exception as e:
            return {"error": f"Ошибка сбора данных: {str(e)}"}

    async def _llm_analyze(self, k8s_data: Dict[str, Any]) -> Dict[str, Any]:
        """LLM анализ проблемы"""

        prompt = f"""Проанализируй проблему с Kubernetes deployment:

Данные:
{json.dumps(k8s_data, indent=2, ensure_ascii=False)}

Определи:
1. problem - краткое описание проблемы (1 предложение)
2. root_cause - корневая причина (технические детали)
3. severity - критичность: low/medium/high/critical

Ответь в JSON формате:
{{
  "problem": "...",
  "root_cause": "...",
  "severity": "..."
}}"""

        try:
            response = await self.llm.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Извлечение текста из ответа
            content = cast(TextBlock, response.content[0]).text

            # Извлечь JSON из ответа
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            diagnosis = json.loads(content)
            logger.info(f"LLM диагноз: {diagnosis.get('problem', 'Unknown')}")

            return diagnosis

        except Exception as e:
            logger.error(f"Ошибка LLM анализа: {e}")
            return {
                "problem": "Не удалось проанализировать проблему",
                "root_cause": str(e),
                "severity": "unknown"
            }

    async def _generate_fix(
        self,
        diagnosis: Dict[str, Any],
        namespace: str,
        deployment_name: str
    ) -> Dict[str, Any]:
        """Генерирует команду для исправления"""

        prompt = f"""На основе диагноза проблемы с Kubernetes deployment, сгенерируй команду для исправления:

Проблема: {diagnosis.get('problem', 'Unknown')}
Причина: {diagnosis.get('root_cause', 'Unknown')}
Namespace: {namespace}
Deployment: {deployment_name}

Сгенерируй:
1. command - kubectl команду для исправления (без sudo, одна строка)
2. explanation - краткое объяснение что делает команда
3. safe_to_auto_apply - true если команду безопасно применить автоматически (только для: scale, restart, patch labels/annotations)

НЕ разрешай auto_apply для:
- delete
- изменения image
- изменения resources
- изменения секретов

Ответ в JSON:
{{
  "command": "kubectl ...",
  "explanation": "...",
  "safe_to_auto_apply": true/false
}}"""

        try:
            response = await self.llm.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Извлечение текста из ответа
            content = cast(TextBlock, response.content[0]).text

            # Извлечь JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            fix = json.loads(content)
            logger.info(f"Сгенерирован fix: {fix.get('command', 'Unknown')}")

            return fix

        except Exception as e:
            logger.error(f"Ошибка генерации fix: {e}")
            return {
                "command": "",
                "explanation": f"Не удалось сгенерировать fix: {str(e)}",
                "safe_to_auto_apply": False
            }

    async def apply_fix(
        self,
        fix_command: str,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Применяет исправление

        Args:
            fix_command: kubectl команда для исправления
            dry_run: если True, только проверка (--dry-run=client)

        Returns:
            Dict с результатом применения
        """
        try:
            # Валидация команды перед выполнением (защита от command injection)
            self._validate_kubectl_command(fix_command)

            # Добавить --dry-run если требуется
            command = fix_command
            if dry_run and "--dry-run" not in command:
                command += " --dry-run=client"

            logger.info(f"Применяем fix: {command}")

            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                return {
                    "status": "success",
                    "output": result.stdout,
                    "dry_run": dry_run
                }
            else:
                return {
                    "status": "error",
                    "error": result.stderr,
                    "dry_run": dry_run
                }

        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "error": "Timeout при применении fix"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
