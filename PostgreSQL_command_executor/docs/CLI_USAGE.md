Руководство по эксплуатации.

Параметры запуска:
--cmd: Имя SQL-шаблона из базы данных (обязательно).

--host: Запуск на конкретном сервере. Если не указан — выполняется на всех активных хостах.

--workers: Лимит параллельных потоков (по умолчанию 5).

-v key=value: Передача аргументов в SQL-шаблон.

Примеры:
PowerShell
# Проверка всех серверов с лимитом в 1 строку
python cli/main.py --cmd CHECK_HEALTH --var limit_val=1

# Сбор размеров баз в 10 потоков
python cli/main.py --cmd DB_SIZES --workers 10

# Топ самых больших баз данных в количество потоков по умолчанию
python cli/main.py --cmd TOP_TABLES --host tor-dev-pg-01.torus.private

# Выполнение команды на всех активных хостах:
python cli/main.py --cmd CHECK_HEALTH