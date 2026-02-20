"""
Модуль аудита. Фиксирует каждый запрос и ответ в wasserfall_logger.db.
"""
import sqlite3
import json
import re
from pathlib import Path
from typing import Any, Optional


def _mask_secrets(query: str) -> str:
    """
    Маскирует потенциальные секреты в запросе перед логированием.
    """
    query = re.sub(
        r"password['\"]?\s*[:=]\s*['\"]?[^'\",\s]+",
        "password=***",
        query,
        flags=re.IGNORECASE
    )
    query = re.sub(
        r"PGPASSWORD=['\"]?[^'\",\s]+",
        "PGPASSWORD=***",
        query,
        flags=re.IGNORECASE
    )
    return query


def log_execution(
    target_host: str,
    query_text: str,
    result: dict,
    code: str,
    logger_db_path: Optional[Path] = None,
    database_name: Optional[str] = None
):
    """
    Записывает результат выполнения задачи в базу логов.
    
    Аргументы:
        target_host: Имя хоста
        query_text: Текст запроса (будет замаскирован при наличии секретов)
        result: Словарь с результатами выполнения
        code: Код ошибки (ssh_XX или pg_XX или cmd_XX)
        logger_db_path: Путь к базе логов (опционально)
        database_name: Имя базы данных (опционально)
    """
    if logger_db_path is None:
        logger_db_path = Path(__file__).resolve().parent.parent / "databases" / "wasserfall_logger.db"
    
    masked_query = _mask_secrets(query_text)
    
    conn = sqlite3.connect(str(logger_db_path))
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(execution_tasks)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "database_name" in columns:
        cursor.execute(
            "INSERT INTO execution_tasks (target_host, database_name, query_text) VALUES (?, ?, ?)",
            (target_host, database_name, masked_query)
        )
    else:
        cursor.execute(
            "INSERT INTO execution_tasks (target_host, query_text) VALUES (?, ?)",
            (target_host, masked_query)
        )
    
    task_id = cursor.lastrowid
    
    cursor.execute("""
        INSERT INTO execution_results (task_id, pg_code, exit_code, stdout_json, stderr_text)
        VALUES (?, ?, ?, ?, ?)
    """, (
        task_id,
        code,
        result.get("exit_code"),
        json.dumps(result.get("data"), ensure_ascii=False),
        result.get("stderr")
    ))
    
    conn.commit()
    conn.close()