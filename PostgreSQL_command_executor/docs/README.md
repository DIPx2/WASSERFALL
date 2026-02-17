Wasserfall: PostgreSQL Orchestration Engine - это инструмент для параллельного управления парком серверов PostgreSQL через SSH. Система построена на принципе Data-Driven Automation: все настройки подключений, параметры сред и SQL-шаблоны хранятся во внешней базе данных SQLite.

Ключевые компоненты:
cli/main.py: Точка входа. Управляет жизненным циклом выполнения и распределяет задачи по потокам через ThreadPoolExecutor.
modules/getter.py: "Config Provider". Отвечает за извлечение параметров хостов и SQL-шаблонов из БД.
modules/template_engine.py: Использует Jinja2 для рендеринга динамических SQL-запросов.
modules/db_postgres_runner.py: Исполнитель. Выполняет SQL через SSH и агрегирует результат в JSON.
modules/logger.py: Модуль аудита. Фиксирует каждый запрос и ответ в wasserfall_logger.db.