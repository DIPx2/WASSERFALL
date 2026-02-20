PS C:\Users\g.timofeyev\Desktop\WASSERFALL> python PostgreSQL_command_executor/cli/main.py -h
usage: main.py [-h] --cmd CMD [--host HOST] [--workers WORKERS] [--var VAR] [--db DB] [--db_exclude DB_EXCLUDE]

Wasserfall CLI: Выполение запросов в PostgreSQL: параллельно по хостам, последовательно по базам

options:
  -h, --help            	show this help message and exit
  --cmd CMD             	Имя SQL команды
  --host HOST           	Имя конкретного хоста (опционально)
  --workers WORKERS     	Макс. параллельных хостов default=5 (опционально)
  --var VAR             	Переменные шаблона key=value (опционально)
  --db DB               	Только эти базы (если не указано — все пользовательские) (опционально)
  --db_exclude DB_EXCLUDE	Исключить эти базы (опционально)



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