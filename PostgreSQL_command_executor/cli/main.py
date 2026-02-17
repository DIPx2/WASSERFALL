import sys
import argparse
import sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.getter import get_ssh_connection, get_config_for_host, get_sql_template, get_sqlite_connection
from modules.template_engine import render_sql
from modules.db_postgres_runner import run_postgres_command_over_ssh
from modules.logger import log_execution

def parse_args():
    parser = argparse.ArgumentParser(description="Wasserfall CLI: Parallel Mode")
    parser.add_argument("--cmd", required=True, help="Имя SQL команды")
    parser.add_argument("--host", help="Имя конкретного хоста (опционально)")
    parser.add_argument("--workers", type=int, default=5, help="Количество параллельных потоков")
    parser.add_argument("-v", "--var", action="append", help="Переменные шаблона key=value")
    return parser.parse_args()

def get_all_active_hosts():
    """Извлекает список всех активных хостов из БД."""
    conn = sqlite3.connect(ROOT / "databases" / "wasserfall_config.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM hosts WHERE toggle = 1;")
    hosts = [row[0] for row in cursor.fetchall()]
    conn.close()
    return hosts
    
# Обработка отдельного хоста (внутри потока)
def process_single_host(hostname, command_name, template_vars):
    try:
        # 1. Загрузка конфига для конкретного хоста
        """
        Функция get_config_for_host подключается к wasserfall_config.db и возвращает
        два словаря переменных: cловарь SSH-переменных (ssh_vars) и 
        словарь PostgreSQL-переменных (pg_vars)
        """
        
# TODO: Надо в get_config_for_host обработчик ошибок + здесь
# TODO: get_config_for_host: переработать запрос
        _, ssh_v, pg_v = get_config_for_host(hostname)

        """
        Извлекает сырой текст SQL-запроса из таблицы sql_commands
        """
        raw_template = get_sql_template(command_name)
        
        """
        Использует модуль template_engine.py, который использует библиотеку Jinja2
        для подстановки переменных в шаблон. Если переменная отсутствует,
        StrictUndefined вызовет ошибку.
        """
        final_sql = render_sql(raw_template, template_vars)

        # 2. SSH-подключение
        """
        Создается SSH-client. В зависимости от настройки allow_new_hosts,
        устанавливается политика AutoAddPolicy (доверять новым) или RejectPolicy (отклонять).
        Происходит подключение к хосту. В случае ошибок (таймаут, auth fail) возвращается
        соответствующий код ошибки (например, ssh_20).
        """
        client, ssh_code = get_ssh_connection(
            username=ssh_v['SSH_USER'],
            hostname=hostname,
            key_path=ROOT / ssh_v['SSH_KEY_PATH'].lstrip('.\\'),
            timeout=int(ssh_v['SSH_TIMEOUT']),
            allow_new_hosts=(ssh_v['SSH_ALLOW_NEW_HOSTS'] == 'True')
        )

        if client and ssh_code == "ssh_0": # SSH-соединение успешно
            # 3. Выполнение команды PostgreSQL (db_postgres_runner.py)
            result, pg_code = run_postgres_command_over_ssh(
                ssh_client=client,
                sql=final_sql,
                db_user=pg_v['PG_DB_USER'],
                db_port=int(pg_v['PG_DB_PORT']),
                db_name=pg_v['PG_DB_DEFAULT'],
                psql_path=pg_v['PG_PSQL_PATH']
            )

            # 4. Логирование
            """
            Результат выполнения (успех или ошибка) передается в log_execution.
            Создается запись в таблице execution_tasks (хост, текст запроса).
            Создается связанная запись в execution_results (код PG, код выхода, JSON-вывод, текст ошибки).
            """
            log_execution(hostname, final_sql, result, pg_code)
            client.close()
            return f"[{hostname}] Успешно: {pg_code}"
        else:
            return f"[{hostname}] Ошибка SSH: {ssh_code}"
    except Exception as e:
        return f"[{hostname}] Критическая ошибка: {e}"

def main():
    """
    Скрипт ожидает следующие аргументы командной строки:
    --cmd: Имя SQL-команды (обязательно).
    --host: Имя конкретного хоста (опционально).
    --workers: Количество потоков (по умолчанию 5).
    --var: Переменные шаблона в формате key=value.
    """
    args = parse_args()
    
    """
    Обработка переменных шаблона.
    Аргументы, переданные через --var, преобразуются в словарь template_vars. 
    Строки разбиваются по первому знаку равенства.
    """
    template_vars = {item.split("=", 1)[0]: item.split("=", 1)[1] for item in (args.var or [])}

    """
    Выбор целей (хостов):
    Если указан флаг --host, список целей (targets) состоит из одного этого хоста.
    Если флаг отсутствует, вызывается функция get_all_active_hosts(). 
    Она подключается к локальной базе wasserfall_config.db, выполняет запрос 
    SELECT name FROM hosts WHERE toggle = 1 и возвращает список всех активных серверов.
    """
    if args.host:
        targets = [args.host]
    else:
        targets = get_all_active_hosts()
    
    if not targets:
        print("[!] Нет активных хостов для выполнения.")
        return

    # print(f"Запуск параллельного выполнения на {len(targets)} хостах (потоков: {args.workers})...")

    """
    Запуск пула потоков:
    Используется ThreadPoolExecutor с количеством воркеров, равным args.workers.
    Распределение задач:
    Для каждого хоста из списка targets создается задача (Future),
    которая запускает функцию process_single_host. 
    В эту функцию передаются три ключевых аргумента:
    hostname: Имя целевого сервера.
    command_name: Имя SQL-команды (из --cmd).
    template_vars: Словарь переменных для подстановки.
    """
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Формируем список задач
        future_to_host = {executor.submit(process_single_host, h, args.cmd, template_vars): h for h in targets}
        
        """
        Главный поток main() перехватывает результаты через as_completed и выводит их в консоль.
        Если возникло исключение, оно также выводится в stdout.
        """
        for future in as_completed(future_to_host):
            host = future_to_host[future]
            try:
                status = future.result() # Поток возвращает строковый статус
                print(status)
            except Exception as e:
                print(f"[{host}] Поток завершился с ошибкой: {e}")

# TODO: Модульность

if __name__ == "__main__":
    main()