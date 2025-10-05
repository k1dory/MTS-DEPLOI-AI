"""
Телеком-генератор для создания K8s манифестов телеком-компонентов
Специализируется на 5G компонентах, биллинге, RabbitMQ и других телеком-сервисах
"""

from typing import Dict, Any, List
from pathlib import Path
import yaml
import logging
from jinja2 import Template

from ..config import SecretsConfig, DockerConfig, NetworkConfig

logger = logging.getLogger(__name__)

# Конфигурации телеком-компонентов
TELECOM_COMPONENTS = {
    "5g_upf": {
        "description": "5G User Plane Function - обработка пользовательского трафика",
        "resources": {
            "cpu_min": "4",
            "cpu_max": "8",
            "memory_min": "8Gi",
            "memory_max": "16Gi"
        },
        "replicas": 3,
        "networks": ["n3", "n4", "n6"],  # Интерфейсы 5G
        "capabilities": ["NET_ADMIN", "SYS_ADMIN"],
        "storage": "100Gi",
        "storage_class": "fast-ssd",
        "critical": True,
        "priority": "system-cluster-critical"
    },

    "5g_amf": {
        "description": "5G Access and Mobility Management Function",
        "resources": {
            "cpu_min": "2",
            "cpu_max": "4",
            "memory_min": "4Gi",
            "memory_max": "8Gi"
        },
        "replicas": 3,
        "networks": ["n1", "n2"],
        "capabilities": ["NET_ADMIN"],
        "critical": True,
        "priority": "system-cluster-critical"
    },

    "5g_smf": {
        "description": "5G Session Management Function",
        "resources": {
            "cpu_min": "2",
            "cpu_max": "4",
            "memory_min": "4Gi",
            "memory_max": "8Gi"
        },
        "replicas": 3,
        "networks": ["n4", "n7"],
        "capabilities": ["NET_ADMIN"],
        "critical": True,
        "priority": "system-cluster-critical"
    },

    "billing": {
        "description": "Биллинговая система для тарификации",
        "resources": {
            "cpu_min": "1",
            "cpu_max": "4",
            "memory_min": "2Gi",
            "memory_max": "8Gi"
        },
        "replicas": 3,
        "needs_database": True,
        "needs_cache": True,
        "needs_queue": True,
        "critical": True,
        "priority": "high-priority"
    },

    "rabbitmq": {
        "description": "Message broker для межсервисного взаимодействия",
        "type": "StatefulSet",
        "resources": {
            "cpu_min": "1",
            "cpu_max": "2",
            "memory_min": "2Gi",
            "memory_max": "4Gi"
        },
        "replicas": 3,
        "storage": "100Gi",
        "storage_class": "fast-ssd",
        "ports": [5672, 15672, 25672]
    },

    "redis": {
        "description": "Кэш для быстрого доступа к данным",
        "type": "StatefulSet",
        "resources": {
            "cpu_min": "500m",
            "cpu_max": "2",
            "memory_min": "1Gi",
            "memory_max": "4Gi"
        },
        "replicas": 3,
        "storage": "20Gi",
        "storage_class": "fast-ssd"
    }
}


class TelecomGenerator:
    """Генератор телеком-конфигураций"""

    def __init__(self, templates_dir: str = "templates/telecom"):
        self.templates_dir = Path(templates_dir)
        self.base_templates_dir = Path("templates/k8s")

    def identify_component(self, prompt: str) -> str:
        """
        Определяет тип компонента из промпта

        Args:
            prompt: Текст запроса

        Returns:
            Тип компонента или 'generic'
        """
        prompt_lower = prompt.lower()

        # Поиск по ключевым словам
        if any(word in prompt_lower for word in ["upf", "user plane"]):
            return "5g_upf"
        elif any(word in prompt_lower for word in ["amf", "access mobility"]):
            return "5g_amf"
        elif any(word in prompt_lower for word in ["smf", "session management"]):
            return "5g_smf"
        elif any(word in prompt_lower for word in ["billing", "биллинг", "тарификация"]):
            return "billing"
        elif "rabbitmq" in prompt_lower:
            return "rabbitmq"
        elif "redis" in prompt_lower:
            return "redis"
        else:
            return "generic"

    def get_component_config(self, component_type: str) -> Dict[str, Any]:
        """Получить конфигурацию компонента"""
        return TELECOM_COMPONENTS.get(component_type, {})

    def generate_deployment_yaml(
        self,
        component_type: str,
        service_name: str,
        namespace: str = "telecom",
        custom_params: Dict[str, Any] | None = None
    ) -> str:
        """
        Генерирует Deployment YAML для телеком-компонента

        Args:
            component_type: Тип компонента
            service_name: Имя сервиса
            namespace: Namespace K8s
            custom_params: Дополнительные параметры

        Returns:
            YAML манифест
        """
        config = self.get_component_config(component_type)
        if custom_params:
            config = {**config, **custom_params}

        # Базовый шаблон Deployment
        template_str = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ service_name }}
  namespace: {{ namespace }}
  labels:
    app: {{ service_name }}
    component: {{ component_type }}
    operator: mts
    tier: telecom
spec:
  replicas: {{ replicas }}
  selector:
    matchLabels:
      app: {{ service_name }}

  template:
    metadata:
      labels:
        app: {{ service_name }}
        component: {{ component_type }}
        version: v1
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9090"
        prometheus.io/path: "/metrics"
        {% if networks %}
        # Multus CNI для множественных сетевых интерфейсов
        k8s.v1.cni.cncf.io/networks: |
          [
            {% for net in networks %}
            {
              "name": "{{ net }}-network",
              "interface": "{{ net }}",
              "ips": ["{{ network_ips[loop.index0] }}/24"]
            }{% if not loop.last %},{% endif %}
            {% endfor %}
          ]
        {% endif %}

    spec:
      {% if critical %}
      # Высокая доступность - каждый pod на отдельном узле
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchExpressions:
              - key: app
                operator: In
                values:
                - {{ service_name }}
            topologyKey: kubernetes.io/hostname
      {% endif %}

      {% if priority %}
      priorityClassName: {{ priority }}
      {% endif %}

      containers:
      - name: {{ component_type }}
        image: {{ docker_image }}
        imagePullPolicy: IfNotPresent

        resources:
          requests:
            cpu: "{{ resources.cpu_min }}"
            memory: "{{ resources.memory_min }}"
          limits:
            cpu: "{{ resources.cpu_max }}"
            memory: "{{ resources.memory_max }}"

        {% if networks or needs_database or needs_cache or needs_queue %}
        env:
        {% if networks %}
        {% for net in networks %}
        - name: {{ net | upper }}_IP
          value: "{{ network_ips[loop.index0] }}"
        {% endfor %}
        {% endif %}
        - name: COMPONENT_TYPE
          value: "{{ component_type }}"
        - name: LOG_LEVEL
          value: "INFO"
        {% if needs_database %}
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: {{ service_name }}-secrets
              key: database-url
        {% endif %}
        {% if needs_cache %}
        - name: REDIS_URL
          value: "redis://redis-service:6379"
        {% endif %}
        {% if needs_queue %}
        - name: RABBITMQ_URL
          valueFrom:
            secretKeyRef:
              name: {{ service_name }}-secrets
              key: rabbitmq-url
        {% endif %}
        {% endif %}

        ports:
        - containerPort: 8080
          name: http
          protocol: TCP
        - containerPort: 9090
          name: metrics
          protocol: TCP

        # Health checks
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 60
          periodSeconds: 30
          timeoutSeconds: 5
          failureThreshold: 3

        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 3
          failureThreshold: 3

        {% if capabilities %}
        securityContext:
          capabilities:
            add:
            {% for cap in capabilities %}
            - {{ cap }}
            {% endfor %}
          runAsNonRoot: false
        {% endif %}

        {% if storage %}
        volumeMounts:
        - name: data
          mountPath: /var/lib/{{ component_type }}
        {% endif %}

      {% if storage %}
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: {{ service_name }}-pvc
      {% endif %}
"""

        # Генерируем IP адреса для сетей
        network_ips = []
        if config.get('networks'):
            for idx in range(len(config['networks'])):
                network_ips.append(NetworkConfig.get_ip(100 + idx))

        template = Template(template_str)
        yaml_content = template.render(
            component_type=component_type,
            service_name=service_name,
            namespace=namespace,
            docker_image=DockerConfig.get_image_name(component_type),
            network_ips=network_ips,
            **config
        )

        return yaml_content.strip()

    def generate_service_yaml(
        self,
        service_name: str,
        namespace: str = "telecom",
        port: int = 8080
    ) -> str:
        """Генерирует Service YAML"""

        yaml_content = f"""
apiVersion: v1
kind: Service
metadata:
  name: {service_name}-service
  namespace: {namespace}
  labels:
    app: {service_name}
    operator: mts
spec:
  selector:
    app: {service_name}
  ports:
  - name: http
    port: {port}
    targetPort: 8080
    protocol: TCP
  - name: metrics
    port: 9090
    targetPort: 9090
    protocol: TCP
  type: ClusterIP
  sessionAffinity: ClientIP
"""
        return yaml_content.strip()

    def generate_hpa_yaml(
        self,
        service_name: str,
        namespace: str = "telecom",
        min_replicas: int = 3,
        max_replicas: int = 10
    ) -> str:
        """Генерирует HorizontalPodAutoscaler YAML"""

        yaml_content = f"""
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {service_name}-hpa
  namespace: {namespace}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {service_name}
  minReplicas: {min_replicas}
  maxReplicas: {max_replicas}
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
"""
        return yaml_content.strip()

    def generate_pvc_yaml(
        self,
        service_name: str,
        namespace: str = "telecom",
        storage: str = "100Gi",
        storage_class: str = "fast-ssd"
    ) -> str:
        """Генерирует PersistentVolumeClaim YAML"""

        yaml_content = f"""
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {service_name}-pvc
  namespace: {namespace}
spec:
  accessModes:
  - ReadWriteOnce
  storageClassName: {storage_class}
  resources:
    requests:
      storage: {storage}
"""
        return yaml_content.strip()

    def generate_networkattachmentdefinition_yaml(
        self,
        network_name: str,
        namespace: str = "telecom",
        subnet: str = "10.100.0.0/24"
    ) -> str:
        """Генерирует NetworkAttachmentDefinition для Multus CNI"""

        # Безопасный парсинг subnet
        try:
            subnet_parts = subnet.split('/')
            if len(subnet_parts) != 2:
                raise ValueError(f"Invalid subnet format: {subnet}. Expected CIDR notation (e.g., 10.100.0.0/24)")

            ip_part = subnet_parts[0]
            cidr = subnet_parts[1]

            if '.' not in ip_part:
                raise ValueError(f"Invalid IP in subnet: {ip_part}")

            base_ip = ip_part.rsplit('.', 1)[0]
        except Exception as e:
            logger.error(f"Error parsing subnet {subnet}: {e}")
            raise ValueError(f"Invalid subnet format: {subnet}") from e

        yaml_content = f"""
apiVersion: k8s.cni.cncf.io/v1
kind: NetworkAttachmentDefinition
metadata:
  name: {network_name}-network
  namespace: {namespace}
spec:
  config: |
    {{
      "cniVersion": "0.3.1",
      "type": "macvlan",
      "master": "eth1",
      "mode": "bridge",
      "ipam": {{
        "type": "host-local",
        "subnet": "{subnet}",
        "rangeStart": "{base_ip}.10",
        "rangeEnd": "{base_ip}.100",
        "gateway": "{base_ip}.1"
      }}
    }}
"""
        return yaml_content.strip()

    def generate_full_stack(
        self,
        component_type: str,
        service_name: str,
        namespace: str = "telecom"
    ) -> Dict[str, str]:
        """
        Генерирует полный набор манифестов для телеком-компонента

        Returns:
            Dict с именами файлов и их содержимым
        """
        config = self.get_component_config(component_type)
        manifests = {}

        # 1. Deployment
        manifests["deployment.yaml"] = self.generate_deployment_yaml(
            component_type, service_name, namespace
        )

        # 2. Service
        manifests["service.yaml"] = self.generate_service_yaml(
            service_name, namespace
        )

        # 3. HPA (если критический сервис)
        if config.get("critical"):
            manifests["hpa.yaml"] = self.generate_hpa_yaml(
                service_name,
                namespace,
                min_replicas=config.get("replicas", 3),
                max_replicas=config.get("replicas", 3) * 3
            )

        # 4. PVC (если нужно хранилище)
        if config.get("storage"):
            manifests["pvc.yaml"] = self.generate_pvc_yaml(
                service_name,
                namespace,
                storage=config["storage"],
                storage_class=config.get("storage_class", "standard")
            )

        # 5. NetworkAttachmentDefinition (если есть сети)
        if config.get("networks"):
            nad_manifests = []
            for idx, net in enumerate(config["networks"]):
                subnet = NetworkConfig.get_subnet(100 + idx)
                nad_yaml = self.generate_networkattachmentdefinition_yaml(
                    net, namespace, subnet
                )
                nad_manifests.append(nad_yaml)
            manifests["network-attachment.yaml"] = "\n---\n".join(nad_manifests)

        # 6. Secret (если нужна БД/очередь)
        if config.get("needs_database") or config.get("needs_queue"):
            manifests["secret.yaml"] = self._generate_secret_yaml(
                service_name, namespace, config
            )

        return manifests

    def _generate_secret_yaml(
        self,
        service_name: str,
        namespace: str,
        config: Dict[str, Any]
    ) -> str:
        """Генерирует Secret YAML"""

        yaml_content = f"""
apiVersion: v1
kind: Secret
metadata:
  name: {service_name}-secrets
  namespace: {namespace}
type: Opaque
stringData:
"""

        if config.get("needs_database"):
            db_url = SecretsConfig.DEMO_DATABASE_URL_TEMPLATE.format(
                password=SecretsConfig.get_placeholder('PASSWORD')
            )
            yaml_content += f"""  database-url: "{db_url}"
"""

        if config.get("needs_queue"):
            rabbitmq_url = SecretsConfig.DEMO_RABBITMQ_URL_TEMPLATE.format(
                password=SecretsConfig.get_placeholder('PASSWORD')
            )
            yaml_content += f"""  rabbitmq-url: "{rabbitmq_url}"
"""

        return yaml_content.strip()
