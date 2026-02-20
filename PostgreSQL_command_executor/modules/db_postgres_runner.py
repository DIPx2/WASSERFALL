"""
Модуль выполнения SQL-запросов к СУБД PostgreSQL через SSH-туннель.
PG-специфичный модуль — не перемещать в общие модули!
"""
from __future__ import annotations
import json
import shlex
from typing import Optional, Tuple, Any, Dict


def _parse_psql_error(stderr: str, exit_code: int) -> str:
    """Анализировать stderr и классифицировать ошибку PostgreSQL."""
    err = stderr.lower()
    
    if "psql: not found" in err or "command not found" in err:
        return "pg_10"
    if "fatal" in err and "password" in err:
        return "pg_12"
    if "fatal" in err and ("could not connect" in err or "no route" in err):
        return "pg_16"
    if "syntax error" in err or "error:" in err:
        return "pg_14"
    
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
    """Выполнить SQL-запрос на удалённом хосте через SSH-соединение."""
    psql_flags = f"-U {shlex.quote(db_user)} -d {shlex.quote(db_name)} -p {db_port} -t -q -A -v ON_ERROR_STOP=1"
    env_vars = f"PGPASSWORD={shlex.quote(db_password)} " if db_password else ""
    wrapped_sql = f"SELECT json_agg(t) FROM ({sql.strip().rstrip(';')}) t;"
    inner_cmd = f"{env_vars}{psql_path} {psql_flags} < <'__PGSQL_HEREDOC__'\n{wrapped_sql}\n__PGSQL_HEREDOC__"
    full_cmd = f"su - postgres -c {shlex.quote(inner_cmd)}"
    
    try:
        stdin, stdout, stderr = ssh_client.exec_command(full_cmd)
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()
    except Exception:
        return {"data": None, "stderr": "SSH Execution Failed", "exit_code": -1}, "ssh_99"
    
    res = {"data": None, "stderr": err, "exit_code": exit_code}
    
    if exit_code == 0:
        try:
            res["data"] = json.loads(out) if out else []
            return res, "pg_0"
        except json.JSONDecodeError:
            res["data"] = out
            return res, "pg_0"
    
    return res, _parse_psql_error(err, exit_code)


def get_user_databases(client, pg_vars) -> list:
    """Получить список пользовательских баз данных через системное представление."""
    sql = """
    SELECT datname FROM pg_stat_database
    WHERE datname NOT IN ('postgres', 'template0', 'template1')
    ORDER BY datname;
    """
    result, code = run_postgres_command_over_ssh(
        ssh_client=client,
        sql=sql,
        db_user=pg_vars.get('PG_DB_USER', 'postgres'),
        db_port=int(pg_vars.get('PG_DB_PORT', 5432)),
        db_name=pg_vars.get('PG_DB_DEFAULT', 'postgres'),
        psql_path=pg_vars.get('PG_PSQL_PATH', '/usr/bin/psql'),
    )
    
    if code != "pg_0":
        print("Не удалось получить список баз: " + code)
        return []
    
    databases = []
    data = result.get("data", [])
    
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict) and "datname" in row:
                databases.append(row["datname"])
            elif isinstance(row, str):
                databases.append(row)
    
    return sorted(set(databases))