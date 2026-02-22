"""
Модуль выполнения SQL‑запросов к PostgreSQL через SSH‑туннель.
Гарантирует единый формат результата:
{
    "stdout": <str>,      # сырой stdout psql
    "stderr": <str>,      # stderr psql
    "exit_code": <int>,   # код возврата процесса
    "data": <list|str|None>  # распарсенный JSON или сырой текст
}
"""

from __future__ import annotations
import json
import shlex
from typing import Optional, Tuple, Any, Dict


def _parse_psql_error(stderr: str, exit_code: int) -> str:
    """
    Классификация ошибок PostgreSQL по тексту stderr и коду возврата.
    Возвращает строковый код pg_XX.
    """
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
    db_password: Optional[str] = None,
) -> Tuple[Dict[str, Any], str]:
    """
    Выполнить SQL‑запрос на удалённом хосте через SSH.
    Возвращает (dict result, str pg_code).
    """

    psql_flags = (
        f"-U {shlex.quote(db_user)} "
        f"-d {shlex.quote(db_name)} "
        f"-p {db_port} -t -q -A -v ON_ERROR_STOP=1"
    )

    env_vars = f"PGPASSWORD={shlex.quote(db_password)} " if db_password else ""

    wrapped_sql = f"SELECT json_agg(t) FROM ({sql.strip().rstrip(';')}) t;"

    inner_cmd = (
        f"{env_vars}{psql_path} {psql_flags} <<'__PGSQL_HEREDOC__'\n"
        f"{wrapped_sql}\n"
        f"__PGSQL_HEREDOC__"
    )

    full_cmd = f"su - postgres -c {shlex.quote(inner_cmd)}"

    try:
        stdin, stdout, stderr = ssh_client.exec_command(full_cmd)

        raw_out = stdout.read().decode("utf-8", errors="replace").strip()
        raw_err = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()

    except Exception:
        return {
            "stdout": "",
            "stderr": "SSH Execution Failed",
            "exit_code": -1,
            "data": None,
        }, "ssh_99"

    result: Dict[str, Any] = {
        "stdout": raw_out,
        "stderr": raw_err,
        "exit_code": exit_code,
        "data": None,
    }

    if exit_code == 0:
        try:
            result["data"] = json.loads(raw_out) if raw_out else []
            return result, "pg_0"
        except json.JSONDecodeError:
            result["data"] = raw_out
            return result, "pg_0"

    return result, _parse_psql_error(raw_err, exit_code)
