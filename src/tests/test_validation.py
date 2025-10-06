"""
Unit тесты для validation утилит
Критически важные функции безопасности
"""

import pytest
import os
from pathlib import Path
from src.mcp_server.utils.validation import (
    validate_k8s_resource_name,
    validate_k8s_namespace,
    validate_api_key,
    sanitize_secret_value,
    SecurityValidator,
    check_file_permissions
)


class TestK8sValidation:
    """Тесты валидации Kubernetes имен"""

    def test_valid_resource_names(self):
        """Тест валидных имен ресурсов"""
        valid_names = [
            "app",
            "my-app",
            "web-server-1",
            "database-prod",
            "test123",
            "a",  # минимальная длина
            "a" * 253,  # максимальная длина
        ]

        for name in valid_names:
            result = validate_k8s_resource_name(name, "test")
            assert result == name, f"Валидное имя '{name}' должно пройти валидацию"

    def test_invalid_resource_names(self):
        """Тест невалидных имен ресурсов"""
        invalid_names = [
            "",  # пустое
            "MyApp",  # заглавные буквы
            "my_app",  # подчеркивание
            "-app",  # начинается с дефиса
            "app-",  # заканчивается дефисом
            "my app",  # пробел
            "app@123",  # спецсимволы
            "a" * 254,  # слишком длинное
        ]

        for name in invalid_names:
            with pytest.raises(ValueError):
                validate_k8s_resource_name(name, "test")

    def test_namespace_validation(self):
        """Тест валидации namespace"""
        assert validate_k8s_namespace("default") == "default"
        assert validate_k8s_namespace("telecom") == "telecom"
        assert validate_k8s_namespace("kube-system") == "kube-system"

        with pytest.raises(ValueError):
            validate_k8s_namespace("Invalid-Namespace")

    def test_injection_protection(self):
        """Тест защиты от injection атак"""
        malicious_names = [
            "../etc/passwd",
            "'; DROP TABLE users; --",
            "$(rm -rf /)",
            "`whoami`",
            "${IFS}cat${IFS}/etc/passwd",
        ]

        for name in malicious_names:
            with pytest.raises(ValueError):
                validate_k8s_resource_name(name, "deployment")


class TestAPIKeyValidation:
    """Тесты валидации API ключей"""

    def test_valid_api_key(self):
        """Тест валидного API ключа"""
        valid_key = "sk-ant-" + "a" * 50
        assert validate_api_key(valid_key) is True

    def test_invalid_api_keys(self):
        """Тест невалидных API ключей"""
        invalid_keys = [
            None,
            "",
            "your-api-key-here",  # placeholder
            "sk-openai-123",  # неправильный префикс
            "sk-ant-short",  # слишком короткий
            "invalid-key",
        ]

        for key in invalid_keys:
            assert validate_api_key(key) is False

    def test_api_key_sanitization(self):
        """Тест sanitization API ключа для логов"""
        api_key = "sk-ant-1234567890abcdefghijklmnop"
        sanitized = sanitize_secret_value(api_key)

        # Должен показывать только первые и последние 4 символа
        assert "sk-a" in sanitized
        assert "mnop" in sanitized
        assert "..." in sanitized
        assert len(sanitized) < len(api_key)

        # Полный ключ не должен быть виден
        assert "1234567890abcdefghij" not in sanitized


class TestSecurityValidator:
    """Тесты SecurityValidator класса"""

    def test_env_file_validation_missing(self, tmp_path):
        """Тест валидации несуществующего .env файла"""
        result = SecurityValidator.validate_env_file(str(tmp_path / "nonexistent.env"))

        assert result['valid'] is False
        assert len(result['errors']) > 0
        assert any(".env не найден" in err for err in result['errors'])

    def test_env_file_validation_valid(self, tmp_path):
        """Тест валидации корректного .env файла"""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-test123456789012345678901234567890\n")

        result = SecurityValidator.validate_env_file(str(env_file))

        assert result['valid'] is True
        assert len(result['errors']) == 0

    def test_env_file_validation_placeholder(self, tmp_path):
        """Тест обнаружения placeholder в .env"""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=your-api-key-here\n")

        result = SecurityValidator.validate_env_file(str(env_file))

        assert result['valid'] is False
        assert any("placeholder" in err.lower() for err in result['errors'])

    def test_yaml_manifest_security(self):
        """Тест проверки безопасности YAML манифестов"""
        # Небезопасный манифест с hardcoded password (правильный формат)
        unsafe_yaml = """
apiVersion: v1
kind: Secret
metadata:
  name: test
stringData:
  password: hardcoded_password123
"""

        result = SecurityValidator.validate_yaml_manifest(unsafe_yaml)

        # Проверяем что warnings или recommendations содержат информацию о проблеме
        all_messages = result['warnings'] + result['recommendations']
        assert len(all_messages) > 0, "Should detect security issues"
        # Хотя бы одно сообщение должно быть о паролях или секретах
        assert any(("password" in msg.lower() or "secret" in msg.lower() or "hardcoded" in msg.lower())
                   for msg in all_messages), "Should warn about hardcoded passwords"

    def test_privileged_detection(self):
        """Тест обнаружения privileged режима"""
        privileged_yaml = """
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: app
        securityContext:
          privileged: true
"""

        result = SecurityValidator.validate_yaml_manifest(privileged_yaml)

        assert len(result['warnings']) > 0
        assert any("privileged" in w.lower() for w in result['warnings'])

    def test_resource_limits_detection(self):
        """Тест обнаружения отсутствия resource limits"""
        no_limits_yaml = """
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: app
        image: nginx
"""

        result = SecurityValidator.validate_yaml_manifest(no_limits_yaml)

        assert len(result['warnings']) > 0
        assert any("resource" in w.lower() and "limit" in w.lower()
                   for w in result['warnings'])


class TestFilePermissions:
    """Тесты проверки прав доступа к файлам"""

    def test_check_permissions_nonexistent(self):
        """Тест проверки несуществующего файла"""
        result = check_file_permissions("/nonexistent/file.txt")

        assert result['secure'] is False
        assert len(result['warnings']) > 0

    def test_check_permissions_existing(self, tmp_path):
        """Тест проверки существующего файла"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = check_file_permissions(str(test_file))

        # На Windows проверка ограничена
        if os.name == 'nt':
            assert result['permissions'] == 'windows (проверка ограничена)'
        else:
            assert 'permissions' in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
