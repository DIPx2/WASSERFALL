# =============================================================================
# Модуль: main.py
# Назначение: оркестрация выполнения SQL‑команд PostgreSQL на удалённых хостах
# через SSH. Обеспечивает:
#   - загрузку конфигурации хоста (SSH/PG‑параметры);
#   - подключение по SSH с контролируемой моделью ошибок;
#   - выбор целевых баз данных (все пользовательские или заданные);
#   - рендеринг SQL‑шаблона с подстановкой переменных;
#   - выполнение SQL‑команды по каждой БД через psql;
#   - централизованное логирование результатов в SQLite;
#   - параллельную обработку множества хостов;
#   - унифицированный вывод статусов (OK / PARTIAL / FAIL).
# =============================================================================

import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Optional

# Корневая директория проекта для корректного импорта внутренних модулей
ROOT = Path(__file__).resolve().parent.parents[1]
# ROOT = Path(__file__).resolve().parents[2]
# ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


print (ROOT)


if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Импорт вспомогательных модулей
from common.getter import (
    get_config_for_host,
    get_ssh_connection,
    get_all_active_hosts,
)

from EXECUTOR.command_executor_postgresql.modules.getter import (
    get_parse_args,
    get_sql_template,
    get_user_databases,
)

from EXECUTOR.command_executor_postgresql.modules.postgres_runner import (
    run_postgres_command_over_ssh,
)

from common.template_engine import render_sql
from common.logger import log_execution

# Пути к конфигурационной и логирующей SQLite‑БД
PATH_CONFIG_DB = ROOT / "databases" / "wasserfall_config.db"
PATH_LOGGER_DB = ROOT / "databases" / "wasserfall_logger.db"


# =============================================================================
# Форматированный вывод результата выполнения SQL‑команды
# =============================================================================
def print_pg_result(host: str, result: Dict[str, Any], verbose: bool = False):
    """
    Унифицированный вывод результата выполнения SQL‑команды.
    Поддерживаемые состояния:
      - OK       — все базы обработаны успешно;
      - PARTIAL  — часть баз завершилась ошибкой;
      - FAIL     — ошибка SSH, конфигурации или отсутствие результатов.
    """

    # Ошибка SSH‑подключения или конфигурации
    if result.get("ssh_code") != "ssh_0":
        print(f"[FAIL] {host} - {result.get('error', 'SSH error')}")
        return

    # Ошибка до выполнения SQL (например, пустой список БД)
    if not result.get("results"):
        print(f"[FAIL] {host} - {result.get('error', 'Unknown error')}")
        return

    # Полный успех
    if result.get("success"):
        print(f"[OK] {host}")
        if verbose:
            for r in result["results"]:
                print(f"      БД {r['database']}: pg_0 (exit=0)")
                print(f"      DATA: {r.get('data')}")
        return

    # Частичный успех
    db_results = result["results"]
    db_success = len([r for r in db_results if r["success"]])
    db_total = len(db_results)

    print(f"[PARTIAL] {host} - {db_success}/{db_total} БД успешно")

    for r in db_results:
        if not r["success"]:
            print(f"      БД {r['database']}: ошибка {r['pg_code']} (exit={r['exit_code']})")
            if verbose:
                print(f"      DATA: {r.get('data')}")

    if result.get("error"):
        print(f"      Причина: {result['error']}")


# =============================================================================
# Обработка одного хоста: SSH → выбор БД → рендеринг SQL → выполнение
# =============================================================================
def process_host(
    host_name: str,
    cmd_name: str,
    template_vars: Dict[str, str],
    target_dbs: Optional[List[str]],
    exclude_dbs: Optional[List[str]],
    allow_new_hosts: bool,
) -> Dict[str, Any]:

    results = []
    client = None
    name = host_name

    try:
        # ---------------------------------------------------------
        # Загрузка конфигурации хоста (SSH/PG‑параметры)
        # ---------------------------------------------------------
        try:
            name, ssh_vars, pg_vars = get_config_for_host(
                host_name=host_name,
                PATH_CONFIG_DB=str(PATH_CONFIG_DB),
            )
        except Exception as e:
            # Ошибка конфигурации фиксируется как ssh_99
            error_msg = "CONFIG_ERROR: " + str(e)
            log_execution(
                target_host=host_name,
                query_text="CONFIG_ERROR: " + cmd_name,
                result={"data": None, "stderr": error_msg, "exit_code": -1},
                code="ssh_99",
                logger_db_path=PATH_LOGGER_DB,
                database_name=None,
            )
            return {
                "host": host_name,
                "ssh_code": "ssh_99",
                "pg_code": None,
                "error": error_msg,
                "success": False,
            }

        # ---------------------------------------------------------
        # SSH‑подключение
        # ---------------------------------------------------------
        key_path_str = ssh_vars.get("SSH_KEY_PATH", "~/.ssh/id_ed25519")
        key_path = Path(key_path_str)

        # Разрешение относительных путей и $HOME
        if not key_path.is_absolute():
            test_path = ROOT / key_path
            key_path = test_path if test_path.exists() else key_path.expanduser()

        username = ssh_vars.get("SSH_USER", "root")
        timeout = int(ssh_vars.get("SSH_TIMEOUT", 10))

        client, ssh_code = get_ssh_connection(
            username=username,
            hostname=name,
            key_path=key_path,
            timeout=timeout,
            allow_new_hosts=allow_new_hosts,
        )

        # Ошибка SSH‑подключения фиксируется и возвращается как явное состояние
        if ssh_code != "ssh_0":
            error_msg = "SSH Connection Failed: " + ssh_code
            log_execution(
                target_host=name,
                query_text="SSH_ERROR: " + cmd_name,
                result={"data": None, "stderr": error_msg, "exit_code": -1},
                code=ssh_code,
                logger_db_path=PATH_LOGGER_DB,
                database_name=None,
            )
            return {
                "host": name,
                "ssh_code": ssh_code,
                "pg_code": None,
                "error": error_msg,
                "success": False,
            }

        # ---------------------------------------------------------
        # Определение списка баз данных
        # ---------------------------------------------------------
        if target_dbs:
            databases = target_dbs
        else:
            databases = get_user_databases(client=client, pg_vars=pg_vars)

        # Исключение указанных БД
        if exclude_dbs and databases:
            databases = [db for db in databases if db not in exclude_dbs]

        # Пустой список БД — ошибка pg_99
        if not databases:
            error_msg = "No databases to process"
            log_execution(
                target_host=name,
                query_text="DB_LIST_ERROR: " + cmd_name,
                result={"data": None, "stderr": error_msg, "exit_code": -1},
                code="pg_99",
                logger_db_path=PATH_LOGGER_DB,
                database_name=None,
            )
            return {
                "host": name,
                "ssh_code": "ssh_0",
                "pg_code": "pg_99",
                "error": error_msg,
                "success": False,
            }

        # ---------------------------------------------------------
        # Рендеринг SQL‑шаблона
        # ---------------------------------------------------------
        try:
            sql_template = get_sql_template(
                command_name=cmd_name,
                PATH_CONFIG_DB=str(PATH_CONFIG_DB),
            )
            rendered_sql = render_sql(
                template_str=sql_template,
                context=template_vars,
            )
        except Exception as e:
            # Ошибка шаблона — pg_99
            error_msg = "Template Error: " + str(e)
            log_execution(
                target_host=name,
                query_text="TEMPLATE_ERROR: " + cmd_name,
                result={"data": None, "stderr": error_msg, "exit_code": -1},
                code="pg_99",
                logger_db_path=PATH_LOGGER_DB,
                database_name=None,
            )
            return {
                "host": name,
                "ssh_code": "ssh_0",
                "pg_code": "pg_99",
                "error": error_msg,
                "success": False,
            }

        # ---------------------------------------------------------
        # Выполнение SQL‑команды по каждой БД
        # ---------------------------------------------------------
        for db_name in databases:
            result, pg_code = run_postgres_command_over_ssh(
                ssh_client=client,
                sql=rendered_sql,
                db_user=pg_vars.get("PG_DB_USER", "postgres"),
                db_name=db_name,
                db_port=int(pg_vars.get("PG_DB_PORT", 5432)),
                psql_path=pg_vars.get("PG_PSQL_PATH", "/usr/bin/psql"),
                db_password=pg_vars.get("PG_PASSWORD", None),
            )

            # Логирование результата выполнения SQL
            log_execution(
                target_host=name,
                query_text=rendered_sql,
                result=result,
                code=pg_code,
                logger_db_path=PATH_LOGGER_DB,
                database_name=db_name,
            )

            results.append({
                "database": db_name,
                "pg_code": pg_code,
                "exit_code": result.get("exit_code"),
                "success": pg_code == "pg_0",
                "data": result.get("data"),
            })

        # Итоговый статус: успех только если все БД успешны
        all_success = all(r["success"] for r in results) if results else False

        return {
            "host": name,
            "ssh_code": "ssh_0",
            "results": results,
            "success": all_success,
            "databases_processed": len(results),
            "databases_failed": len([r for r in results if not r["success"]]),
        }

    finally:
        # Закрытие SSH‑клиента при наличии
        if client:
            try:
                client.close()
            except Exception:
                pass


# =============================================================================
# Точка входа: разбор аргументов, запуск пула потоков, вывод итогов
# =============================================================================
def main():
    args = get_parse_args()
    verbose = getattr(args, "verbose", False)

    # Формирование словаря переменных шаблона
    template_vars: Dict[str, str] = {}
    if args.var:
        for var in args.var:
            if "=" in var:
                key, value = var.split("=", 1)
                template_vars[key.strip()] = value.strip()

    # Определение списка хостов
    hosts = [args.host] if args.host else get_all_active_hosts(root=ROOT)
    if not hosts:
        print("Нет активных хостов для обработки.")
        return

    # Информационный заголовок
    print("=" * 70)
    print("Wasserfall: PostgreSQL Orchestration Engine")
    print("=" * 70)
    print("Хостов для обработки:", len(hosts))
    print("Воркеров (потоков):", args.workers)
    print("Команда:", args.cmd)
    print("Переменные шаблона:", template_vars if template_vars else "Нет")
    print("Базы данных:", args.db if args.db else "Все пользовательские")
    print("Исключить базы:", args.db_exclude if args.db_exclude else "Нет")
    print("Verbose:", verbose)
    print("=" * 70)

    success_count = 0
    fail_count = 0
    partial_count = 0

    # Параллельная обработка хостов
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_host,
                host_name=host,
                cmd_name=args.cmd,
                template_vars=template_vars,
                target_dbs=args.db,
                exclude_dbs=args.db_exclude,
                allow_new_hosts=args.allow_new_hosts,
            ): host
            for host in hosts
        }

        # Обработка результатов по мере завершения
        for future in as_completed(futures):
            host = futures[future]
            try:
                result = future.result()
                print_pg_result(host, result, verbose=verbose)

                if result.get("success"):
                    success_count += 1
                elif result.get("results"):
                    partial_count += 1
                else:
                    fail_count += 1

            except Exception as e:
                print(f"[ERROR] {host} - {e}")
                fail_count += 1

    # Итоговая статистика
    print("=" * 70)
    print(f"Завершено. Успешно: {success_count}, Частично: {partial_count}, Ошибок: {fail_count}")
    print("=" * 70)


if __name__ == "__main__":
    main()
