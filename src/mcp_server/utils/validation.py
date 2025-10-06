"""
Утилиты для валидации и security checks
"""

import os
import re
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_k8s_resource_name(name: str, resource_type: str = "resource") -> str:
    """
    Валидирует имя Kubernetes ресурса согласно RFC 1123 DNS label

    Правила:
    - строчные буквы и цифры + дефисы
    - максимум 253 символа
    - начало и конец - буквенно-цифровые символы

    Args:
        name: Имя ресурса для валидации
        resource_type: Тип ресурса (для сообщений об ошибках)

    Returns:
        Валидированное имя

    Raises:
        ValueError: Если имя не соответствует требованиям K8s
    """
    if not name:
        raise ValueError(f"K8s {resource_type} name cannot be empty")

    if len(name) > 253:
        raise ValueError(
            f"K8s {resource_type} name too long: {len(name)} chars (max 253). "
            f"Name: '{name[:50]}...'"
        )

    # RFC 1123 DNS label: lowercase alphanumeric + hyphens, must start/end with alphanumeric
    if not re.match(r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$', name):
        raise ValueError(
            f"Invalid K8s {resource_type} name '{name}'. "
            "Must be lowercase alphanumeric with hyphens, "
            "starting and ending with alphanumeric character. "
            "Examples: 'my-app', 'web-server-1', 'database'"
        )

    logger.debug(f"Validated K8s {resource_type} name: {name}")
    return name


def validate_k8s_namespace(namespace: str) -> str:
    """
    Валидирует имя Kubernetes namespace

    Args:
        namespace: Имя namespace для валидации

    Returns:
        Валидированное имя namespace

    Raises:
        ValueError: Если namespace не валиден
    """
    # Namespace имеет те же правила что и resource name
    return validate_k8s_resource_name(namespace, resource_type="namespace")


class SecurityValidator:
    """Валидатор безопасности для конфигураций"""

    # Паттерны для обнаружения потенциальных секретов
    SECRET_PATTERNS = {
        'api_key': re.compile(r'(api[_-]?key|apikey)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})', re.IGNORECASE),
        'password': re.compile(r'password["\']?\s*[:=]\s*["\']?([^"\'\s]{8,})', re.IGNORECASE),
        'token': re.compile(r'(token|bearer)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-\.]{20,})', re.IGNORECASE),
        'aws_key': re.compile(r'(AKIA|aws_access_key_id)[A-Z0-9]{16,}', re.IGNORECASE),
        'private_key': re.compile(r'-----BEGIN [A-Z ]+ PRIVATE KEY-----'),
    }

    @staticmethod
    def validate_env_file(env_path: str = ".env") -> Dict[str, Any]:
        """
        Валидирует .env файл

        Returns:
            {
                'valid': bool,
                'errors': [],
                'warnings': [],
                'required_keys': []
            }
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'required_keys': []
        }

        env_file = Path(env_path)

        # Проверка существования
        if not env_file.exists():
            result['valid'] = False
            result['errors'].append(f"❌ Файл {env_path} не найден")
            result['warnings'].append("💡 Скопируйте .env.example в .env")
            return result

        # Чтение и парсинг
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            env_vars = {}
            for line_num, line in enumerate(lines, 1):
                line = line.strip()

                # Пропуск комментариев и пустых строк
                if not line or line.startswith('#'):
                    continue

                # Парсинг переменной
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    env_vars[key] = value
                else:
                    result['warnings'].append(f"⚠️  Строка {line_num}: неверный формат")

            # Проверка обязательных ключей
            required_keys = ['ANTHROPIC_API_KEY']
            for key in required_keys:
                if key not in env_vars:
                    result['valid'] = False
                    result['errors'].append(f"❌ Отсутствует обязательная переменная: {key}")
                    result['required_keys'].append(key)
                elif not env_vars[key] or env_vars[key] == 'your-api-key-here':
                    result['valid'] = False
                    result['errors'].append(f"❌ {key} не установлен (содержит placeholder)")

            # Проверка формата API ключа
            if 'ANTHROPIC_API_KEY' in env_vars:
                api_key = env_vars['ANTHROPIC_API_KEY']
                if not api_key.startswith('sk-ant-'):
                    result['warnings'].append("⚠️  ANTHROPIC_API_KEY должен начинаться с 'sk-ant-'")

            logger.info(f"✅ .env валидация завершена: {len(env_vars)} переменных найдено")

        except Exception as e:
            result['valid'] = False
            result['errors'].append(f"❌ Ошибка чтения .env: {e}")

        return result

    @staticmethod
    def validate_yaml_manifest(yaml_content: str) -> Dict[str, Any]:
        """
        Валидирует YAML манифест на наличие проблем безопасности

        Returns:
            {
                'valid': bool,
                'warnings': [],
                'recommendations': []
            }
        """
        result = {
            'valid': True,
            'warnings': [],
            'recommendations': []
        }

        # Проверка на захардкоженные credentials (в stringData)
        if re.search(r'(stringData|data):\s*\n\s*password:\s*["\']?[^"\'\s]{5,}', yaml_content, re.IGNORECASE):
            result['warnings'].append("⚠️  Обнаружен захардкоженный пароль в манифесте")
            result['recommendations'].append("💡 Используйте Kubernetes Secrets с правильным шифрованием")

        # Проверка на runAsRoot
        if 'runAsNonRoot: false' in yaml_content:
            result['warnings'].append("⚠️  Контейнер запускается от root")
            result['recommendations'].append("💡 Рекомендуется runAsNonRoot: true")

        # Проверка на отсутствие resource limits
        if 'resources:' not in yaml_content or 'limits:' not in yaml_content:
            result['warnings'].append("⚠️  Отсутствуют resource limits")
            result['recommendations'].append("💡 Добавьте CPU и Memory limits")

        # Проверка на privileged mode
        if 'privileged: true' in yaml_content:
            result['warnings'].append("⚠️  Используется privileged режим")
            result['recommendations'].append("💡 Используйте capabilities вместо privileged")

        return result


def validate_api_key(api_key: Optional[str]) -> bool:
    """
    Валидирует Anthropic API ключ

    Args:
        api_key: API ключ для проверки

    Returns:
        True если валиден, False иначе
    """
    if not api_key:
        logger.error("API ключ отсутствует")
        return False

    if api_key == 'your-api-key-here':
        logger.error("API ключ содержит placeholder значение")
        return False

    if not api_key.startswith('sk-ant-'):
        logger.warning("API ключ не соответствует ожидаемому формату (должен начинаться с 'sk-ant-')")
        return False

    if len(api_key) < 20:
        logger.error("API ключ слишком короткий")
        return False

    logger.info("✅ API ключ прошел базовую валидацию")
    return True


def sanitize_secret_value(value: str, placeholder: str = "***REDACTED***") -> str:
    """
    Заменяет секретное значение на placeholder для логирования

    Args:
        value: Секретное значение
        placeholder: Что показывать вместо значения

    Returns:
        Безопасная строка для логирования
    """
    if not value or len(value) < 4:
        return placeholder

    # Показываем только первые и последние 4 символа
    return f"{value[:4]}...{value[-4:]}"


def check_file_permissions(file_path: str) -> Dict[str, Any]:
    """
    Проверяет права доступа к файлу

    Args:
        file_path: Путь к файлу

    Returns:
        {
            'secure': bool,
            'permissions': str,
            'warnings': []
        }
    """
    result = {
        'secure': True,
        'permissions': 'unknown',
        'warnings': []
    }

    try:
        path = Path(file_path)
        if not path.exists():
            result['secure'] = False
            result['warnings'].append(f"Файл {file_path} не существует")
            return result

        # На Windows проверка прав ограничена
        if os.name == 'nt':
            result['permissions'] = 'windows (проверка ограничена)'
            logger.debug(f"Windows detected - permissions check limited for {file_path}")
        else:
            import stat
            mode = path.stat().st_mode
            result['permissions'] = oct(stat.S_IMODE(mode))

            # Проверка на чрезмерные права (например, world-readable для .env)
            if stat.S_IROTH & mode:
                result['secure'] = False
                result['warnings'].append(f"⚠️  Файл доступен для чтения всем пользователям")

    except Exception as e:
        logger.error(f"Ошибка проверки прав доступа: {e}")
        result['secure'] = False
        result['warnings'].append(f"Ошибка: {e}")

    return result
