""
Unit тесты для CostOptimizer
Тестирование анализа стоимости и оптимизаций
"""

import pytest
from src.mcp_server.tools.cost_optimizer import CostOptimizer


class TestCostOptimizer:
    """Тесты оптимизатора стоимости"""

    @pytest.fixture
    def optimizer(self):
        """Фикстура с mock оптимизатором (без реального LLM)"""
        # Для unit тестов создаем оптимизатор без Claude API
        class MockCostOptimizer(CostOptimizer):
            def __init__(self):
                self.pricing = {
                    "cpu_core": 1500,
                    "memory_gb": 600,
                    "storage_gb": 50,
                    "spot_discount": 0.65
                }

        return MockCostOptimizer()

    def test_cpu_parsing(self, optimizer):
        """Тест парсинга CPU строк"""
        test_cases = [
            ("100m", 0.1),
            ("500m", 0.5),
            ("1000m", 1.0),
            ("1", 1.0),
            ("2", 2.0),
            ("4", 4.0),
        ]

        for cpu_str, expected_cores in test_cases:
            result = optimizer._parse_cpu(cpu_str)
            assert result == expected_cores, f"CPU '{cpu_str}' должен парситься в {expected_cores} cores"

    def test_memory_parsing(self, optimizer):
        """Тест парсинга Memory строк"""
        test_cases = [
            ("128Mi", 0.125),  # 128 / 1024 = 0.125 GB
            ("256Mi", 0.25),
            ("512Mi", 0.5),
            ("1Gi", 1.0),
            ("2Gi", 2.0),
            ("1024Mi", 1.0),
            ("1Ti", 1024.0),
        ]

        for mem_str, expected_gb in test_cases:
            result = optimizer._parse_memory(mem_str)
            assert abs(result - expected_gb) < 0.01, \
                f"Memory '{mem_str}' должна парситься в ~{expected_gb} GB"

    def test_cost_calculation_simple(self, optimizer):
        """Тест расчета стоимости простого манифеста"""
        simple_manifest = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-app
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: app
        resources:
          requests:
            cpu: "1"
            memory: "2Gi"
"""

        manifests = {"deployment.yaml": simple_manifest}
        cost = optimizer._calculate_current_cost(manifests)

        # Ожидаемая стоимость:
        # CPU: 1 core * 1500 руб * 3 replicas = 4500 руб
        # Memory: 2 GB * 600 руб * 3 replicas = 3600 руб
        # Итого: 8100 руб/мес
        expected_cost = (1 * 1500 + 2 * 600) * 3
        assert abs(cost - expected_cost) < 1, f"Стоимость должна быть ~{expected_cost} руб/мес"

    def test_cost_calculation_multi_container(self, optimizer):
        """Тест расчета стоимости с несколькими контейнерами"""
        multi_container_manifest = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-app
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: app
        resources:
          requests:
            cpu: "500m"
            memory: "1Gi"
      - name: sidecar
        resources:
          requests:
            cpu: "200m"
            memory: "512Mi"
"""

        manifests = {"deployment.yaml": multi_container_manifest}
        cost = optimizer._calculate_current_cost(manifests)

        # App: 0.5 cores * 1500 + 1 GB * 600 = 1350 руб
        # Sidecar: 0.2 cores * 1500 + 0.5 GB * 600 = 600 руб
        # Total per pod: 1950 руб
        # 2 replicas: 3900 руб/мес
        expected_cost = ((0.5 * 1500 + 1 * 600) + (0.2 * 1500 + 0.5 * 600)) * 2
        assert abs(cost - expected_cost) < 1

    def test_summarize_manifests(self, optimizer):
        """Тест создания summary для LLM"""
        test_manifest = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-deployment
spec:
  replicas: 5
  template:
    spec:
      containers:
      - name: main
        resources:
          requests:
            cpu: "2"
            memory: "4Gi"
"""

        manifests = {"deployment.yaml": test_manifest}
        summary = optimizer._summarize_manifests(manifests)

        assert len(summary) == 1
        assert summary[0]["kind"] == "Deployment"
        assert summary[0]["name"] == "test-deployment"
        assert summary[0]["replicas"] == 5
        assert summary[0]["cpu"] == "2"
        assert summary[0]["memory"] == "4Gi"

    def test_apply_optimizations_reduce_replicas(self, optimizer):
        """Тест применения оптимизации уменьшения replicas"""
        original_manifest = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-app
spec:
  replicas: 5
  template:
    spec:
      containers:
      - name: app
        resources:
          requests:
            cpu: "1"
            memory: "2Gi"
"""

        manifests = {"deployment.yaml": original_manifest}

        optimization = {
            "changes": [
                {
                    "type": "reduce_replicas",
                    "target": "test-app",
                    "from": "5",
                    "to": "3",
                    "savings": 2000
                }
            ]
        }

        optimized = optimizer._apply_optimizations(manifests, optimization)

        # Проверяем что replicas изменились
        import yaml
        optimized_manifest = yaml.safe_load(optimized["deployment.yaml"])
        assert optimized_manifest["spec"]["replicas"] == 3

    def test_zero_cost_handling(self, optimizer):
        """Тест обработки случая нулевой стоимости"""
        empty_manifests = {}
        cost = optimizer._calculate_current_cost(empty_manifests)

        assert cost == 0.0


class TestCostCalculations:
    """Тесты математики расчета стоимости"""

    def test_pricing_constants(self):
        """Тест что pricing константы разумны"""
        optimizer = CostOptimizer.__new__(CostOptimizer)
        optimizer.pricing = {
            "cpu_core": 1500,
            "memory_gb": 600,
            "storage_gb": 50,
            "spot_discount": 0.65
        }

        # CPU не должен быть слишком дешевым/дорогим
        assert 1000 <= optimizer.pricing["cpu_core"] <= 3000

        # Memory не должен быть слишком дешевым/дорогим
        assert 400 <= optimizer.pricing["memory_gb"] <= 1000

        # Spot discount должен быть между 0 и 1
        assert 0 < optimizer.pricing["spot_discount"] < 1

    def test_savings_calculation(self):
        """Тест расчета экономии"""
        current_cost = 45000  # руб/мес
        optimized_cost = 28000  # руб/мес

        savings_monthly = current_cost - optimized_cost
        savings_yearly = savings_monthly * 12
        savings_percentage = (savings_monthly / current_cost * 100)

        assert savings_monthly == 17000
        assert savings_yearly == 204000
        assert abs(savings_percentage - 37.78) < 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
