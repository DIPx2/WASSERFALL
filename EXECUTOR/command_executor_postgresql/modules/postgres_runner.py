"""
Модуль выполнения SQL-запросов к СУБД PostgreSQL через SSH-туннель.
Инкапсулирует логику удалённого исполнения psql-команд, парсинга ответов и классификации ошибок.
"""
from __future__ import annotations
import json
import shlex
from typing import Optional, Tuple, Any, Dict


def _parse_psql_error(stderr: str, exit_code: int) -> str:
    """Анализировать stderr и классифицировать ошибку PostgreSQL по коду.

    Аргументы:
        stderr: Текст ошибки от psql
        exit_code: Код возврата процесса

    Возвращает:
        Строковый код ошибки (pg_XX) согласно внутренней классификации
    """
    err = stderr.lower()
    # Определить ошибку отсутствия исполняемого файла psql
    if "psql: not found" in err or "command not found" in err:
        return "pg_10"
    # Определить ошибку аутентификации по паролю
    if "fatal" in err and "password" in err:
        return "pg_12"
    # Определить ошибку сетевого подключения к серверу
    if "fatal" in err and ("could not connect" in err or "no route" in err):
        return "pg_16"
    # Определить синтаксическую ошибку SQL-запроса
    if "syntax error" in err or "error:" in err:
        return "pg_14"
    # Вернуть общий код ошибки при ненулевом exit_code или неизвестную ошибку
    return "pg_18" if exit_code != 0 else "pg_99"


def run_postgres_command_over_ssh(
    ssh_client,
    sql: str,
    db_user: str,
    db_name: str,
    db_port: int,
    psql_path: str,
    db_password: Optional[str] = None
) -> Tuple[Dict[str, Any], str]:
    """Выполнить SQL-запрос на удалённом хосте через SSH-соединение.

    Аргументы:
        ssh_client: Активный SSH-клиент paramiko
        sql: Текст SQL-запроса для выполнения
        db_user: Имя пользователя PostgreSQL
        db_name: Имя целевой базы данных
        db_port: Порт подключения к PostgreSQL
        psql_path: Полный путь к исполняемому файлу psql
        db_password: Пароль базы данных (опционально)

    Возвращает:
        Кортеж (словарь результата, код ошибки pg_XX)
    """
    # Сформировать флаги командной строки psql для неинтерактивного режима
    psql_flags = f"-U {shlex.quote(db_user)} -d {shlex.quote(db_name)} -p {db_port} -t -q -A -v ON_ERROR_STOP=1"
    # Экспортировать пароль через переменную окружения при наличии
    env_vars = f"PGPASSWORD={shlex.quote(db_password)} " if db_password else ""
    # Обернуть запрос в агрегирующую функцию для гарантированного JSON-вывода
    wrapped_sql = f"SELECT json_agg(t) FROM ({sql.strip().rstrip(';')}) t;"

    # Сформировать команду с heredoc для безопасной передачи многострочного SQL
    inner_cmd = f"{env_vars}{psql_path} {psql_flags} <<'__PGSQL_HEREDOC__'\n{wrapped_sql}\n__PGSQL_HEREDOC__"
    # Выполнить команду от имени системного пользователя postgres через su
    full_cmd = f"su - postgres -c {shlex.quote(inner_cmd)}"

    try:
        # Инициировать выполнение команды на удалённом хосте
        stdin, stdout, stderr = ssh_client.exec_command(full_cmd)
        # Прочитать стандартный вывод и поток ошибок с заменой некорректных символов
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        # Получить код завершения процесса
        exit_code = stdout.channel.recv_exit_status()
    except Exception:
        # Вернуть ошибку выполнения SSH-команды
        return {"data": None, "stderr": "SSH Execution Failed", "exit_code": -1}, "ssh_99"

    # Инициализировать словарь результата стандартными полями
    res = {"data": None, "stderr": err, "exit_code": exit_code}

    if exit_code == 0:
        try:
            # Попытаться распарсить вывод как JSON-массив
            res["data"] = json.loads(out) if out else []
            return res, "pg_0"
        except json.JSONDecodeError:
            # Сохранить сырой вывод при неудаче парсинга JSON
            res["data"] = out
            return res, "pg_0"

    # Классифицировать ошибку по тексту stderr и коду возврата
    return res, _parse_psql_error(err, exit_code)