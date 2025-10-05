#!/usr/bin/env python3
"""
MTS Deploy AI - MCP Server
Главный файл MCP сервера для генерации телеком-конфигураций
"""

import asyncio
import os
import sys
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

# Исправление кодировки Windows (должно быть ПЕРЕД логированием!)
try:
    from .utils.encoding_fix import ensure_utf8
    ensure_utf8()
except ImportError:
    pass  # Модуль encoding_fix опционален

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types
except ImportError:
    logger.error("MCP библиотека не установлена! Установите: pip install mcp")
    sys.exit(1)

from dotenv import load_dotenv
import yaml

# Загрузка переменных окружения
load_dotenv()

# Импорт внутренних модулей
try:
    from .llm.claude_client import ClaudeClient
    from .tools.telecom_generator import TelecomGenerator
    from .tools.k8s_generator import K8sManifestGenerator
    from .tools.cicd_generator import CICDGenerator
    from .tools.troubleshooter import TroubleshooterTool
    from .tools.cost_optimizer import CostOptimizer
    from .tools.security_analyzer import SecurityAnalyzer
    from .utils.validation import SecurityValidator, validate_api_key, sanitize_secret_value
    from .config import OutputConfig, UIConfig
except ImportError as e:
    logger.error(f"Ошибка импорта модулей: {e}")
    logger.info("Убедитесь, что все файлы созданы корректно")
    sys.exit(1)


class MTSDeployServer:
    """
    MCP Server для MTS Deploy AI
    Предоставляет tools для генерации K8s манифестов и CI/CD конфигов
    """

    def __init__(self):
        self.server = Server("mts-deploy-ai")
        self.symbols = UIConfig.get_symbols()

        # Валидация .env файла
        logger.info(f"{self.symbols['search']} Проверка конфигурации...")
        env_validation = SecurityValidator.validate_env_file()

        if not env_validation['valid']:
            logger.error(f"{self.symbols['error']} Ошибки в .env файле:")
            for error in env_validation['errors']:
                logger.error(f"   {error}")
            for warning in env_validation['warnings']:
                logger.warning(f"   {warning}")

        # Проверка API ключа с расширенной валидацией
        self.api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
        if validate_api_key(self.api_key):
            # sanitize_secret_value требует non-None строку
            sanitized = sanitize_secret_value(self.api_key) if self.api_key else "N/A"
            logger.info(f"{self.symbols['success']} API ключ валиден: {sanitized}")
        else:
            logger.warning(f"{self.symbols['warning']} ANTHROPIC_API_KEY не установлен или невалиден!")
            logger.warning("   Скопируйте .env.example в .env и добавьте ваш API ключ")
            logger.warning("   Получить ключ: https://console.anthropic.com/")
            self.api_key = None

        # Инициализация компонентов
        try:
            self.claude_client: Optional[ClaudeClient] = ClaudeClient(api_key=self.api_key) if self.api_key else None
            self.telecom_generator = TelecomGenerator()
            self.k8s_generator = K8sManifestGenerator()
            self.cicd_generator = CICDGenerator()
            self.troubleshooter: Optional[TroubleshooterTool] = None
            self.cost_optimizer: Optional[CostOptimizer] = None
            self.security_analyzer: Optional[SecurityAnalyzer] = None

            # Инициализация LLM-based tools только если есть API ключ
            if self.api_key and self.claude_client:
                from anthropic import AsyncAnthropic
                claude_async = AsyncAnthropic(api_key=self.api_key)
                self.troubleshooter = TroubleshooterTool(claude_async)
                self.cost_optimizer = CostOptimizer(claude_async)
                self.security_analyzer = SecurityAnalyzer(claude_async)
                logger.info("✅ Auto-troubleshooter инициализирован")
                logger.info("✅ Cost Optimizer инициализирован")
                logger.info("✅ Security Analyzer инициализирован")

            logger.info("✅ Все компоненты инициализированы")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации компонентов: {e}", exc_info=True)
            raise RuntimeError(f"Не удалось инициализировать сервер: {e}")

        # Регистрация tools
        self._register_tools()

    def _register_tools(self):
        """Регистрация MCP tools"""

        @self.server.list_tools()
        async def list_tools() -> List[types.Tool]:
            """Список доступных tools"""
            return [
                types.Tool(
                    name="generate_telecom_manifest",
                    description=(
                        "Генерирует Kubernetes манифесты для телеком-компонентов "
                        "(5G UPF, AMF, SMF, биллинг, RabbitMQ и др.). "
                        "Использует LLM для интеллектуальной генерации."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": (
                                    "Описание что нужно задеплоить. "
                                    "Например: 'Deploy 5G UPF for Moscow region with 10Gbps throughput'"
                                )
                            },
                            "output_dir": {
                                "type": "string",
                                "description": "Директория для сохранения манифестов (по умолчанию: ./output)",
                                "default": "./output"
                            }
                        },
                        "required": ["prompt"]
                    }
                ),

                types.Tool(
                    name="generate_k8s_manifest",
                    description=(
                        "Генерирует стандартные Kubernetes манифесты "
                        "(Deployment, Service, Ingress, ConfigMap и др.) "
                        "для обычных приложений (не телеком-специфичных)."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "service_name": {
                                "type": "string",
                                "description": "Имя сервиса"
                            },
                            "image": {
                                "type": "string",
                                "description": "Docker образ (например: nginx:latest)"
                            },
                            "replicas": {
                                "type": "integer",
                                "description": "Количество реплик (по умолчанию: 3)",
                                "default": 3
                            },
                            "port": {
                                "type": "integer",
                                "description": "Порт приложения (по умолчанию: 8080)",
                                "default": 8080
                            }
                        },
                        "required": ["service_name", "image"]
                    }
                ),

                types.Tool(
                    name="generate_cicd_pipeline",
                    description=(
                        "Генерирует CI/CD pipeline конфигурацию "
                        "(GitLab CI, GitHub Actions). "
                        "Включает сборку, тесты, security scan и деплой."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "platform": {
                                "type": "string",
                                "enum": ["gitlab", "github"],
                                "description": "CI/CD платформа (gitlab или github)"
                            },
                            "project_type": {
                                "type": "string",
                                "enum": ["python", "nodejs", "golang", "java", "telecom"],
                                "description": "Тип проекта"
                            },
                            "include_security_scan": {
                                "type": "boolean",
                                "description": "Включить security scanning (Trivy)",
                                "default": True
                            }
                        },
                        "required": ["platform", "project_type"]
                    }
                ),

                types.Tool(
                    name="generate_documentation",
                    description=(
                        "Генерирует документацию и runbook для деплоя. "
                        "Включает: описание, prerequisites, deployment steps, "
                        "troubleshooting, rollback procedure."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "component_type": {
                                "type": "string",
                                "description": "Тип компонента (5g_upf, billing, etc.)"
                            },
                            "manifests": {
                                "type": "object",
                                "description": "Сгенерированные манифесты (JSON)"
                            }
                        },
                        "required": ["component_type"]
                    }
                ),

                types.Tool(
                    name="troubleshoot_deployment",
                    description=(
                        "🔍 Auto-troubleshooting для Kubernetes deployments. "
                        "LLM автоматически диагностирует проблемы с deployment, "
                        "анализирует логи, события и предлагает решение."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "namespace": {
                                "type": "string",
                                "description": "Kubernetes namespace"
                            },
                            "deployment_name": {
                                "type": "string",
                                "description": "Имя deployment для диагностики"
                            }
                        },
                        "required": ["namespace", "deployment_name"]
                    }
                ),

                types.Tool(
                    name="apply_auto_fix",
                    description=(
                        "🔧 Применяет автоматическое исправление для deployment проблемы. "
                        "Выполняет kubectl команду для исправления (с опцией dry-run)."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "fix_command": {
                                "type": "string",
                                "description": "kubectl команда для исправления"
                            },
                            "dry_run": {
                                "type": "boolean",
                                "description": "Режим dry-run (только проверка, без реального применения)",
                                "default": True
                            }
                        },
                        "required": ["fix_command"]
                    }
                ),

                types.Tool(
                    name="analyze_cost",
                    description=(
                        "💰 Анализирует стоимость K8s манифестов и предлагает оптимизации. "
                        "Рассчитывает текущую и оптимизированную стоимость deployment, "
                        "показывает потенциальную экономию в рублях."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "manifests": {
                                "type": "object",
                                "description": "Словарь манифестов (filename: yaml_content)"
                            },
                            "cluster_type": {
                                "type": "string",
                                "enum": ["production", "staging", "development"],
                                "description": "Тип кластера для оптимизации",
                                "default": "production"
                            }
                        },
                        "required": ["manifests"]
                    }
                ),

                types.Tool(
                    name="analyze_security",
                    description=(
                        "🔒 Анализирует безопасность K8s манифестов. "
                        "Проверяет security contexts, secrets management, network policies, "
                        "RBAC, и соответствие Pod Security Standards. Генерирует security score."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "manifests": {
                                "type": "object",
                                "description": "Словарь манифестов (filename: yaml_content)"
                            }
                        },
                        "required": ["manifests"]
                    }
                ),
            ]

        @self.server.call_tool()
        async def call_tool(
            name: str,
            arguments: Dict[str, Any]
        ) -> List[types.TextContent]:
            """Обработка вызова tool"""

            try:
                logger.info(f"🔧 Вызов tool: {name}")
                logger.info(f"   Аргументы: {arguments}")

                # Проверка доступности LLM
                if name == "generate_telecom_manifest" and not self.claude_client:
                    return [types.TextContent(
                        type="text",
                        text="❌ Ошибка: ANTHROPIC_API_KEY не установлен!\n\n"
                             "Для использования LLM генерации:\n"
                             "1. Создайте файл .env\n"
                             "2. Добавьте: ANTHROPIC_API_KEY=your-key\n"
                             "3. Перезапустите сервер\n\n"
                             "Используйте generate_k8s_manifest для генерации без LLM."
                    )]

                # Маршрутизация на соответствующий обработчик
                if name == "generate_telecom_manifest":
                    result = await self._handle_telecom_manifest(arguments)
                elif name == "generate_k8s_manifest":
                    result = await self._handle_k8s_manifest(arguments)
                elif name == "generate_cicd_pipeline":
                    result = await self._handle_cicd_pipeline(arguments)
                elif name == "generate_documentation":
                    result = await self._handle_documentation(arguments)
                elif name == "troubleshoot_deployment":
                    result = await self._handle_troubleshoot(arguments)
                elif name == "apply_auto_fix":
                    result = await self._handle_apply_fix(arguments)
                elif name == "analyze_cost":
                    result = await self._handle_cost_analysis(arguments)
                elif name == "analyze_security":
                    result = await self._handle_security_analysis(arguments)
                else:
                    result = f"❌ Неизвестный tool: {name}"

                return [types.TextContent(type="text", text=result)]

            except ValueError as e:
                logger.error(f"❌ Ошибка валидации при выполнении tool {name}: {e}")
                return [types.TextContent(
                    type="text",
                    text=f"❌ Ошибка валидации: {str(e)}\n\nПроверьте входные параметры."
                )]
            except RuntimeError as e:
                logger.error(f"❌ Runtime ошибка при выполнении tool {name}: {e}")
                return [types.TextContent(
                    type="text",
                    text=f"❌ Runtime ошибка: {str(e)}\n\nПопробуйте повторить запрос или проверьте конфигурацию."
                )]
            except Exception as e:
                logger.error(f"❌ Критическая ошибка при выполнении tool {name}: {e}", exc_info=True)
                return [types.TextContent(
                    type="text",
                    text=f"❌ Критическая ошибка: {str(e)}\n\nПодробности в логах.\n\nТип ошибки: {type(e).__name__}"
                )]

    def _validate_prompt(self, prompt: str) -> str:
        """Валидация промпта"""
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")
        if len(prompt) > 10000:
            raise ValueError("Prompt must be less than 10000 characters")
        return prompt.strip()

    def _validate_output_dir(self, output_dir: str) -> Path:
        """Валидация output директории (защита от path traversal)"""
        output_path = Path(output_dir).resolve()
        project_root = Path.cwd().resolve()

        # Проверка что путь не выходит за пределы проекта
        if not str(output_path).startswith(str(project_root)):
            raise ValueError(f"Output directory must be within project: {output_dir}")

        return output_path

    async def _handle_telecom_manifest(self, args: Dict[str, Any]) -> str:
        """Обработка генерации телеком-манифестов с LLM"""
        # Валидация входных данных
        prompt = self._validate_prompt(args.get("prompt", ""))
        output_path = self._validate_output_dir(args.get("output_dir", "./output"))

        logger.info(f"📡 Генерация телеком-манифеста: {prompt[:100]}...")

        # Проверка наличия Claude client
        if not self.claude_client:
            raise RuntimeError("Claude client is not initialized (missing API key)")

        # Используем LLM для полной генерации
        result = await self.claude_client.generate_telecom_deployment(
            prompt=prompt,
            output_dir=str(output_path)
        )

        # Сохраняем манифесты
        output_path.mkdir(parents=True, exist_ok=True)

        saved_files = []
        for filename, content in result["manifests"].items():
            # Валидация YAML перед сохранением
            if OutputConfig.VALIDATE_YAML and filename.endswith('.yaml'):
                try:
                    # Проверяем что это валидный YAML
                    yaml.safe_load_all(content)
                    logger.debug(f"{self.symbols['success']} YAML валидация пройдена: {filename}")
                except yaml.YAMLError as e:
                    logger.error(f"{self.symbols['error']} Невалидный YAML в {filename}: {e}")
                    logger.warning(f"   Пропускаем сохранение {filename}")
                    continue

            file_path = output_path / filename
            file_path.write_text(content, encoding=OutputConfig.FILE_ENCODING)
            saved_files.append(str(file_path))
            logger.info(f"{self.symbols['success']} Сохранен: {file_path}")

        # Сохраняем документацию
        if "documentation" in result:
            docs_path = output_path / "RUNBOOK.md"
            docs_path.write_text(result["documentation"], encoding='utf-8')
            saved_files.append(str(docs_path))
            logger.info(f"📄 Документация: {docs_path}")

        # Формируем ответ
        response = f"✅ Телеком-манифесты успешно сгенерированы!\n\n"
        response += f"📊 Анализ:\n{result.get('analysis', 'N/A')}\n\n"
        response += f"📁 Сохранено файлов: {len(saved_files)}\n"
        for file in saved_files:
            response += f"   • {file}\n"

        response += f"\n💡 Что дальше:\n"
        response += f"1. Проверьте манифесты: ls {output_path}\n"
        response += f"2. Валидация: kubectl apply --dry-run=client -f {output_path}/\n"
        response += f"3. Деплой: kubectl apply -f {output_path}/\n"

        return response

    async def _handle_k8s_manifest(self, args: Dict[str, Any]) -> str:
        """Обработка генерации стандартных K8s манифестов (без LLM)"""
        service_name = args["service_name"]
        image = args["image"]
        replicas = args.get("replicas", 3)
        port = args.get("port", 8080)

        logger.info(f"🔧 Генерация K8s манифеста: {service_name}")

        # Генерация через шаблоны
        manifests = self.k8s_generator.generate_basic_deployment(
            service_name=service_name,
            image=image,
            replicas=replicas,
            port=port
        )

        # Сохранение
        output_dir = Path("./output")
        output_dir.mkdir(parents=True, exist_ok=True)

        saved_files = []
        for filename, content in manifests.items():
            file_path = output_dir / filename
            file_path.write_text(content, encoding='utf-8')
            saved_files.append(str(file_path))

        response = f"✅ K8s манифесты сгенерированы!\n\n"
        response += f"📋 Сервис: {service_name}\n"
        response += f"🐳 Образ: {image}\n"
        response += f"🔢 Реплики: {replicas}\n"
        response += f"🔌 Порт: {port}\n\n"
        response += f"📁 Файлы:\n"
        for file in saved_files:
            response += f"   • {file}\n"

        return response

    async def _handle_cicd_pipeline(self, args: Dict[str, Any]) -> str:
        """Обработка генерации CI/CD пайплайна"""
        platform = args["platform"]
        project_type = args["project_type"]
        include_security = args.get("include_security_scan", True)

        logger.info(f"🔄 Генерация CI/CD: {platform} для {project_type}")

        # Генерация через CICDGenerator
        if self.claude_client:
            # С LLM (интеллектуальная генерация)
            config = await self.claude_client.generate_cicd(
                platform=platform,
                project_type=project_type,
                include_security=include_security
            )
        else:
            # Без LLM (шаблонная генерация)
            config = self.cicd_generator.generate_pipeline(
                platform=platform,
                project_type=project_type,
                include_security=include_security
            )

        # Сохранение
        filename = ".gitlab-ci.yml" if platform == "gitlab" else ".github/workflows/ci.yml"
        output_path = Path(filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(config, encoding='utf-8')

        response = f"✅ CI/CD pipeline сгенерирован!\n\n"
        response += f"🏗️  Платформа: {platform}\n"
        response += f"📦 Тип проекта: {project_type}\n"
        response += f"🔒 Security scan: {'включен' if include_security else 'отключен'}\n\n"
        response += f"📁 Файл: {output_path}\n"

        return response

    async def _handle_documentation(self, args: Dict[str, Any]) -> str:
        """Обработка генерации документации"""
        component_type = args["component_type"]
        manifests = args.get("manifests", {})

        logger.info(f"📝 Генерация документации для: {component_type}")

        if not self.claude_client:
            return "❌ Для генерации документации требуется ANTHROPIC_API_KEY"

        # Генерация через LLM
        docs = await self.claude_client.generate_documentation(
            component_type=component_type,
            manifests=manifests
        )

        # Сохранение
        docs_path = Path("./output/RUNBOOK.md")
        docs_path.parent.mkdir(parents=True, exist_ok=True)
        docs_path.write_text(docs, encoding='utf-8')

        response = f"✅ Документация сгенерирована!\n\n"
        response += f"📄 Компонент: {component_type}\n"
        response += f"📁 Файл: {docs_path}\n"

        return response

    async def _handle_troubleshoot(self, args: Dict[str, Any]) -> str:
        """Обработка auto-troubleshooting deployment"""
        namespace = args["namespace"]
        deployment_name = args["deployment_name"]

        logger.info(f"🔍 Диагностика deployment: {namespace}/{deployment_name}")

        if not self.troubleshooter:
            return "❌ Auto-troubleshooter недоступен (требуется ANTHROPIC_API_KEY)"

        # Запуск диагностики
        diagnosis = await self.troubleshooter.diagnose_deployment(
            namespace=namespace,
            deployment_name=deployment_name
        )

        if diagnosis["status"] == "error":
            return f"❌ Ошибка диагностики: {diagnosis['error']}"

        # Формирование отчета
        response = f"🔍 **Диагностика deployment: {namespace}/{deployment_name}**\n\n"
        response += f"**Проблема:** {diagnosis['problem']}\n\n"
        response += f"**Корневая причина:** {diagnosis['root_cause']}\n\n"
        response += f"**Критичность:** {diagnosis['severity']}\n\n"

        if diagnosis['fix_command']:
            response += f"**Предложенное решение:**\n```bash\n{diagnosis['fix_command']}\n```\n\n"
            response += f"**Объяснение:** {diagnosis.get('fix_explanation', 'N/A')}\n\n"

            if diagnosis['auto_fixable']:
                response += "✅ **Безопасно применить автоматически**\n"
                response += f"Для применения используйте: apply_auto_fix с командой выше\n"
            else:
                response += "⚠️ **Требуется ручное подтверждение**\n"
                response += "Проверьте команду перед применением\n"

        return response

    async def _handle_apply_fix(self, args: Dict[str, Any]) -> str:
        """Обработка применения автоматического исправления"""
        fix_command = args["fix_command"]
        dry_run = args.get("dry_run", True)

        logger.info(f"🔧 Применение fix: {fix_command} (dry_run={dry_run})")

        if not self.troubleshooter:
            return "❌ Auto-troubleshooter недоступен (требуется ANTHROPIC_API_KEY)"

        # Применение исправления
        result = await self.troubleshooter.apply_fix(
            fix_command=fix_command,
            dry_run=dry_run
        )

        if result["status"] == "success":
            mode = "DRY-RUN" if result["dry_run"] else "ПРИМЕНЕНО"
            response = f"✅ **Fix {mode} успешно!**\n\n"
            response += f"**Команда:** {fix_command}\n\n"
            response += f"**Результат:**\n```\n{result['output']}\n```\n"

            if result["dry_run"]:
                response += "\n💡 Для реального применения установите dry_run=false\n"

            return response
        else:
            return f"❌ Ошибка применения fix: {result['error']}"

    async def _handle_cost_analysis(self, args: Dict[str, Any]) -> str:
        """Обработка анализа стоимости"""
        manifests = args["manifests"]
        cluster_type = args.get("cluster_type", "production")

        logger.info(f"💰 Анализ стоимости для {cluster_type} кластера")

        if not self.cost_optimizer:
            return "❌ Cost Optimizer недоступен (требуется ANTHROPIC_API_KEY)"

        # Запуск анализа
        analysis = await self.cost_optimizer.analyze_costs(
            manifests=manifests,
            cluster_type=cluster_type
        )

        if analysis["status"] == "error":
            return f"❌ Ошибка анализа стоимости: {analysis['error']}"

        # Формирование отчета
        response = f"💰 **COST OPTIMIZATION ANALYSIS**\n\n"
        response += f"**Кластер:** {cluster_type}\n\n"
        response += f"**Текущая стоимость:** {analysis['current_cost_monthly']:,.2f} ₽/мес\n"
        response += f"**Оптимизированная:** {analysis['optimized_cost_monthly']:,.2f} ₽/мес\n"
        response += f"**Экономия:** {analysis['savings_monthly']:,.2f} ₽/мес ({analysis['savings_percentage']}%)\n"
        response += f"**Экономия в год:** {analysis['savings_yearly']:,.2f} ₽/год\n\n"

        if analysis['optimizations']:
            response += f"**Предложенные оптимизации:**\n"
            for opt in analysis['optimizations']:
                response += f"\n• **{opt.get('type')}** для `{opt.get('target')}`\n"
                response += f"  - Было: {opt.get('from')}\n"
                response += f"  - Станет: {opt.get('to')}\n"
                response += f"  - Экономия: {opt.get('savings', 0):,.2f} ₽/мес\n"
                response += f"  - Причина: {opt.get('reason', 'N/A')}\n"

        if analysis['recommendations']:
            response += f"\n**Рекомендации:**\n"
            for rec in analysis['recommendations']:
                response += f"• {rec}\n"

        return response

    async def _handle_security_analysis(self, args: Dict[str, Any]) -> str:
        """Обработка security анализа"""
        manifests = args["manifests"]

        logger.info("🔒 Запуск security анализа")

        if not self.security_analyzer:
            return "❌ Security Analyzer недоступен (требуется ANTHROPIC_API_KEY)"

        # Запуск анализа
        analysis = await self.security_analyzer.analyze_security(manifests)

        if analysis["status"] == "error":
            return f"❌ Ошибка security анализа: {analysis['error']}"

        # Формирование отчета
        response = f"🔒 **SECURITY POSTURE ANALYSIS**\n\n"
        response += f"**Security Score:** {analysis['security_score']}/100 ({analysis['grade']})\n\n"

        # Compliance
        if analysis.get('compliance'):
            response += f"**Compliance:**\n"
            for std, status in analysis['compliance'].items():
                icon = "✅" if status else "❌"
                response += f"  {icon} {std}\n"
            response += "\n"

        # Critical issues
        if analysis['critical_issues']:
            response += f"**🔴 Critical Issues ({len(analysis['critical_issues'])}):**\n"
            for issue in analysis['critical_issues']:
                response += f"\n• **{issue.get('issue')}**\n"
                response += f"  - Severity: {issue.get('severity', 'unknown')}\n"
                response += f"  - Affected: {issue.get('affected', 'N/A')}\n"
                response += f"  - Mitigation: {issue.get('mitigation', 'N/A')}\n"

        # Warnings
        if analysis['warnings']:
            response += f"\n**⚠️ Warnings ({len(analysis['warnings'])}):**\n"
            for warning in analysis['warnings']:
                response += f"\n• {warning.get('warning', 'N/A')}\n"
                if warning.get('recommendation'):
                    response += f"  → {warning['recommendation']}\n"

        # Auto-fixes
        if analysis.get('auto_fixes'):
            auto_fixable = [f for f in analysis['auto_fixes'] if f.get('auto_applicable')]
            if auto_fixable:
                response += f"\n**🔧 Auto-Fixes Available ({len(auto_fixable)}):**\n"
                for fix in auto_fixable:
                    response += f"\n• {fix.get('issue')}\n"
                    if fix.get('kubectl_command'):
                        response += f"  ```bash\n  {fix['kubectl_command']}\n  ```\n"

        # Recommendations
        if analysis['recommendations']:
            response += f"\n**💡 Recommendations:**\n"
            for rec in analysis['recommendations']:
                response += f"• {rec}\n"

        return response

    async def run(self):
        """Запуск MCP сервера"""
        logger.info("🚀 Запуск MTS Deploy AI MCP Server...")
        logger.info(f"📍 Версия: 1.0.0")
        logger.info(f"🔑 API ключ: {'✅ установлен' if self.api_key else '❌ не установлен'}")

        async with stdio_server() as (read_stream, write_stream):
            logger.info("✅ MCP Server запущен и готов к работе!")
            await self.server.run(
                read_stream,
                write_stream,
                initialization_options=None  # type: ignore
            )


async def main():
    """Главная функция"""
    try:
        server = MTSDeployServer()
        await server.run()
    except KeyboardInterrupt:
        logger.info("\n👋 Остановка сервера...")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
