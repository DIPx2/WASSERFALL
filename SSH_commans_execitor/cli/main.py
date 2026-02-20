#!/usr/bin/env python3
"""
CLI интерфейс для SSH Command Executor.
Использует общие модули из корня проекта.
"""
import sys
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Optional

# Добавляем корень проекта в path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Импорт ОБЩИХ модулей из корня
from modules.getter import (
    get_ssh_connection,
    get_config_for_host,
    get_sqlite_connection,
    get_all_active_hosts,
)
from modules.template_engine import render_sql
from modules.logger import log_execution

# Импорт SSH-специфичного модуля
from SSH_commans_execitor.modules.ssh_command_runner import run_ssh_command

# Глобальные пути (относительно корня)
PATH_CONFIG_DB = ROOT / "databases" / "wasserfall_config.db"
PATH_LOGGER_DB = ROOT / "databases" / "wasserfall_logger.db"


def parse_args():
    """Парсинг аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="SSH Command Executor - Выполнение команд на удалённых хостах"
    )
    parser.add_argument("--cmd", required=True, help="Имя команды или текст команды")
    parser.add_argument("--host", help="Имя конкретного хоста")
    parser.add_argument("--workers", type=int, default=5, help="Макс. параллельных хостов")
    parser.add_argument("--var", action="append", help="Переменные шаблона key=value")
    parser.add_argument("--sudo", action="store_true", help="Выполнять через sudo")
    parser.add_argument("--sudo-user", default="root", help="Пользователь для sudo")
    parser.add_argument("--timeout", type=int, default=60, help="Таймаут в секундах")
    parser.add_argument("--allow-new-hosts", action="store_true", help="Разрешить unknown hosts")
    parser.add_argument("--dry-run", action="store_true", help="Показать без выполнения")
    parser.add_argument("--verbose", action="store_true", help="Показывать stderr при ошибках")
    return parser.parse_args()


def get_ssh_command_template(command_name):
    """Получить шаблон команды по имени из БД."""
    conn, code = get_sqlite_connection(PATH_CONFIG_DB)
    if conn is None:
        return None
    
    cursor = conn.cursor()
    cursor.execute("SELECT template FROM sql_commands WHERE name = ?;", (command_name,))
    row = cursor.fetchone()
    conn.close()
    
    return row[0] if row else None


def process_host(
    host_name,
    cmd_name,
    command_template,
    template_vars,
    sudo,
    sudo_user,
    timeout,
    allow_new_hosts,
    dry_run,
):
    """Обработать один хост."""
    result = {
        "host": host_name,
        "success": False,
        "error": None,
        "ssh_code": None,
        "cmd_code": None,
        "stdout": "",
        "stderr": "",
        "exit_code": None,
    }
    
    client = None
    
    try:
        name, ssh_vars, pg_vars = get_config_for_host(
            host_name=host_name,
            PATH_CONFIG_DB=str(PATH_CONFIG_DB)
        )
        
        key_path_str = ssh_vars.get("SSH_KEY_PATH", "")
        
        if key_path_str:
            key_path = Path(key_path_str)
            if not key_path.is_absolute():
                test_path = ROOT / key_path
                if test_path.exists():
                    key_path = test_path
                else:
                    test_path = ROOT / "PostgreSQL_command_executor" / key_path
                    if test_path.exists():
                        key_path = test_path
                    else:
                        key_path = key_path.expanduser()
        else:
            key_path = ROOT / "key" / "id_ed25519"
            if not key_path.exists():
                key_path = Path.home() / ".ssh" / "id_ed25519"
        
        if not key_path.exists():
            result["error"] = "SSH ключ не найден: " + str(key_path)
            result["ssh_code"] = "ssh_10"
            return result
        
        username = ssh_vars.get("SSH_USER", "root")
        ssh_timeout = int(ssh_vars.get("SSH_TIMEOUT", 10))
        
        client, ssh_code = get_ssh_connection(
            username=username,
            hostname=name,
            key_path=key_path,
            timeout=ssh_timeout,
            allow_new_hosts=allow_new_hosts,
        )
        
        result["ssh_code"] = ssh_code
        
        if ssh_code != "ssh_0":
            result["error"] = "SSH Connection Failed: " + ssh_code
            return result
        
        try:
            rendered_command = render_sql(
                template_str=command_template,
                context=template_vars
            )
        except Exception as e:
            result["error"] = "Template Error: " + str(e)
            result["cmd_code"] = "cmd_99"
            return result
        
        if dry_run:
            sys.stdout.write("[DRY-RUN] " + name + ": " + rendered_command + "\n")
            sys.stdout.flush()
            result["success"] = True
            result["cmd_code"] = "cmd_0"
            return result
        
        cmd_result, cmd_code = run_ssh_command(
            ssh_client=client,
            command=rendered_command,
            sudo=sudo,
            sudo_user=sudo_user,
            timeout=timeout,
            get_pty=sudo,
        )
        
        result["cmd_code"] = cmd_code
        result["success"] = cmd_code == "cmd_0"
        result["exit_code"] = cmd_result.get("exit_code")
        result["stdout"] = cmd_result.get("stdout", "")
        result["stderr"] = cmd_result.get("stderr", "")
        
        log_execution(
            target_host=name,
            query_text=rendered_command,
            result={
                "data": cmd_result.get("stdout", ""),
                "stderr": cmd_result.get("stderr", ""),
                "exit_code": cmd_result.get("exit_code"),
            },
            code=cmd_code,
            logger_db_path=PATH_LOGGER_DB,
            database_name=None
        )
        
    except Exception as e:
        result["error"] = "Exception: " + str(e)
        result["cmd_code"] = "cmd_99"
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass
    
    return result


def main():
    """Точка входа CLI."""
    sys.stdout.write("\n")
    sys.stdout.write("=" * 70 + "\n")
    sys.stdout.write("SSH Command Executor\n")
    sys.stdout.write("=" * 70 + "\n")
    sys.stdout.flush()
    
    args = parse_args()
    
    template_vars = {}
    if args.var:
        for var in args.var:
            if "=" in var:
                key, value = var.split("=", 1)
                template_vars[key.strip()] = value.strip()
    
    command_template = get_ssh_command_template(args.cmd)
    
    if command_template is None:
        command_template = args.cmd
        sys.stdout.write("Команда не найдена в БД: " + args.cmd + "\n")
        sys.stdout.flush()
    
    try:
        if args.host:
            hosts = [args.host]
        else:
            hosts = get_all_active_hosts(root=ROOT)
    except Exception as e:
        sys.stdout.write("Ошибка получения хостов: " + str(e) + "\n")
        sys.stdout.flush()
        sys.exit(1)
    
    if not hosts:
        sys.stdout.write("Нет активных хостов для обработки\n")
        sys.stdout.flush()
        sys.exit(1)
    
    sys.stdout.write("Хостов: " + str(len(hosts)) + "\n")
    sys.stdout.write("Команда: " + command_template + "\n")
    sys.stdout.write("Sudo: " + str(args.sudo) + "\n")
    sys.stdout.write("=" * 70 + "\n")
    sys.stdout.write("\n")
    sys.stdout.flush()
    
    success_count = 0
    fail_count = 0
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for host in hosts:
            future = executor.submit(
                process_host,
                host_name=host,
                cmd_name=args.cmd,
                command_template=command_template,
                template_vars=template_vars,
                sudo=args.sudo,
                sudo_user=args.sudo_user,
                timeout=args.timeout,
                allow_new_hosts=args.allow_new_hosts,
                dry_run=args.dry_run,
            )
            futures[future] = host
        
        for future in as_completed(futures):
            host_name = futures[future]
            try:
                result = future.result()
                
                if result.get("success") == True:
                    sys.stdout.write("[OK] " + host_name + "\n")
                    success_count += 1
                    if result.get("stdout"):
                        sys.stdout.write("   " + result["stdout"][:300] + "\n")
                else:
                    error_msg = result.get("error", "Unknown")
                    cmd_code = result.get("cmd_code", "")
                    stderr = result.get("stderr", "")
                    
                    if cmd_code:
                        error_msg = error_msg + " [" + cmd_code + "]"
                    
                    sys.stdout.write("[FAIL] " + host_name + " - " + error_msg + "\n")
                    
                    if args.verbose and stderr:
                        sys.stdout.write("   Stderr: " + stderr[:500] + "\n")
                    
                    fail_count += 1
            except Exception as e:
                sys.stdout.write("[ERROR] " + host_name + " - " + str(e) + "\n")
                fail_count += 1
            
            sys.stdout.flush()
    
    sys.stdout.write("\n")
    sys.stdout.write("=" * 70 + "\n")
    sys.stdout.write("Завершено. Успешно: " + str(success_count) + ", Ошибок: " + str(fail_count) + "\n")
    sys.stdout.write("=" * 70 + "\n")
    sys.stdout.flush()
    
    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()