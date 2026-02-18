import sqlite3
import paramiko
from getpass import getpass
from pathlib import Path
from typing import Tuple, Optional
from paramiko import (
    Ed25519Key,
    ECDSAKey,
    RSAKey,
    PasswordRequiredException,
    SSHException,
    AutoAddPolicy,
    RejectPolicy,
)

####################################################################################################################################################################

def _load_private_key(
    path: Path,
    ask_passphrase: bool = True,
) -> Tuple[Optional[paramiko.PKey], str]:
    """
    Попытка загрузить приватный ключ (Ed25519, ECDSA или RSA).
    Если ключ зашифрован (PasswordRequiredException), скрипт запросит пароль через getpass
    (если ask_passphrase=True). 
    Функция возвращает объект ключа и код статуса (pkey, code):
    code:
        ssh_0  - ключ успешно загружён
        ssh_10 - файл ключа отсутствует
        ssh_12 - ключ зашифрован, ввод passphrase запрещён
        ssh_14 - введён некорректный passphrase
        ssh_16 - ключ не соответствует поддерживаемым форматам
    """

    # Проверяет наличие файла ключа как предварительное условие загрузки.
    if not path.is_file():
        return None, f"ssh_{10}"

    # Поддерживаемые типы ключей.
    key_classes = [Ed25519Key, ECDSAKey, RSAKey]

    for key_class in key_classes:
        try:
            # Попытка прямой загрузки незашифрованного ключа.
            key = key_class.from_private_key_file(str(path))
            return key, f"ssh_{0}"

        except PasswordRequiredException:
            # Случай зашифрованного ключа, требующего passphrase.
            if not ask_passphrase:
                return None, f"ssh_{12}"

            try:
                # Повторная попытка загрузки с использованием passphrase.
                passphrase = getpass("Passphrase для ключа: ")
                key = key_class.from_private_key_file(
                    str(path),
                    password=passphrase,
                )
                return key, f"ssh_{0}"
            except SSHException:
                return None, f"ssh_{14}"

        except SSHException:
            continue

    # Невозможность загрузки ключа.
    return None, f"ssh_{16}"

def get_ssh_connection(
    username: str,
    hostname: str,
    key_path: Path,
    timeout: int,
    allow_new_hosts: bool,
) -> Tuple[Optional[paramiko.SSHClient], int]:
    """
    Возвращает:
        (client, code)
        code:
            ssh_20 - ошибка аутентификации или сетевого соединения
            ssh_21 - хост отсутствует в known_hosts
            ssh_22 - ключ хоста не совпадает с ожидаемым
            ssh_99 - прочие ошибки SSH или системные исключения
    """

    pkey, load_code = _load_private_key(key_path)
    if pkey is None:
        return None, load_code

    client = paramiko.SSHClient()
    client.load_system_host_keys()

    # Определяет политику обработки неизвестных хостов для обеспечения контроля доверия.
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
        return client, f"ssh_{0}"

    except paramiko.AuthenticationException:
        return None, f"ssh_{20}"

    except paramiko.SSHException as e:
        msg = str(e).lower()
        if "host key" in msg or "known_hosts" in msg:
            return None, f"ssh_{21}"
        if "mismatch" in msg or "does not match" in msg:
            return None, f"ssh_{22}"
        if "timed out" in msg or "connect" in msg or "unreachable" in msg:
            return None, f"ssh_{20}"
        return None, f"ssh_{99}"
    except Exception:
        return None, f"ssh_{99}"

####################################################################################################################################################################

def get_sqlite_connection(db_path: Path) -> Tuple[Optional[sqlite3.Connection], int]:
    """
    Аргументы:
        db_path: Абсолютный путь к файлу базы данных в файловой системе.
    Возвращает:
        Кортеж, состоящий из объекта соединения и целочисленного кода SQLite.
    """

    try:
        # Для систем, работающих исключительно с предзаполненными схемами, исключить создание пустых баз данных нулевого размера.
        if not db_path.exists():
            return None, sqlite3.SQLITE_CANTOPEN

        db_uri = f"{db_path.as_uri()}?mode=rw"
        
        conn = sqlite3.connect(db_uri, uri=True)
        
        # Выполнить процедуру полной проверки целостности структуры данных. Инструкция PRAGMA integrity_check анализирует соответствие индексов, корректность B-деревьев и отсутствие поврежденных страниц данных.
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        check_result = cursor.fetchone()

        # Проверить финальный статус валидации структуры. Любой результат, отличный от 'ok', сигнализирует о деградации данных, требующей немедленного прекращения работы с ресурсом.
        if check_result is None or check_result[0] != "ok":
            conn.close()
            return None, sqlite3.SQLITE_CORRUPT

        return conn, sqlite3.SQLITE_OK

    except sqlite3.Error as sqlite_exc:
        error_code = getattr(sqlite_exc, "sqlite_errorcode", sqlite3.SQLITE_ERROR)
        return None, error_code

    except Exception:
        return None, sqlite3.SQLITE_ERROR

####################################################################################################################################################################

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DB = ROOT / "databases" / "wasserfall_config.db"

def get_config_for_host(host_name: str = None):
    """Возвращает настройки хоста и его переменные."""
    conn = sqlite3.connect(CONFIG_DB)
    cursor = conn.cursor()
    
    # Если хост не указан, все разрешенные (toggle)
    if not host_name:
        cursor.execute("SELECT id, name FROM hosts WHERE toggle = 1 ;")
    else:
        cursor.execute("SELECT id, name FROM hosts WHERE name = ? ;", (host_name,))
    
    host_data = cursor.fetchone()
    if not host_data:
        conn.close()
        raise ValueError(f"Хост {host_name} не найден или не активен.")
    
    host_id, name = host_data
    
    # Собираем переменные в словари
    cursor.execute("SELECT variable, value FROM ssh_variables WHERE id_host = ? ;", (host_id,))
    ssh_vars = dict(cursor.fetchall())
    
    cursor.execute("SELECT variable, value FROM postgre_variables WHERE id_host = ? ;", (host_id,))
    pg_vars = dict(cursor.fetchall())
    
    conn.close()
    return name, ssh_vars, pg_vars

####################################################################################################################################################################

def get_sql_template(command_name: str) -> str:
    """Извлекает SQL шаблон из базы."""
    conn = sqlite3.connect(CONFIG_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT template FROM sql_commands WHERE name = ? ;", (command_name,))
    data = cursor.fetchone()
    conn.close()
    if not data:
        raise ValueError(f"Команда {command_name} не найдена.")
    return data[0]
    
####################################################################################################################################################################