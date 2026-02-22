# common/logger.py

from typing import Any, Dict, Optional
import json
from common.getter import get_sqlite_connection


def log_execution(
    target_host: str,
    query_text: str,
    result: Dict[str, Any],
    code: str,
    logger_db_path,
    database_name: Optional[str] = None,
) -> None:
    conn, conn_code = get_sqlite_connection(logger_db_path)
    if conn is None:
        print(f"[LOGGER] Ошибка подключения к БД логов: {conn_code}")
        return

    cursor = conn.cursor()

    # 1. Создаём запись в execution_tasks
    cursor.execute(
        """
        INSERT INTO execution_tasks (target_host, query_text, database_name)
        VALUES (?, ?, ?);
        """,
        (target_host, query_text, database_name),
    )
    task_id = cursor.lastrowid

    # 2. Подготавливаем данные результата
    exit_code = result.get("exit_code")
    stdout_text = result.get("stdout", "")
    stderr_text = result.get("stderr", "")

    stdout_json = json.dumps(
        {
            "stdout": stdout_text,
            "stderr": stderr_text,
            "exit_code": exit_code,
        },
        ensure_ascii=False,
    )

    # 3. Создаём запись в execution_results
    cursor.execute(
        """
        INSERT INTO execution_results (task_id, pg_code, exit_code, stdout_json, stderr_text)
        VALUES (?, ?, ?, ?, ?);
        """,
        (task_id, code, exit_code, stdout_json, stderr_text),
    )

    conn.commit()
    conn.close()
