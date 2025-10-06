"""
Security Posture Analysis для K8s манифестов
Анализирует безопасность deployment и предлагает улучшения
"""

import json
import logging
from typing import Dict, Any, List, Optional, cast
from anthropic import AsyncAnthropic
from anthropic.types import TextBlock
import yaml

from ..config import LLMConfig

logger = logging.getLogger(__name__)


class SecurityAnalyzer:
    """Анализ безопасности K8s манифестов"""

    def __init__(self, claude_client: AsyncAnthropic):
        self.llm = claude_client
        self.model = LLMConfig.MODEL

    async def analyze_security(
        self,
        manifests: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Анализирует security posture манифестов

        Args:
            manifests: Словарь YAML манифестов

        Returns:
            Dict с security score и рекомендациями
        """
        try:
            logger.info("Starting security analysis")

            # 1. Базовые security checks
            basic_checks = self._run_basic_checks(manifests)

            # 2. LLM глубокий анализ
            llm_analysis = await self._llm_security_analysis(manifests, basic_checks)

            # 3. Генерация security fixes
            fixes = await self._generate_security_fixes(llm_analysis)

            # 4. Расчёт security score
            score = self._calculate_security_score(basic_checks, llm_analysis)

            return {
                "status": "analyzed",
                "security_score": score,
                "grade": self._get_security_grade(score),
                "basic_checks": basic_checks,
                "critical_issues": llm_analysis.get("critical_issues", []),
                "warnings": llm_analysis.get("warnings", []),
                "recommendations": llm_analysis.get("recommendations", []),
                "auto_fixes": fixes,
                "compliance": self._check_compliance(basic_checks)
            }

        except Exception as e:
            logger.error(f"Security analysis failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "security_score": 0
            }

    def _run_basic_checks(self, manifests: Dict[str, str]) -> Dict[str, Any]:
        """Базовые security проверки"""
        checks = {
            "security_context_present": False,
            "run_as_non_root": False,
            "privileged_containers": [],
            "host_network_usage": [],
            "host_path_volumes": [],
            "secrets_in_env": [],
            "capabilities_added": [],
            "resource_limits_set": False,
            "readiness_probes_set": False,
            "liveness_probes_set": False,
            "network_policies_present": False,
            "service_account_set": False,
            "image_pull_policy": [],
            "trusted_registry": []
        }

        for filename, content in manifests.items():
            if not filename.endswith('.yaml'):
                continue

            try:
                docs = list(yaml.safe_load_all(content))

                for doc in docs:
                    if not doc:
                        continue

                    kind = doc.get("kind")
                    name = doc.get("metadata", {}).get("name", "unnamed")

                    if kind == "Deployment":
                        spec = doc.get("spec", {}).get("template", {}).get("spec", {})

                        # Security context
                        pod_security = spec.get("securityContext", {})
                        if pod_security:
                            checks["security_context_present"] = True
                            if pod_security.get("runAsNonRoot"):
                                checks["run_as_non_root"] = True

                        # Containers
                        for container in spec.get("containers", []):
                            container_name = container.get("name", "unnamed")

                            # Privileged
                            if container.get("securityContext", {}).get("privileged"):
                                checks["privileged_containers"].append(f"{name}/{container_name}")

                            # Capabilities
                            caps = container.get("securityContext", {}).get("capabilities", {}).get("add", [])
                            if caps:
                                checks["capabilities_added"].extend([f"{name}/{container_name}: {cap}" for cap in caps])

                            # Resource limits
                            if container.get("resources", {}).get("limits"):
                                checks["resource_limits_set"] = True

                            # Probes
                            if container.get("readinessProbe"):
                                checks["readiness_probes_set"] = True
                            if container.get("livenessProbe"):
                                checks["liveness_probes_set"] = True

                            # Image registry
                            image = container.get("image", "")
                            if image:
                                if "registry.mts.ru" in image or "docker.io/library" in image:
                                    checks["trusted_registry"].append(image)
                                else:
                                    checks["image_pull_policy"].append(f"{name}: {image}")

                            # Secrets in env
                            for env in container.get("env", []):
                                if "SECRET" in env.get("name", "").upper() or "PASSWORD" in env.get("name", "").upper():
                                    if "value" in env:  # Hardcoded secret
                                        checks["secrets_in_env"].append(f"{name}/{container_name}: {env['name']}")

                        # Host network
                        if spec.get("hostNetwork"):
                            checks["host_network_usage"].append(name)

                        # Host path volumes
                        for volume in spec.get("volumes", []):
                            if volume.get("hostPath"):
                                checks["host_path_volumes"].append(f"{name}: {volume['hostPath']['path']}")

                        # Service account
                        if spec.get("serviceAccountName"):
                            checks["service_account_set"] = True

                    elif kind == "NetworkPolicy":
                        checks["network_policies_present"] = True

            except Exception as e:
                logger.warning(f"Failed to check {filename}: {e}")
                continue

        return checks

    async def _llm_security_analysis(
        self,
        manifests: Dict[str, str],
        basic_checks: Dict[str, Any]
    ) -> Dict[str, Any]:
        """LLM глубокий security анализ"""

        # Подготовить summary для LLM
        manifest_summary = self._summarize_for_security(manifests)

        prompt = f"""Ты эксперт по Kubernetes security и телеком-инфраструктуре с глубокими знаниями 5G компонентов и их специфичных security требований.

МАНИФЕСТЫ:
{json.dumps(manifest_summary, indent=2, ensure_ascii=False)}

БАЗОВЫЕ ПРОВЕРКИ:
{json.dumps(basic_checks, indent=2, ensure_ascii=False)}

ГЛУБОКИЙ SECURITY АНАЛИЗ:

1. **Security Contexts** - критично для телекома:
   - runAsNonRoot: true (ОБЯЗАТЕЛЬНО кроме UPF)
   - readOnlyRootFilesystem: true (где возможно)
   - allowPrivilegeEscalation: false
   - Capabilities: drop ALL, add ТОЛЬКО необходимые (NET_ADMIN для 5G)
   - seccompProfile: RuntimeDefault
   - fsGroup: корректно настроен

   **ИСКЛЮЧЕНИЕ для UPF:** может требовать root для DPDK/SR-IOV, но БЕЗ privileged mode!

2. **Secrets Management** - критично для billing/payment:
   - ❌ Hardcoded passwords/API keys в env vars
   - ✅ Kubernetes Secrets (минимум)
   - ✅ HashiCorp Vault (production)
   - ❌ Database credentials в plain text
   - ❌ Private keys в ConfigMaps
   - Проверь: env vars с "PASSWORD", "SECRET", "KEY", "TOKEN"

3. **Network Policies** - zero-trust для 5G:
   - Default deny all
   - Explicit allow для N1-N7 интерфейсов
   - Ingress/Egress правила для каждого компонента
   - Блокировка inter-namespace без разрешения
   - Control plane изоляция от data plane

4. **RBAC** - principle of least privilege:
   - ServiceAccount специфичный для компонента (не default)
   - ClusterRole ТОЛЬКО если нужен (обычно достаточно Role)
   - Минимальные permissions (get/list/watch, НЕ create/update/delete)
   - NO wildcard permissions ("*" - запрещено!)

5. **Image Security**:
   - ✅ Trusted registry: registry.mts.ru
   - ❌ Public Docker Hub (security risk!)
   - ❌ Unknown registries
   - ✅ Specific tags (v1.2.3), НЕ "latest"
   - imagePullPolicy: IfNotPresent или Always для production
   - Image scanning: Trivy, Clair

6. **Resource Limits** - защита от DoS:
   - requests И limits заданы (ОБЯЗАТЕЛЬНО)
   - limits не больше 10x requests (анти-noisy neighbor)
   - Memory limits для предотвращения OOM на ноде
   - CPU limits для fair scheduling
   - ephemeral-storage limits

7. **Pod Security Standards (PSS)**:

   **Baseline** (minimum):
   - No privileged containers
   - No hostNetwork/hostPID/hostIPC
   - No hostPath volumes (кроме исключений для UPF)
   - Capabilities: только безопасные

   **Restricted** (recommended для большинства):
   - runAsNonRoot: true
   - Capabilities: drop ALL
   - seccompProfile: RuntimeDefault
   - Volume types: только безопасные (no hostPath)

   **Privileged** (ТОЛЬКО для UPF с обоснованием):
   - DPDK/SR-IOV требования
   - Документированные исключения
   - Дополнительный аудит

8. **Telekom-Specific Security**:

   **5G Control Plane (AMF/SMF):**
   - Обработка аутентификации → highest security
   - Secrets для NAS keys → vault обязательно
   - Network isolation → strict NetworkPolicy

   **5G User Plane (UPF):**
   - High throughput → может требовать исключений
   - NO privileged mode даже для DPDK
   - Isolate от других workloads

   **Billing:**
   - PCI-DSS compliance
   - Database encryption at rest
   - TLS для всех соединений
   - Audit logging всех транзакций

9. **Additional Checks**:
   - TLS/mTLS для inter-service communication
   - Pod Security Policies (deprecated) или OPA Gatekeeper
   - Vulnerability scanning в CI/CD
   - Runtime security (Falco)
   - Audit logging включён

10. **CVE Risk Assessment**:
    - Base image vulnerabilities
    - Dependency versions
    - Known exploits для компонентов
    - Mitigation strategies

Ответь ТОЛЬКО в JSON:
{{
    "critical_issues": [
        {{
            "issue": "описание проблемы",
            "severity": "critical|high|medium|low",
            "affected": "компонент",
            "cve_risk": "высокий|средний|низкий",
            "mitigation": "как исправить"
        }}
    ],
    "warnings": [
        {{
            "warning": "описание предупреждения",
            "recommendation": "рекомендация"
        }}
    ],
    "recommendations": [
        "общие рекомендации по улучшению security"
    ],
    "compliance_issues": [
        "проблемы с compliance (PCI-DSS, ISO 27001)"
    ]
}}"""

        try:
            response = await self.llm.messages.create(
                model=self.model,
                max_tokens=2500,
                temperature=0.1,  # Очень консервативно для security
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
            logger.info(f"LLM found {len(result.get('critical_issues', []))} critical issues")

            return result

        except Exception as e:
            logger.error(f"LLM security analysis failed: {e}")
            return {
                "critical_issues": [],
                "warnings": [{"warning": f"LLM анализ не удался: {str(e)}"}],
                "recommendations": [],
                "compliance_issues": []
            }

    def _summarize_for_security(self, manifests: Dict[str, str]) -> List[Dict]:
        """Создаёт summary для security анализа"""
        summary = []

        for filename, content in manifests.items():
            if not filename.endswith('.yaml'):
                continue

            try:
                docs = list(yaml.safe_load_all(content))

                for doc in docs:
                    if not doc:
                        continue

                    kind = doc.get("kind")
                    name = doc.get("metadata", {}).get("name", "unnamed")

                    info = {"kind": kind, "name": name}

                    if kind == "Deployment":
                        spec = doc.get("spec", {}).get("template", {}).get("spec", {})

                        info["securityContext"] = spec.get("securityContext", {})
                        info["hostNetwork"] = spec.get("hostNetwork", False)
                        info["serviceAccount"] = spec.get("serviceAccountName", "default")

                        containers = spec.get("containers", [])
                        if containers:
                            c = containers[0]
                            info["containerSecurityContext"] = c.get("securityContext", {})
                            info["image"] = c.get("image", "")
                            info["hasResourceLimits"] = bool(c.get("resources", {}).get("limits"))

                    summary.append(info)

            except Exception as e:
                logger.warning(f"Failed to summarize {filename}: {e}")
                continue

        return summary

    async def _generate_security_fixes(self, llm_analysis: Dict[str, Any]) -> List[Dict]:
        """Генерирует автоматические security fixes"""
        fixes = []

        for issue in llm_analysis.get("critical_issues", []):
            fix = {
                "issue": issue.get("issue"),
                "severity": issue.get("severity"),
                "affected": issue.get("affected"),
                "fix_type": self._determine_fix_type(issue),
                "auto_applicable": self._is_auto_fixable(issue),
                "kubectl_command": self._generate_kubectl_fix(issue)
            }
            fixes.append(fix)

        return fixes

    def _determine_fix_type(self, issue: Dict) -> str:
        """Определяет тип исправления"""
        issue_text = issue.get("issue", "").lower()

        if "security context" in issue_text or "runasnonroot" in issue_text:
            return "add_security_context"
        elif "privileged" in issue_text:
            return "remove_privileged"
        elif "secret" in issue_text or "password" in issue_text:
            return "move_to_secret"
        elif "network policy" in issue_text:
            return "add_network_policy"
        elif "resource limit" in issue_text:
            return "add_resource_limits"
        else:
            return "manual_review_required"

    def _is_auto_fixable(self, issue: Dict) -> bool:
        """Проверяет возможность автофикса"""
        auto_fixable_types = [
            "add_security_context",
            "add_resource_limits",
            "add_network_policy"
        ]
        return self._determine_fix_type(issue) in auto_fixable_types

    def _generate_kubectl_fix(self, issue: Dict) -> Optional[str]:
        """Генерирует kubectl команду для исправления"""
        fix_type = self._determine_fix_type(issue)
        affected = issue.get("affected", "")

        if fix_type == "add_security_context":
            return f"kubectl patch deployment {affected} --type=json -p='[{{\"op\":\"add\",\"path\":\"/spec/template/spec/securityContext\",\"value\":{{\"runAsNonRoot\":true,\"runAsUser\":1000}}}}]'"
        elif fix_type == "remove_privileged":
            return f"kubectl patch deployment {affected} --type=json -p='[{{\"op\":\"remove\",\"path\":\"/spec/template/spec/containers/0/securityContext/privileged\"}}]'"
        elif fix_type == "add_resource_limits":
            return f"kubectl set resources deployment {affected} --limits=cpu=1,memory=1Gi --requests=cpu=100m,memory=128Mi"

        return None

    def _calculate_security_score(
        self,
        basic_checks: Dict[str, Any],
        llm_analysis: Dict[str, Any]
    ) -> int:
        """Рассчитывает security score (0-100)"""
        score = 100

        # Вычитаем за проблемы
        critical_issues = len(llm_analysis.get("critical_issues", []))
        warnings = len(llm_analysis.get("warnings", []))

        score -= critical_issues * 15  # -15 за каждую critical
        score -= warnings * 5  # -5 за каждое warning

        # Вычитаем за отсутствие базовых мер
        if not basic_checks.get("security_context_present"):
            score -= 10
        if not basic_checks.get("run_as_non_root"):
            score -= 10
        if basic_checks.get("privileged_containers"):
            score -= 20
        if basic_checks.get("secrets_in_env"):
            score -= 15
        if not basic_checks.get("resource_limits_set"):
            score -= 10
        if not basic_checks.get("network_policies_present"):
            score -= 10

        return max(0, min(100, score))

    def _get_security_grade(self, score: int) -> str:
        """Переводит score в оценку"""
        if score >= 90:
            return "A (Отлично)"
        elif score >= 75:
            return "B (Хорошо)"
        elif score >= 60:
            return "C (Удовлетворительно)"
        elif score >= 40:
            return "D (Требуется улучшение)"
        else:
            return "F (Критично)"

    def _check_compliance(self, basic_checks: Dict[str, Any]) -> Dict[str, bool]:
        """Проверяет соответствие стандартам"""
        return {
            "pod_security_baseline": (
                basic_checks.get("security_context_present", False) and
                not basic_checks.get("privileged_containers")
            ),
            "pod_security_restricted": (
                basic_checks.get("run_as_non_root", False) and
                basic_checks.get("resource_limits_set", False) and
                not basic_checks.get("host_network_usage")
            ),
            "zero_trust_ready": (
                basic_checks.get("network_policies_present", False) and
                basic_checks.get("service_account_set", False)
            )
        }
