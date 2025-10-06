# Телеком шаблоны

Эта папка содержит Jinja2 шаблоны для телеком-специфичных компонентов.

**Примечание:** Телеком-компоненты генерируются программно в `telecom_generator.py`
с использованием встроенных шаблонов для обеспечения гибкости и специфичных настроек.

## Поддерживаемые компоненты:

- **5g_upf** - User Plane Function
- **5g_amf** - Access Mobility Function
- **5g_smf** - Session Management Function
- **billing** - Биллинговая система
- **rabbitmq** - Message Broker
- **redis** - Cache

## Использование:

Генерация выполняется через:
```python
from src.mcp_server.tools.telecom_generator import TelecomGenerator

gen = TelecomGenerator()
manifests = gen.generate_full_stack("5g_upf", "moscow-upf", "telecom")
```

Шаблоны встроены в код для максимальной гибкости настройки телеком-параметров.
