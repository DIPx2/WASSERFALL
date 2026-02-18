"""
Выполнение SQL-запросов к СУБД PostgreSQL через SSH.
"""

from __future__ import annotations
import json
import shlex
from typing import Optional, Tuple, Any, Dict

def _parse_psql_error(stderr: str, exit_code: int) -> str:
    err = stderr.lower()
    if "psql: not found" in err or "command not found" in err: return "pg_10"
    if "fatal" in err and "password" in err: return "pg_12"
    if "fatal" in err and ("could not connect" in err or "no route" in err): return "pg_16"
    if "syntax error" in err or "error:" in err: return "pg_14"
    return "pg_18" if exit_code != 0 else "pg_99"

def run_postgres_command_over_ssh(
    ssh_client, 
    sql: str, 
    db_user: str,      # Обязательный параметр
    db_name: str,      # Обязательный параметр
    db_port: int,      # Обязательный параметр
    psql_path: str,    # Обязательный параметр
    db_password: Optional[str] = None
) -> Tuple[Dict[str, Any], str]:
    psql_flags = f"-U {shlex.quote(db_user)} -d {shlex.quote(db_name)} -p {db_port} -t -q -A -v ON_ERROR_STOP=1"
    env_vars = f"PGPASSWORD={shlex.quote(db_password)} " if db_password else ""
    wrapped_sql = f"SELECT json_agg(t) FROM ({sql.strip().rstrip(';')}) t;"
    """
    wrapped_sql - обертывание запроса:
    Исходный SQL-запрос оборачивается в конструкцию SELECT json_agg(t) FROM (...) t;. 
    Это заставляет PostgreSQL вернуть результат в формате JSON, что упрощает парсинг.
    """

    """
    Формирование команды Shell:
    формируются флаги psql: -t (только кортежи), -q (тихий режим), -A (без выравнивания).
    Команда psql запускается через su - postgres -c ... для смены пользователя на системном уровне.
    SQL передается через Here-Doc (<<'__PGSQL_HEREDOC__') для избежания проблем с кавычками.
    """
    inner_cmd = f"{env_vars}{psql_path} {psql_flags} <<'__PGSQL_HEREDOC__'\n{wrapped_sql}\n__PGSQL_HEREDOC__"
    full_cmd = f"su - postgres -c {shlex.quote(inner_cmd)}"

    """
    Исполнение через SSH:
    команда выполняется методом ssh_client.exec_command().
    Считываются stdout, stderr и код возврата (exit_code).
    """
    try:
        stdin, stdout, stderr = ssh_client.exec_command(full_cmd)
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()
    except Exception:
        return {"data": None, "stderr": "SSH Execution Failed", "exit_code": -1}, "ssh_99"

    res = {"data": None, "stderr": err, "exit_code": exit_code}

    if exit_code == 0:
        """
        Если exit_code == 0: stdout парсится как JSON.
        Если возникла ошибка: функция _parse_psql_error анализирует текст ошибки 
        (например, "fatal", "syntax error") 
        и возвращает внутренний код ошибки (например, pg_14, pg_16).
        """
        try:
            res["data"] = json.loads(out) if out else []
            return res, "pg_0"
        except json.JSONDecodeError:
            res["data"] = out
            return res, "pg_0"
    
    return res, _parse_psql_error(err, exit_code)