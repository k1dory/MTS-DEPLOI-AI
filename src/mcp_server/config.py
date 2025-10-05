"""
Конфигурация MTS Deploy AI
Централизованное управление константами и настройками
"""

import os
from typing import Dict, Any


# ========================================
# LLM Configuration
# ========================================

class LLMConfig:
    """Конфигурация для Claude API"""

    # Модель Claude (можно переопределить через .env)
    MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

    # Temperature для разных типов генерации
    TEMP_DETERMINISTIC = 0.2  # Для оптимизации манифестов (меньше вариативности)
    TEMP_BALANCED = 0.3       # Для анализа и параметров (баланс точности и креативности)
    TEMP_CREATIVE = 0.5       # Для документации (больше вариативности)

    # Max tokens для разных операций
    TOKENS_ANALYSIS = 1000      # Анализ промпта - короткий ответ
    TOKENS_PARAMETERS = 1500    # Генерация параметров - средний ответ
    TOKENS_OPTIMIZATION = 4000  # Оптимизация манифестов - длинный ответ
    TOKENS_DOCUMENTATION = 4000 # Генерация документации - длинный ответ
    TOKENS_CICD = 3000         # Генерация CI/CD - длинный ответ


# ========================================
# Network Configuration
# ========================================

class NetworkConfig:
    """Конфигурация сетей для телеком-компонентов"""

    # Базовая сеть для телеком (10.100.x.x по умолчанию)
    BASE_NETWORK = os.getenv("TELECOM_NETWORK_BASE", "10.100")

    # CIDR маска
    NETWORK_CIDR = "/24"

    # Стартовый IP в подсети
    SUBNET_START_IP = "10"
    SUBNET_END_IP = "100"
    SUBNET_GATEWAY_IP = "1"

    @staticmethod
    def get_subnet(index: int) -> str:
        """
        Генерирует subnet для интерфейса

        Args:
            index: Индекс интерфейса (0, 1, 2...)

        Returns:
            Subnet в формате "10.100.0.0/24"
        """
        base = NetworkConfig.BASE_NETWORK
        third_octet = index
        return f"{base}.{third_octet}.0{NetworkConfig.NETWORK_CIDR}"

    @staticmethod
    def get_ip(index: int) -> str:
        """
        Генерирует IP адрес для интерфейса

        Args:
            index: Индекс интерфейса

        Returns:
            IP адрес в формате "10.100.0.10"
        """
        base = NetworkConfig.BASE_NETWORK
        third_octet = index
        return f"{base}.{third_octet}.{NetworkConfig.SUBNET_START_IP}"

    @staticmethod
    def get_gateway(index: int) -> str:
        """Генерирует gateway IP для интерфейса"""
        base = NetworkConfig.BASE_NETWORK
        third_octet = index
        return f"{base}.{third_octet}.{NetworkConfig.SUBNET_GATEWAY_IP}"


# ========================================
# Docker Configuration
# ========================================

class DockerConfig:
    """Конфигурация Docker registry"""

    # Docker registry (можно переопределить через .env)
    REGISTRY = os.getenv("DOCKER_REGISTRY", "registry.mts.ru")

    # Namespace/organization
    ORGANIZATION = os.getenv("DOCKER_ORGANIZATION", "telecom")

    # Тег по умолчанию
    DEFAULT_TAG = "latest"

    @staticmethod
    def get_image_name(component_type: str, tag: str | None = None) -> str:
        """
        Генерирует полное имя Docker образа

        Args:
            component_type: Тип компонента (5g_upf, billing, etc.)
            tag: Тег образа (по умолчанию: latest)

        Returns:
            Полное имя образа: "registry.mts.ru/telecom/5g_upf:latest"
        """
        tag = tag or DockerConfig.DEFAULT_TAG
        return f"{DockerConfig.REGISTRY}/{DockerConfig.ORGANIZATION}/{component_type}:{tag}"


# ========================================
# Output Configuration
# ========================================

class OutputConfig:
    """Конфигурация для выходных файлов"""

    # Директория для сохранения манифестов
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")

    # Кодировка файлов
    FILE_ENCODING = "utf-8"

    # Валидировать YAML перед сохранением
    VALIDATE_YAML = os.getenv("VALIDATE_YAML", "true").lower() == "true"


# ========================================
# UI Configuration
# ========================================

class UIConfig:
    """Конфигурация UI элементов (логирование, вывод)"""

    @staticmethod
    def _detect_emoji_support() -> bool:
        """Автоопределение поддержки emoji в консоли"""
        import sys

        # Windows console обычно не поддерживает emoji
        if os.name == 'nt':
            try:
                encoding = sys.stdout.encoding or 'cp1251'
                return encoding.lower() in ['utf-8', 'utf8']
            except:
                return False
        return True

    # Использовать эмоджи в логах (автодетект или из .env)
    USE_EMOJI = os.getenv("USE_EMOJI", str(_detect_emoji_support())).lower() == "true"

    # Символы для статусов (с/без эмоджи)
    @staticmethod
    def get_symbols() -> Dict[str, str]:
        """Возвращает символы для статусов в зависимости от настройки USE_EMOJI"""
        if UIConfig.USE_EMOJI:
            return {
                "success": "✅",
                "error": "❌",
                "warning": "⚠️ ",
                "info": "ℹ️ ",
                "rocket": "🚀",
                "lock": "🔒",
                "search": "🔍",
                "wrench": "🔧",
                "file": "📁",
                "docs": "📄",
                "telecom": "📡",
                "robot": "🤖",
            }
        else:
            return {
                "success": "[OK]",
                "error": "[ERROR]",
                "warning": "[WARN]",
                "info": "[INFO]",
                "rocket": "[START]",
                "lock": "[SECURE]",
                "search": "[CHECK]",
                "wrench": "[FIX]",
                "file": "[FILE]",
                "docs": "[DOCS]",
                "telecom": "[TELECOM]",
                "robot": "[AI]",
            }


# ========================================
# Secrets Configuration
# ========================================

class SecretsConfig:
    """Конфигурация для генерации секретов"""

    # Использовать placeholders вместо генерации случайных значений
    USE_PLACEHOLDERS = True

    # Шаблон placeholder
    PLACEHOLDER_PREFIX = "__PLACEHOLDER_"
    PLACEHOLDER_SUFFIX = "__"

    @staticmethod
    def get_placeholder(name: str) -> str:
        """
        Генерирует placeholder для секретного значения

        Args:
            name: Имя переменной (PASSWORD, API_KEY, etc.)

        Returns:
            Placeholder в формате "__PLACEHOLDER_PASSWORD__"
        """
        return f"{SecretsConfig.PLACEHOLDER_PREFIX}{name.upper()}{SecretsConfig.PLACEHOLDER_SUFFIX}"

    # Дефолтные значения для демонстрации (НЕ для production!)
    # Эти значения используются только в примерах с явным предупреждением
    DEMO_DATABASE_URL_TEMPLATE = "postgresql://billing_user:{password}@postgres:5432/billing_db"
    DEMO_RABBITMQ_URL_TEMPLATE = "amqp://billing_user:{password}@rabbitmq:5672/"


# ========================================
# Validation Configuration
# ========================================

class ValidationConfig:
    """Конфигурация валидации"""

    # Строгий режим (fail on warnings)
    STRICT_MODE = os.getenv("STRICT_MODE", "false").lower() == "true"

    # Валидировать API ключ при старте
    VALIDATE_API_KEY_ON_START = True

    # Минимальная длина API ключа
    MIN_API_KEY_LENGTH = 20


# ========================================
# Экспорт всех конфигов
# ========================================

__all__ = [
    "LLMConfig",
    "NetworkConfig",
    "DockerConfig",
    "OutputConfig",
    "UIConfig",
    "SecretsConfig",
    "ValidationConfig",
]
