# common/getter.py

import sqlite3
from pathlib import Path
from typing import Tuple, Optional
import paramiko


# ---------------------------------------------------------
# SQLite connection
# ---------------------------------------------------------
def get_sqlite_connection(path: Path) -> Tuple[Optional[sqlite3.Connection], str]:
    try:
        conn = sqlite3.connect(str(path))
        return conn, "ok"
    except Exception as e:
        return None, f"sqlite_error: {str(e)}"


# ---------------------------------------------------------
# SSH connection
# ---------------------------------------------------------
def get_ssh_connection(
    username: str,
    hostname: str,
    key_path: Path,
    timeout: int,
    allow_new_hosts: bool,
):
    client = paramiko.SSHClient()

    if allow_new_hosts:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    else:
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())

    try:
        client.connect(
            hostname=hostname,
            username=username,
            key_filename=str(key_path),
            timeout=timeout,
        )
        return client, "ssh_0"
    except Exception as e:
        return None, f"ssh_99: {str(e)}"


# ---------------------------------------------------------
# Load host config (SSH + PostgreSQL variables)
# ---------------------------------------------------------
def get_config_for_host(host_name: str, PATH_CONFIG_DB: str):
    conn = sqlite3.connect(PATH_CONFIG_DB)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM hosts WHERE name = ? AND toggle = 1;", (host_name,))
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Host '{host_name}' not found or disabled")

    host_id = row[0]

    cursor.execute(
        "SELECT variable, value FROM ssh_variables WHERE id_host = ?;",
        (host_id,),
    )
    ssh_vars = {var: val for var, val in cursor.fetchall()}

    cursor.execute(
        "SELECT variable, value FROM postgre_variables WHERE id_host = ?;",
        (host_id,),
    )
    pg_vars = {var: val for var, val in cursor.fetchall()}

    conn.close()
    return host_name, ssh_vars, pg_vars


# ---------------------------------------------------------
# Get all active hosts
# ---------------------------------------------------------
def get_all_active_hosts(root: Path):
    db_path = root / "databases" / "wasserfall_config.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM hosts WHERE toggle = 1;")
    hosts = [row[0] for row in cursor.fetchall()]

    conn.close()
    return hosts
