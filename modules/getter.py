"""
Модуль конфигурации и подключения.
Извлекает параметры хостов и SQL-шаблонов из базы данных.
Управляет SSH-сессиями через библиотеку paramiko.
"""
import argparse
import paramiko
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from getpass import getpass
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any
from paramiko import (
    Ed25519Key,
    ECDSAKey,
    RSAKey,
    PasswordRequiredException,
    SSHException,
    AutoAddPolicy,
    RejectPolicy,
)


def _load_private_key(
    path: Path,
    ask_passphrase: bool = True,
) -> Tuple[Optional[paramiko.PKey], str]:
    """
    Загрузить приватный ключ поддерживаемого формата.
    Обработать защиту паролем и верифицировать тип ключа.
    
    Аргументы:
        path: Путь к файлу приватного ключа
        ask_passphrase: Флаг запроса пароля при шифровании ключа
    
    Возвращает:
        Кортеж (объект ключа, код статуса)
    """
    if not path.is_file():
        return None, "ssh_10"
    
    key_classes = [Ed25519Key, ECDSAKey, RSAKey]
    
    for key_class in key_classes:
        try:
            key = key_class.from_private_key_file(str(path))
            return key, "ssh_0"
        except PasswordRequiredException:
            if not ask_passphrase:
                return None, "ssh_12"
            try:
                passphrase = getpass("Passphrase для ключа: ")
                key = key_class.from_private_key_file(str(path), password=passphrase)
                return key, "ssh_0"
            except SSHException:
                return None, "ssh_14"
        except SSHException:
            continue
    
    return None, "ssh_16"


def get_ssh_connection(
    username: str,
    hostname: str,
    key_path: Path,
    timeout: int,
    allow_new_hosts: bool,
) -> Tuple[Optional[paramiko.SSHClient], str]:
    """
    Установить SSH-соединение с удаленным хостом.
    Настроить политику проверки ключей хоста.
    
    Аргументы:
        username: Имя пользователя для аутентификации
        hostname: Адрес удаленного хоста
        key_path: Путь к приватному ключу
        timeout: Таймаут соединения в секундах
        allow_new_hosts: Разрешить автоматическое добавление ключей хостов
    
    Возвращает:
        Кортеж (SSH-клиент, код статуса)
    """
    pkey, load_code = _load_private_key(key_path)
    if pkey is None:
        return None, load_code
    
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    
    if allow_new_hosts:
        client.set_missing_host_key_policy(AutoAddPolicy())
    else:
        client.set_missing_host_key_policy(RejectPolicy())
    
    try:
        client.connect(
            hostname=hostname,
            username=username,
            pkey=pkey,
            timeout=timeout,
            auth_timeout=timeout,
            banner_timeout=timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        return client, "ssh_0"
    except paramiko.AuthenticationException:
        return None, "ssh_20"
    except paramiko.SSHException as e:
        msg = str(e).lower()
        if "host key" in msg or "known_hosts" in msg:
            return None, "ssh_21"
        if "mismatch" in msg or "does not match" in msg:
            return None, "ssh_22"
        if "timed out" in msg or "connect" in msg or "unreachable" in msg:
            return None, "ssh_20"
        return None, "ssh_99"
    except Exception:
        return None, "ssh_99"


def get_sqlite_connection(db_path: Path) -> Tuple[Optional[sqlite3.Connection], int]:
    """
    Проверить целостность файла базы данных SQLite.
    Вернуть соединение или код ошибки.
    
    Аргументы:
        db_path: Путь к файлу базы данных
    
    Возвращает:
        Кортеж (соединение, код статуса SQLite)
    """
    try:
        if not db_path.exists():
            return None, sqlite3.SQLITE_CANTOPEN
        
        db_uri = f"{db_path.as_uri()}?mode=rw"
        conn = sqlite3.connect(db_uri, uri=True)
        
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        check_result = cursor.fetchone()
        
        if check_result is None or check_result[0] != "ok":
            conn.close()
            return None, sqlite3.SQLITE_CORRUPT
        
        return conn, sqlite3.SQLITE_OK
    except sqlite3.Error as sqlite_exc:
        error_code = getattr(sqlite_exc, "sqlite_errorcode", sqlite3.SQLITE_ERROR)
        return None, error_code
    except Exception:
        return None, sqlite3.SQLITE_ERROR


def get_config_for_host(
    host_name: str = None,
    PATH_CONFIG_DB: str = None
) -> Tuple[str, Dict, Dict]:
    """
    Извлечь конфигурацию хоста и переменные окружения из базы данных.
    
    Аргументы:
        host_name: Имя целевого хоста (None = первый активный)
        PATH_CONFIG_DB: Путь к файлу базы конфигурации
    
    Возвращает:
        Кортеж (имя хоста, словарь SSH-переменных, словарь PG-переменных)
    """
    conn = sqlite3.connect(PATH_CONFIG_DB)
    cursor = conn.cursor()
    
    if not host_name:
        cursor.execute("SELECT id, name FROM hosts WHERE toggle = 1;")
    else:
        cursor.execute("SELECT id, name FROM hosts WHERE name = ?;", (host_name,))
    
    host_data = cursor.fetchone()
    if not host_data:
        conn.close()
        raise ValueError("Хост " + str(host_name) + " не найден или не активен.")
    
    host_id, name = host_data
    
    cursor.execute(
        "SELECT variable, value FROM ssh_variables WHERE id_host = ?;",
        (host_id,)
    )
    ssh_vars = dict(cursor.fetchall())
    
    cursor.execute(
        "SELECT variable, value FROM postgre_variables WHERE id_host = ?;",
        (host_id,)
    )
    pg_vars = dict(cursor.fetchall())
    
    conn.close()
    return name, ssh_vars, pg_vars


def get_sql_template(command_name: str, PATH_CONFIG_DB: str = None) -> str:
    """
    Получить текст SQL-шаблона по имени команды.
    
    Аргументы:
        command_name: Имя команды в таблице sql_commands
        PATH_CONFIG_DB: Путь к файлу базы конфигурации
    
    Возвращает:
        Строка SQL-шаблона
    """
    conn = sqlite3.connect(PATH_CONFIG_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT template FROM sql_commands WHERE name = ?;", (command_name,))
    data = cursor.fetchone()
    conn.close()
    
    if not data:
        raise ValueError("Команда " + str(command_name) + " не найдена.")
    
    return data[0]


def get_parse_args():
    """
    Инициализировать парсер аргументов командной строки.
    """
    parser = argparse.ArgumentParser(
        description="Wasserfall CLI: Выполнение запросов в PostgreSQL",
        epilog="Команды смотри в таблице sql_commands базы данных wasserfall_config"
    )
    parser.add_argument("--cmd", required=True, help="Имя SQL команды")
    parser.add_argument("--host", help="Имя конкретного хоста (опционально)")
    parser.add_argument("--workers", type=int, default=5, help="Макс. параллельных хостов default=5")
    parser.add_argument("--var", action="append", help="Переменные шаблона key=value")
    parser.add_argument("--db", action="append", help="Только эти базы")
    parser.add_argument("--db_exclude", action="append", help="Исключить эти базы")
    parser.add_argument(
        "--allow-new-hosts",
        action="store_true",
        help="Разрешить добавление неизвестных хостов в known_hosts"
    )
    return parser.parse_args()


def get_all_active_hosts(root: Path) -> List[str]:
    """
    Выбрать имена всех активных хостов из таблицы hosts.
    
    Аргументы:
        root: Корневая директория проекта для построения пути к БД
    
    Возвращает:
        Список имен хостов
    """
    conn = sqlite3.connect(root / "databases" / "wasserfall_config.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM hosts WHERE toggle = 1;")
    hosts = [row[0] for row in cursor.fetchall()]
    conn.close()
    return hosts


if __name__ == "__main__":
    pass