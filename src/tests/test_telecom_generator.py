"""
Unit тесты для TelecomGenerator
Критически важные функции генерации манифестов
"""

import pytest
import yaml
from src.mcp_server.tools.telecom_generator import (
    TelecomGenerator,
    TELECOM_COMPONENTS
)
from src.mcp_server.config import DockerConfig, NetworkConfig


class TestTelecomGenerator:
    """Тесты генератора телеком-манифестов"""

    @pytest.fixture
    def generator(self):
        """Фикстура с инстансом генератора"""
        return TelecomGenerator()

    def test_component_identification(self, generator):
        """Тест определения типа компонента по промпту"""
        test_cases = [
            ("Deploy 5G UPF for Moscow", "5g_upf"),
            ("Deploy User Plane Function", "5g_upf"),
            ("Create AMF deployment", "5g_amf"),
            ("Setup billing system", "billing"),
            ("Deploy RabbitMQ cluster", "rabbitmq"),
            ("Setup Redis cache", "redis"),
            ("Unknown component", "generic"),
        ]

        for prompt, expected_type in test_cases:
            result = generator.identify_component(prompt)
            assert result == expected_type, f"Prompt '{prompt}' должен определяться как '{expected_type}'"

    def test_5g_upf_config(self, generator):
        """Тест конфигурации 5G UPF"""
        config = generator.get_component_config("5g_upf")

        assert config is not None
        assert "description" in config
        assert "resources" in config
        assert config["critical"] is True
        assert "networks" in config
        assert "n3" in config["networks"]
        assert "n4" in config["networks"]
        assert "n6" in config["networks"]

    def test_deployment_yaml_generation(self, generator):
        """Тест генерации Deployment YAML"""
        yaml_content = generator.generate_deployment_yaml(
            component_type="5g_upf",
            service_name="test-upf",
            namespace="telecom"
        )

        assert yaml_content is not None
        assert len(yaml_content) > 0

        # Парсим YAML для валидации
        try:
            manifest = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            pytest.fail(f"Невалидный YAML: {e}")

        # Проверка структуры
        assert manifest["kind"] == "Deployment"
        assert manifest["metadata"]["name"] == "test-upf"
        assert manifest["metadata"]["namespace"] == "telecom"
        assert manifest["spec"]["replicas"] == 3  # 5G UPF critical

    def test_service_yaml_generation(self, generator):
        """Тест генерации Service YAML"""
        yaml_content = generator.generate_service_yaml(
            service_name="test-service",
            namespace="telecom",
            port=8080
        )

        manifest = yaml.safe_load(yaml_content)

        assert manifest["kind"] == "Service"
        assert manifest["metadata"]["name"] == "test-service-service"
        assert manifest["spec"]["ports"][0]["port"] == 8080

    def test_hpa_yaml_generation(self, generator):
        """Тест генерации HPA YAML"""
        yaml_content = generator.generate_hpa_yaml(
            service_name="test-app",
            namespace="telecom",
            min_replicas=3,
            max_replicas=10
        )

        manifest = yaml.safe_load(yaml_content)

        assert manifest["kind"] == "HorizontalPodAutoscaler"
        assert manifest["spec"]["minReplicas"] == 3
        assert manifest["spec"]["maxReplicas"] == 10

    def test_pvc_yaml_generation(self, generator):
        """Тест генерации PVC YAML"""
        yaml_content = generator.generate_pvc_yaml(
            service_name="test-storage",
            namespace="telecom",
            storage="100Gi",
            storage_class="fast-ssd"
        )

        manifest = yaml.safe_load(yaml_content)

        assert manifest["kind"] == "PersistentVolumeClaim"
        assert manifest["spec"]["resources"]["requests"]["storage"] == "100Gi"
        assert manifest["spec"]["storageClassName"] == "fast-ssd"

    def test_network_attachment_definition(self, generator):
        """Тест генерации NetworkAttachmentDefinition"""
        yaml_content = generator.generate_networkattachmentdefinition_yaml(
            network_name="n3",
            namespace="telecom",
            subnet="10.100.0.0/24"
        )

        manifest = yaml.safe_load(yaml_content)

        assert manifest["kind"] == "NetworkAttachmentDefinition"
        assert manifest["metadata"]["name"] == "n3-network"

        # Проверка вложенной JSON конфигурации
        import json
        config = json.loads(manifest["spec"]["config"])
        assert config["ipam"]["subnet"] == "10.100.0.0/24"

    def test_invalid_subnet_format(self, generator):
        """Тест обработки невалидного формата subnet"""
        with pytest.raises(ValueError, match="Invalid subnet format"):
            generator.generate_networkattachmentdefinition_yaml(
                network_name="test",
                namespace="telecom",
                subnet="invalid_subnet"
            )

    def test_full_stack_generation_5g_upf(self, generator):
        """Тест генерации полного стека для 5G UPF"""
        manifests = generator.generate_full_stack(
            component_type="5g_upf",
            service_name="moscow-upf",
            namespace="telecom"
        )

        # Должны быть все необходимые манифесты
        assert "deployment.yaml" in manifests
        assert "service.yaml" in manifests
        assert "hpa.yaml" in manifests  # critical component
        assert "pvc.yaml" in manifests  # имеет storage
        assert "network-attachment.yaml" in manifests  # имеет networks

        # Все должны быть валидным YAML
        for filename, content in manifests.items():
            try:
                list(yaml.safe_load_all(content))
            except yaml.YAMLError as e:
                pytest.fail(f"Невалидный YAML в {filename}: {e}")

    def test_full_stack_generation_billing(self, generator):
        """Тест генерации полного стека для Billing"""
        manifests = generator.generate_full_stack(
            component_type="billing",
            service_name="test-billing",
            namespace="telecom"
        )

        # Биллинг должен иметь секреты (БД, очередь)
        assert "secret.yaml" in manifests

        # Парсим секрет
        secret = yaml.safe_load(manifests["secret.yaml"])
        assert secret["kind"] == "Secret"
        assert "database-url" in secret["stringData"]
        assert "rabbitmq-url" in secret["stringData"]

    def test_docker_image_naming(self):
        """Тест генерации имен Docker образов"""
        image = DockerConfig.get_image_name("5g_upf", "v1.2.3")

        assert image.startswith("registry.mts.ru/")
        assert "5g_upf" in image
        assert "v1.2.3" in image

    def test_network_ip_generation(self):
        """Тест генерации IP адресов для сетей"""
        ip_0 = NetworkConfig.get_ip(0)
        ip_1 = NetworkConfig.get_ip(1)

        assert ip_0.startswith("10.100.")
        assert ip_1.startswith("10.100.")
        assert ip_0 != ip_1

    def test_all_telecom_components_valid(self, generator):
        """Тест что все TELECOM_COMPONENTS валидны"""
        for component_type, config in TELECOM_COMPONENTS.items():
            # Проверка обязательных полей
            assert "description" in config, f"{component_type} должен иметь description"
            assert "resources" in config, f"{component_type} должен иметь resources"
            assert "replicas" in config, f"{component_type} должен иметь replicas"

            # Попытка генерации
            try:
                manifests = generator.generate_full_stack(
                    component_type=component_type,
                    service_name=f"test-{component_type}",
                    namespace="telecom"
                )
                assert len(manifests) > 0
            except Exception as e:
                pytest.fail(f"Не удалось сгенерировать {component_type}: {e}")

    def test_yaml_multiline_handling(self, generator):
        """Тест обработки многострочных YAML документов"""
        manifests = generator.generate_full_stack(
            component_type="5g_upf",
            service_name="test",
            namespace="telecom"
        )

        # NetworkAttachmentDefinition может содержать несколько документов
        if "network-attachment.yaml" in manifests:
            content = manifests["network-attachment.yaml"]
            docs = list(yaml.safe_load_all(content))

            # Должно быть 3 документа (n3, n4, n6 для UPF)
            assert len(docs) == 3

            for doc in docs:
                assert doc["kind"] == "NetworkAttachmentDefinition"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
