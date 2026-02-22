import sys
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.getter import (
    get_ssh_connection,
    get_sqlite_connection,
    get_config_for_host,
    get_all_active_hosts,
)
from common.template_engine import render_sql
from common.logger import log_execution
from command_executor_ssh.modules.ssh_runner import run_ssh_command

PATH_CONFIG_DB = ROOT / "databases" / "wasserfall_config.db"
PATH_LOGGER_DB = ROOT / "databases" / "wasserfall_logger.db"


def get_command_template(command_name: str) -> Optional[str]:
    conn, code = get_sqlite_connection(PATH_CONFIG_DB)
    if conn is None:
        return None

    cursor = conn.cursor()
    cursor.execute("SELECT template FROM commands WHERE name = ?;", (command_name,))
    row = cursor.fetchone()
    conn.close()

    return row[0] if row else None


def process_host(
    host_name: str,
    command_template: str,
    template_vars: Dict[str, str],
    sudo: bool,
    sudo_user: str,
    timeout: int,
    allow_new_hosts: bool,
    dry_run: bool,
) -> Dict[str, Any]:

    result = {
        "host": host_name,
        "success": False,
        "error": None,
        "cmd_code": None,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
    }

    client = None

    try:
        name, ssh_vars, pg_vars = get_config_for_host(
            host_name=host_name,
            PATH_CONFIG_DB=str(PATH_CONFIG_DB)
        )

        key_path = Path(ssh_vars.get("SSH_KEY_PATH", "~/.ssh/id_ed25519"))
        if not key_path.is_absolute():
            key_path = (ROOT / key_path) if (ROOT / key_path).exists() else key_path.expanduser()

        username = ssh_vars.get("SSH_USER", "root")
        ssh_timeout = int(ssh_vars.get("SSH_TIMEOUT", 10))

        rendered_command = render_sql(command_template, template_vars)

        if dry_run:
            result["success"] = True
            result["cmd_code"] = "cmd_0"
            result["stdout"] = f"[DRY-RUN] {rendered_command}"
            return result

        client, ssh_code = get_ssh_connection(
            username=username,
            hostname=name,
            key_path=key_path,
            timeout=ssh_timeout,
            allow_new_hosts=allow_new_hosts,
        )

        if ssh_code != "ssh_0":
            result["error"] = f"SSH error: {ssh_code}"
            result["cmd_code"] = ssh_code
            result["exit_code"] = -1
            log_execution(
                target_host=name,
                query_text=rendered_command,
                result={"stdout": "", "stderr": ssh_code, "exit_code": -1},
                code=ssh_code,
                logger_db_path=PATH_LOGGER_DB,
                database_name=None,
            )
            return result

        cmd_result, cmd_code = run_ssh_command(
            ssh_client=client,
            command=rendered_command,
            sudo=sudo,
            sudo_user=sudo_user,
            timeout=timeout,
        )

        result["cmd_code"] = cmd_code
        result["exit_code"] = cmd_result["exit_code"]
        result["stdout"] = cmd_result["stdout"]
        result["stderr"] = cmd_result["stderr"]
        result["success"] = cmd_code == "cmd_0"

        log_execution(
            target_host=name,
            query_text=rendered_command,
            result=cmd_result,
            code=cmd_code,
            logger_db_path=PATH_LOGGER_DB,
            database_name=None,
        )

    finally:
        if client:
            try:
                client.close()
            except:
                pass

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SSH Command Executor — выполнение команд на удалённых хостах"
    )

    parser.add_argument("--cmd", required=True, help="Имя команды из таблицы commands или прямая команда")
    parser.add_argument("--host", help="Конкретный хост (иначе все активные)")
    parser.add_argument("--workers", type=int, default=5, help="Количество параллельных воркеров")
    parser.add_argument("--var", action="append", help="Переменные шаблона key=value")
    parser.add_argument("--sudo", action="store_true", help="Выполнять команду через sudo")
    parser.add_argument("--sudo-user", default="root", help="Пользователь для sudo")
    parser.add_argument("--timeout", type=int, default=60, help="Таймаут SSH-команды, сек")
    parser.add_argument("--allow-new-hosts", action="store_true", help="Разрешить добавление новых хостов в known_hosts")
    parser.add_argument("--dry-run", action="store_true", help="Показать команды без выполнения")
    parser.add_argument("--verbose", action="store_true", help="Подробный вывод (stdout/stderr)")

    return parser.parse_args()


def print_result(host: str, result: dict, verbose: bool) -> None:
    STATUS_MAP = {
        "cmd_0": "OK",
        "ssh_0": "OK",
        "ssh_99": "UNREACHABLE",
        "cmd_10": "FAILED",
        "cmd_12": "FAILED",
        "cmd_16": "FAILED",
        "cmd_18": "FAILED",
    }

    code = result.get("cmd_code")
    status = STATUS_MAP.get(code, "UNKNOWN")
    exit_code = result.get("exit_code")

    print(f"{host}: {status} ({code}, exit={exit_code})")

    if verbose:
        stdout = result.get("stdout") or ""
        stderr = result.get("stderr") or ""

        if stdout:
            print("stdout:")
            print(stdout)

        if stderr:
            print("stderr:")
            print(stderr)



def main() -> int:
    args = parse_args()

    template_vars: Dict[str, str] = {}
    if args.var:
        for v in args.var:
            if "=" in v:
                k, val = v.split("=", 1)
                template_vars[k.strip()] = val.strip()

    command_template = get_command_template(args.cmd)
    if command_template is None:
        print(f"Команда '{args.cmd}' не найдена в БД — выполняю как прямую команду")
        command_template = args.cmd

    hosts = [args.host] if args.host else get_all_active_hosts(ROOT)
    if not hosts:
        print("Нет активных хостов")
        return 1

    print("SSH Command Executor")
    print("--------------------")
    print(f"Хостов: {len(hosts)}")
    print(f"Команда: {command_template}")
    if template_vars:
        print(f"Переменные: {template_vars}")
    print()

    success = 0
    fail = 0
    results: Dict[str, Dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_host,
                host_name=h,
                command_template=command_template,
                template_vars=template_vars,
                sudo=args.sudo,
                sudo_user=args.sudo_user,
                timeout=args.timeout,
                allow_new_hosts=args.allow_new_hosts,
                dry_run=args.dry_run,
            ): h
            for h in hosts
        }

        for future in as_completed(futures):
            host = futures[future]
            try:
                r = future.result()
                results[host] = r

                if r["success"]:
                    success += 1
                else:
                    fail += 1

                # Управляемый вывод — можно отключить одной строкой
                print_result(host, r, args.verbose)

            except Exception as e:
                print(f"{host}: exception {str(e)}")
                fail += 1

    print()
    print("Итог:")
    print(f"Успешно: {success}")
    print(f"Ошибок: {fail}")

    # Если один хост и не verbose — показать stdout отдельно
    if len(hosts) == 1 and not args.verbose:
        r = results[hosts[0]]
        if r["success"] and r.get("stdout"):
            print()
            print("Вывод команды:")
            print(r["stdout"])

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
