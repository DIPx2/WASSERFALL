import sqlite3
import json
from pathlib import Path

LOGGER_DB = Path(__file__).resolve().parent.parent / "databases" / "wasserfall_logger.db"

def log_execution(target_host: str, query: str, result: dict, code: str):
    conn = sqlite3.connect(LOGGER_DB)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO execution_tasks (target_host, query_text) VALUES (?, ?)", (target_host, query))
    task_id = cursor.lastrowid
    
    cursor.execute("""
        INSERT INTO execution_results (task_id, pg_code, exit_code, stdout_json, stderr_text)
        VALUES (?, ?, ?, ?, ?)
    """, (task_id, code, result.get("exit_code"), 
          json.dumps(result.get("data"), ensure_ascii=False), result.get("stderr")))
    conn.commit()
    conn.close()