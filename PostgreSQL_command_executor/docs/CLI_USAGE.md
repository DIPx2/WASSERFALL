Руководство по эксплуатации.

Параметры запуска:
--cmd: Имя SQL-шаблона из базы данных (обязательно).

--host: Запуск на конкретном сервере. Если не указан — выполняется на всех активных хостах.

--workers: Лимит параллельных потоков (по умолчанию 5).

-v key=value: Передача аргументов в SQL-шаблон.

Примеры:
PowerShell

usage: python.exe -m cli.main [-h] --cmd CMD [--host HOST] [--workers WORKERS] [-v VAR]

# Выполнение команды на всех активных хостах:
PS C:\Users\g.timofeyev\Desktop\WASSERFALL\PostgreSQL_command_executor> python -m cli.main --cmd CHECK_HEALTH
                            PS C:\Users\g.timofeyev\Desktop\WASSERFALL> python -m PostgreSQL_command_executor.cli.main --cmd CHECK_HEALTH


# Сбор размеров баз в 10 потоков
python cli/main.py --cmd DB_SIZES --workers 10
# Топ самых больших баз данных в количество потоков по умолчанию
python PostgreSQL_command_executor/cli/main.py --cmd TOP_10_TABLES --host prd-msg-pg-03.maxbit.private


Если установить лимит в табл sql_commands
LIMIT {{ limit_val | default(1) | int }}
Проверка всех серверов с лимитом в 5 строк
python cli/main.py --cmd CHECK_HEALTH --var limit_val=5