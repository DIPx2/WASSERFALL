============================================================
 POSTGRESQL COMMAND EXECUTOR — СПРАВКА ПО КОМАНДНОЙ СТРОКЕ
============================================================

Назначение:
  Выполнение SQL-команд на удалённых PostgreSQL‑хостах по SSH.
  Команды берутся из таблицы "sql_commands" (wasserfall_config.db),
  рендерятся через Jinja2 и выполняются на всех или выбранных БД.

  Все результаты логируются в:
    - execution_tasks
    - execution_results
  через модуль common/logger.py.

============================================================
 СИНТАКСИС
============================================================

  python command_executor_postgresql/main.py --cmd <COMMAND> [OPTIONS]

============================================================
 ОБЯЗАТЕЛЬНЫЕ ПАРАМЕТРЫ
============================================================

  --cmd <NAME>        Имя SQL-команды из таблицы sql_commands.

============================================================
 ОСНОВНЫЕ ОПЦИИ
============================================================

  --host <HOST>       Выполнить команду только на одном хосте.
                      Если не указано — выполняется на всех
                      активных хостах (hosts.toggle = 1).

  --workers <N>       Количество параллельных потоков.
                      По умолчанию: 5.

  --var key=value     Передача переменных в шаблон SQL.
                      Можно указывать несколько раз.

  --db <NAME>         Выполнить команду только на указанных БД.
                      Можно указывать несколько раз.

  --db-exclude <NAME> Исключить указанные БД из обработки.

  --allow-new-hosts   Разрешить автоматическое добавление
                      новых хостов в known_hosts.

  --verbose           Показать подробный вывод:
                        - JSON‑данные по каждой БД
                        - pg_код и exit‑код
                        - сырые данные при ошибках

============================================================
 ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ
============================================================

  1) Выполнить CHECK_HEALTH на всех активных хостах:

      python command_executor_postgresql/main.py --cmd CHECK_HEALTH

  2) Выполнить команду только на одном хосте:

      python command_executor_postgresql/main.py --cmd CHECK_HEALTH \
             --host dev-msg-pg-01.maxbit.private

  3) Подробный вывод JSON‑данных:

      python command_executor_postgresql/main.py --cmd CHECK_HEALTH --verbose

  4) Передача переменных в SQL‑шаблон:

      python command_executor_postgresql/main.py --cmd CHECK_TABLE_SIZE \
             --var table=events --var limit=100

  5) Выполнить команду только на конкретных БД:

      python command_executor_postgresql/main.py --cmd CHECK_HEALTH \
             --db app --db analytics

  6) Исключить БД из обработки:

      python command_executor_postgresql/main.py --cmd CHECK_HEALTH \
             --db-exclude template1 --db-exclude postgres

  7) Автоматическое добавление хостов в known_hosts:

      python command_executor_postgresql/main.py --cmd CHECK_HEALTH --allow-new-hosts

============================================================
 КОДЫ ВЫПОЛНЕНИЯ
============================================================

  SSH-коды:
    ssh_0     Подключение успешно
    ssh_99    Хост недоступен / ошибка SSH / нет в known_hosts

  PostgreSQL-коды:
    pg_0      SQL выполнен успешно
    pg_10     psql не найден / не установлен
    pg_12     Ошибка аутентификации (пароль)
    pg_14     Синтаксическая ошибка SQL
    pg_16     Ошибка подключения к PostgreSQL
    pg_18     Ошибка выполнения SQL (exit_code != 0)
    pg_99     Неизвестная ошибка

  Человекочитаемые статусы:
    OK            Все БД успешны
    PARTIAL       Часть БД успешна
    FAIL          Ошибка SSH или конфигурации

============================================================
 ЛОГИРОВАНИЕ
============================================================

  Все операции записываются в wasserfall_logger.db:

  Таблица execution_tasks:
    task_id       INTEGER PRIMARY KEY
    target_host   TEXT
    query_text    TEXT
    started_at    DATETIME
    database_name TEXT (NULL для ошибок до выполнения)

  Таблица execution_results:
    result_id     INTEGER PRIMARY KEY
    task_id       INTEGER (FK)
    pg_code       TEXT (pg_XX / ssh_XX)
    exit_code     INTEGER
    stdout_json   TEXT (JSON: data, stderr, exit_code)
    stderr_text   TEXT
    finished_at   DATETIME

  Пример stdout_json:
    {
      "data": [{"ts": "2026-02-22T12:00:00"}],
      "stderr": "",
      "exit_code": 0
    }

============================================================
 ASCII-ДИАГРАММА АРХИТЕКТУРЫ
============================================================

                       +---------------------------+
                       | command_executor_postgresql|
                       |---------------------------|
                       | main.py                   |
                       | modules/postgres_runner.py|
                       | modules/getter.py         |
                       +-------------+-------------+
                                     |
                                     | вызывает
                                     v
                       +---------------------------+
                       |          common           |
                       |---------------------------|
                       | getter.py                |
                       | logger.py                |
                       | template_engine.py       |
                       +-------------+-------------+
                                     |
                                     | читает конфиг / пишет логи
                                     v
         +---------------------------+---------------------------+
         |                        databases                     |
         |------------------------------------------------------|
         | wasserfall_config.db   |   wasserfall_logger.db      |
         |-------------------------+-----------------------------|
         | hosts                   | execution_tasks             |
         | ssh_variables           | execution_results           |
         | postgre_variables       |                             |
         | sql_commands            |                             |
         +-------------------------+-----------------------------+

============================================================
 КАК РАБОТАЕТ ШАБЛОНИЗАЦИЯ SQL (JINJA2)
============================================================

  Шаблоны SQL хранятся в таблице sql_commands.template.

  Пример:

    SELECT * FROM {{ table }} LIMIT {{ limit }};

  Запуск:

    --var table=events --var limit=100

  Результат:

    SELECT * FROM events LIMIT 100;

  Поддерживаются:
    - условия {% if %}
    - значения по умолчанию
    - многострочные SQL‑шаблоны

============================================================
 КАК РАБОТАЕТ ПАРАЛЛЕЛИЗМ (ThreadPoolExecutor)
============================================================

  - Каждый хост обрабатывается в отдельном потоке.
  - Каждый поток:
      1) устанавливает SSH‑соединение
      2) получает список БД
      3) рендерит SQL‑шаблон
      4) выполняет SQL на каждой БД
      5) пишет логи
      6) закрывает SSH‑клиент

  - SQLite допускает параллельные INSERT → логирование потокобезопасно.

============================================================
 КАК РАБОТАЕТ SSH‑ПОДКЛЮЧЕНИЕ
============================================================

  1) Загружаются SSH‑переменные хоста:
       SSH_USER, SSH_KEY_PATH, SSH_TIMEOUT

  2) Если --allow-new-hosts:
       AutoAddPolicy()
     иначе:
       RejectPolicy()

  3) Выполняется client.connect()

  4) Ошибки классифицируются в ssh_99

============================================================
 КАК РАБОТАЕТ ВЫПОЛНЕНИЕ SQL
============================================================

  SQL выполняется через:

    su - postgres -c "psql ... <<'EOF' ... EOF"

  Особенности:
    - heredoc позволяет передавать многострочный SQL
    - SQL оборачивается в:
        SELECT json_agg(t) FROM (<SQL>) t;
    - результат всегда JSON‑массив
    - ошибки классифицируются в pg_XX

============================================================
 ТИПИЧНЫЕ ОШИБКИ И РЕШЕНИЯ
============================================================

  1) ssh_99: Host not found in known_hosts
     → добавить вручную через ssh
     → или использовать --allow-new-hosts

  2) pg_14: syntax error
     → ошибка в SQL‑шаблоне

  3) pg_16: could not connect to server
     → PostgreSQL не запущен / неверный порт

  4) pg_12: password authentication failed
     → неверный PG_PASSWORD

  5) pg_10: psql: command not found
     → неверный PG_PSQL_PATH

============================================================
 КАК ДОБАВИТЬ НОВУЮ SQL‑КОМАНДУ
============================================================

  Таблица sql_commands имеет поля:
    id, name, template, description

  Пример:

    INSERT INTO sql_commands (name, template, description)
    VALUES (
      'CHECK_HEALTH',
      'SELECT now() AS ts, current_database() AS db, current_user AS usr;',
      'Проверка доступности PostgreSQL'
    );

  Запуск:

    python command_executor_postgresql/main.py --cmd CHECK_HEALTH


============================================================
 КАК ПИСАТЬ СЛОЖНЫЕ SQL‑ШАБЛОНЫ (JINJA2 + PostgreSQL)
============================================================

Шаблоны SQL хранятся в таблице sql_commands.template и рендерятся
через Jinja2. Это позволяет создавать динамические SQL‑команды,
которые адаптируются под параметры запуска (--var key=value).

Поддерживаются:
  - переменные {{ var }}
  - условия {% if %}
  - циклы {% for %}
  - значения по умолчанию
  - многострочные SQL‑блоки
  - вложенные конструкции
  - динамическая генерация WHERE, LIMIT, ORDER BY

============================================================
 ПРАВИЛО №1 — ШАБЛОН ДОЛЖЕН БЫТЬ ЧИСТЫМ SQL
============================================================

Шаблон — это SQL, в который встроены Jinja2‑конструкции.
Он должен оставаться валидным SQL после рендеринга.

Пример:

  SELECT * FROM {{ table }} LIMIT {{ limit }};

После рендеринга:

  SELECT * FROM events LIMIT 100;

============================================================
 ПРАВИЛО №2 — НЕ СТАВЬТЕ ТОЧКУ С ЗАПЯТОЙ В КОНЦЕ
============================================================

PostgreSQL‑executor автоматически оборачивает SQL в:

  SELECT json_agg(t) FROM (<SQL>) t;

Если в конце SQL стоит «;», получится ошибка синтаксиса.

Правильно:

  SELECT * FROM pg_stat_activity

Неправильно:

  SELECT * FROM pg_stat_activity;

============================================================
 ПРАВИЛО №3 — ИСПОЛЬЗУЙТЕ УСЛОВИЯ ДЛЯ НЕОБЯЗАТЕЛЬНЫХ ФИЛЬТРОВ
============================================================

Пример шаблона с условным WHERE:

  SELECT pid, usename, state, query
  FROM pg_stat_activity
  {% if user %}
      WHERE usename = '{{ user }}'
  {% endif %}
  ORDER BY pid;

Запуск:

  --var user=postgres

Результат:

  SELECT pid, usename, state, query
  FROM pg_stat_activity
  WHERE usename = 'postgres'
  ORDER BY pid;

============================================================
 ПРАВИЛО №4 — ИСПОЛЬЗУЙТЕ ЗНАЧЕНИЯ ПО УМОЛЧАНИЮ
============================================================

Пример:

  SELECT *
  FROM {{ table if table is defined else 'events' }}
  LIMIT {{ limit if limit is defined else 100 }};

Запуск без параметров:

  SELECT * FROM events LIMIT 100;

============================================================
 ПРАВИЛО №5 — ДИНАМИЧЕСКИЕ СПИСКИ ЧЕРЕЗ ЦИКЛЫ
============================================================

Пример: выборка нескольких таблиц в одном запросе.

  {% set tables = tables or [] %}
  SELECT json_build_object(
      'table', '{{ t }}',
      'count', (SELECT count(*) FROM {{ t }})
  )
  FROM (
      {% for t in tables %}
          SELECT '{{ t }}' AS t {% if not loop.last %} UNION ALL {% endif %}
      {% endfor %}
  ) s;

Запуск:

  --var tables=events --var tables=users --var tables=logs

============================================================
 ПРАВИЛО №6 — ДИНАМИЧЕСКИЕ WHERE‑БЛОКИ
============================================================

Пример:

  SELECT *
  FROM orders
  WHERE 1=1
  {% if status %}
      AND status = '{{ status }}'
  {% endif %}
  {% if date_from %}
      AND created_at >= '{{ date_from }}'
  {% endif %}
  {% if date_to %}
      AND created_at <= '{{ date_to }}'
  {% endif %}
  ORDER BY created_at DESC;

============================================================
 ПРАВИЛО №7 — МНОГОСТРОЧНЫЕ ШАБЛОНЫ
============================================================

Шаблон может быть любым по размеру:

  WITH active AS (
      SELECT *
      FROM pg_stat_activity
      WHERE state = 'active'
  ),
  idle AS (
      SELECT *
      FROM pg_stat_activity
      WHERE state = 'idle'
  )
  SELECT
      (SELECT count(*) FROM active) AS active_count,
      (SELECT count(*) FROM idle) AS idle_count;

============================================================
 ПРАВИЛО №8 — НЕ ЭКРАНИРУЙТЕ КАВЫЧКИ
============================================================

Не нужно экранировать кавычки вручную — heredoc передаёт SQL как есть.

Правильно:

  WHERE usename = '{{ user }}'

Неправильно:

  WHERE usename = \'{{ user }}\'

============================================================
 ПРАВИЛО №9 — НЕ ИСПОЛЬЗУЙТЕ ; ВНУТРИ CTE
============================================================

Неправильно:

  WITH x AS (SELECT 1;), y AS (...)

Правильно:

  WITH x AS (SELECT 1), y AS (...)

============================================================
 ПРИМЕР СЛОЖНОГО ШАБЛОНА: ПРОВЕРКА РЕПЛИКАЦИИ
============================================================

  SELECT
      pg_is_in_recovery() AS in_recovery,
      CASE
          WHEN pg_is_in_recovery() THEN
              (SELECT pg_last_xlog_receive_location())
          ELSE
              (SELECT pg_current_xlog_location())
      END AS location,
      (SELECT count(*) FROM pg_stat_replication) AS replicas,
      (SELECT application_name, state, sync_state
       FROM pg_stat_replication) AS replica_info;

============================================================
 ПРИМЕР СЛОЖНОГО ШАБЛОНА: ДИАГНОСТИКА НАГРУЗКИ
============================================================

  SELECT
      now() AS ts,
      (SELECT count(*) FROM pg_stat_activity WHERE state='active') AS active,
      (SELECT count(*) FROM pg_stat_activity WHERE wait_event IS NOT NULL) AS waiting,
      (SELECT sum(blks_read) FROM pg_stat_database) AS blks_read,
      (SELECT sum(blks_hit) FROM pg_stat_database) AS blks_hit,
      (SELECT sum(tup_returned) FROM pg_stat_database) AS tup_returned,
      (SELECT sum(tup_fetched) FROM pg_stat_database) AS tup_fetched;

============================================================
 ПРИМЕР СЛОЖНОГО ШАБЛОНА: ДИНАМИЧЕСКИЙ LIMIT
============================================================

  SELECT *
  FROM {{ table }}
  ORDER BY {{ order if order else 'id' }}
  LIMIT {{ limit if limit else 100 }};

Запуск:

  --var table=events --var order=created_at --var limit=50

============================================================
 ПРИМЕР СЛОЖНОГО ШАБЛОНА: ПОИСК ПРОБЛЕМНЫХ ЗАПРОСОВ
============================================================

  SELECT pid, usename, state, query_start, now() - query_start AS duration, query
  FROM pg_stat_activity
  WHERE state = 'active'
  {% if min_duration %}
      AND now() - query_start > interval '{{ min_duration }}'
  {% endif %}
  ORDER BY duration DESC;

============================================================
 РЕКОМЕНДАЦИИ ПО НАПИСАНИЮ ШАБЛОНОВ
============================================================

  - Всегда проверяйте шаблон через --verbose.
  - Не используйте ; в конце SQL.
  - Используйте {% if %} для необязательных параметров.
  - Используйте {% for %} для динамических списков.
  - Всегда делайте SQL читаемым — многострочные шаблоны приветствуются.
  - Помните, что результат всегда оборачивается в json_agg().
  - Если SQL возвращает одну строку — всё равно будет массив из 1 элемента.
  - Если SQL возвращает 0 строк — будет пустой массив [].

============================================================
 КОНЕЦ РАЗДЕЛА
============================================================


============================================================
 КОНЕЦ СПРАВКИ
============================================================
