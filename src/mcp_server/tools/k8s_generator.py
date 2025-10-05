"""
Генератор стандартных Kubernetes манифестов
Для обычных (не телеком-специфичных) приложений
"""

from typing import Dict


class K8sManifestGenerator:
    """Генератор базовых K8s манифестов"""

    def generate_basic_deployment(
        self,
        service_name: str,
        image: str,
        replicas: int = 3,
        port: int = 8080,
        namespace: str = "default"
    ) -> Dict[str, str]:
        """
        Генерирует базовый Deployment + Service + ConfigMap

        Args:
            service_name: Имя сервиса
            image: Docker образ
            replicas: Количество реплик
            port: Порт приложения
            namespace: Namespace K8s

        Returns:
            Dict с манифестами
        """
        manifests = {}

        # Deployment
        manifests["deployment.yaml"] = f"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {service_name}
  namespace: {namespace}
  labels:
    app: {service_name}
spec:
  replicas: {replicas}
  selector:
    matchLabels:
      app: {service_name}
  template:
    metadata:
      labels:
        app: {service_name}
    spec:
      containers:
      - name: {service_name}
        image: {image}
        ports:
        - containerPort: {port}
          name: http
        resources:
          requests:
            cpu: "100m"
            memory: "128Mi"
          limits:
            cpu: "500m"
            memory: "512Mi"
        livenessProbe:
          httpGet:
            path: /health
            port: {port}
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: {port}
          initialDelaySeconds: 5
          periodSeconds: 5
""".strip()

        # Service
        manifests["service.yaml"] = f"""
apiVersion: v1
kind: Service
metadata:
  name: {service_name}
  namespace: {namespace}
spec:
  selector:
    app: {service_name}
  ports:
  - port: 80
    targetPort: {port}
    protocol: TCP
  type: ClusterIP
""".strip()

        # ConfigMap
        manifests["configmap.yaml"] = f"""
apiVersion: v1
kind: ConfigMap
metadata:
  name: {service_name}-config
  namespace: {namespace}
data:
  app.conf: |
    PORT={port}
    LOG_LEVEL=INFO
""".strip()

        return manifests
