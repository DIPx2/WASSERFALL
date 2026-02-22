# command_executor_postgresql/modules/getter.py

import argparse
import sqlite3
from typing import Dict


def get_parse_args():
    parser = argparse.ArgumentParser(
        description="PostgreSQL Orchestration Engine — выполнение SQL-команд на удалённых хостах"
    )

    parser.add_argument(
        "--cmd",
        required=True,
        help="Имя SQL-команды из таблицы commands"
    )

    parser.add_argument(
        "--host",
        help="Конкретный хост (иначе все активные)"
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Количество параллельных потоков"
    )

    parser.add_argument(
        "--var",
        action="append",
        help="Переменные шаблона key=value"
    )

    parser.add_argument(
        "--db",
        action="append",
        help="Список конкретных баз данных"
    )

    parser.add_argument(
        "--db-exclude",
        action="append",
        help="Список баз, которые нужно исключить"
    )

    parser.add_argument(
        "--allow-new-hosts",
        action="store_true",
        help="Разрешить добавление новых хостов в known_hosts"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Показать подробный вывод (JSON‑данные по каждой БД)"
    )

    return parser.parse_args()


def get_sql_template(command_name: str, PATH_CONFIG_DB: str) -> str:
    conn = sqlite3.connect(PATH_CONFIG_DB)
    cursor = conn.cursor()

    cursor.execute("SELECT template FROM commands WHERE name = ?;", (command_name,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise ValueError(f"SQL-команда '{command_name}' не найдена в таблице commands")

    return row[0]


def get_user_databases(client, pg_vars: Dict[str, str]):
    stdin, stdout, stderr = client.exec_command(
        "su - postgres -c \"psql -t -A -c 'SELECT datname FROM pg_database WHERE datistemplate = false;'\""
    )

    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()

    if err:
        raise RuntimeError(f"Ошибка получения списка баз данных: {err}")

    return [db.strip() for db in out.splitlines() if db.strip()]
