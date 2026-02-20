--
-- Файл сгенерирован с помощью SQLiteStudio v3.4.21 в Чт фев 19 10:55:15 2026
--
-- Использованная кодировка текста: System
--
PRAGMA foreign_keys = off;
BEGIN TRANSACTION;

-- Таблица: hosts
CREATE TABLE hosts (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT    UNIQUE
                   NOT NULL,
    toggle INTEGER NOT NULL
                   DEFAULT 1
);

INSERT INTO hosts (id, name, toggle) VALUES (1, 'dev-msg-pg-01.maxbit.private', 1);
INSERT INTO hosts (id, name, toggle) VALUES (2, 'prd-msg-pg-03.maxbit.private', 0);

-- Таблица: postgre_variables
CREATE TABLE postgre_variables (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    id_host     INTEGER NOT NULL
                        REFERENCES hosts (id) ON DELETE CASCADE,
    variable    TEXT    NOT NULL,
    value       TEXT    NOT NULL,
    description TEXT,
    UNIQUE (
        id_host,
        variable
    )-- Теперь переменная уникальна только внутри одного хоста
);

INSERT INTO postgre_variables (id, id_host, variable, value, description) VALUES (1, 1, 'PG_DB_PORT', '5432', NULL);
INSERT INTO postgre_variables (id, id_host, variable, value, description) VALUES (2, 1, 'PG_DB_DEFAULT', 'postgres', NULL);
INSERT INTO postgre_variables (id, id_host, variable, value, description) VALUES (3, 1, 'PG_PSQL_PATH', '/usr/bin/psql', 'Путь к psql (если в PATH — можно оставить просто "psql")');
INSERT INTO postgre_variables (id, id_host, variable, value, description) VALUES (4, 1, 'PG_DB_USER', 'postgres', 'Системный пользователь для подключения к БД');
INSERT INTO postgre_variables (id, id_host, variable, value, description) VALUES (5, 2, 'PG_DB_DEFAULT', 'postgres', NULL);
INSERT INTO postgre_variables (id, id_host, variable, value, description) VALUES (6, 2, 'PG_DB_PORT', '5432', NULL);
INSERT INTO postgre_variables (id, id_host, variable, value, description) VALUES (7, 2, 'PG_DB_USER', 'postgres', 'Системный пользователь для подключения к БД');
INSERT INTO postgre_variables (id, id_host, variable, value, description) VALUES (8, 2, 'PG_PSQL_PATH', '/usr/bin/psql', 'Путь к psql (если в PATH — можно оставить просто "psql")');

-- Таблица: sql_commands
CREATE TABLE sql_commands (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    UNIQUE
                        NOT NULL,
    template    TEXT    NOT NULL,
    description TEXT
);

INSERT INTO sql_commands (id, name, template, description) VALUES (1, 'CHECK_HEALTH', 'SELECT datname, datcollate FROM pg_database;', 'Simple SQL check');
INSERT INTO sql_commands (id, name, template, description) VALUES (2, 'DB_SIZES', 'SELECT datname AS database_name, pg_size_pretty(pg_database_size(datname)) AS size FROM pg_database ORDER BY pg_database_size(datname) DESC;', 'Список баз данных и их фактический размер на диске');
INSERT INTO sql_commands (id, name, template, description) VALUES (3, 'TOP_10_TABLES', 'SELECT relname AS table_name, pg_size_pretty(pg_total_relation_size(relid)) AS total_size FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 10;', 'ТОП-10 самых тяжелых таблиц (данные + индексы)');
INSERT INTO sql_commands (id, name, template, description) VALUES (4, 'ACTIVE_SESSIONS', 'SELECT count(*) AS total_conns, state FROM pg_stat_activity GROUP BY state;', 'Количество активных, простаивающих и заблокированных сессий');

-- Таблица: ssh_variables
CREATE TABLE ssh_variables (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    id_host     INTEGER NOT NULL
                        REFERENCES hosts (id) ON DELETE CASCADE,
    variable    TEXT    NOT NULL,
    value       TEXT    NOT NULL,
    description TEXT,
    UNIQUE (
        id_host,
        variable
    )-- Позволяет разным хостам иметь одинаковые имена переменных
);

INSERT INTO ssh_variables (id, id_host, variable, value, description) VALUES (1, 1, 'SSH_KEY_PATH', '.\key\id_ed25519', 'Путь к приватному ключу');
INSERT INTO ssh_variables (id, id_host, variable, value, description) VALUES (2, 1, 'SSH_TIMEOUT', '10', 'Таймаут для операций PostgreSQL по SSH (сек)');
INSERT INTO ssh_variables (id, id_host, variable, value, description) VALUES (3, 1, 'SSH_ALLOW_NEW_HOSTS', 'True', 'Политика обработки новых SSH-хостов: True  — автоматически добавляет ключи в known_hosts, False — требует предварительного наличия ключей');
INSERT INTO ssh_variables (id, id_host, variable, value, description) VALUES (4, 1, 'SSH_USER', 'root', NULL);
INSERT INTO ssh_variables (id, id_host, variable, value, description) VALUES (5, 2, 'SSH_ALLOW_NEW_HOSTS', 'True', 'Политика обработки новых SSH-хостов: True  — автоматически добавляет ключи в known_hosts, False — требует предварительного наличия ключей');
INSERT INTO ssh_variables (id, id_host, variable, value, description) VALUES (6, 2, 'SSH_KEY_PATH', '.\key\id_ed25519', 'Путь к приватному ключу');
INSERT INTO ssh_variables (id, id_host, variable, value, description) VALUES (7, 2, 'SSH_TIMEOUT', '10', 'Таймаут для операций PostgreSQL по SSH (сек)');
INSERT INTO ssh_variables (id, id_host, variable, value, description) VALUES (8, 2, 'SSH_USER', 'root', NULL);

COMMIT TRANSACTION;
PRAGMA foreign_keys = on;


--
-- Файл сгенерирован с помощью SQLiteStudio v3.4.21 в Чт фев 19 10:54:55 2026
--
-- Использованная кодировка текста: System
--
PRAGMA foreign_keys = off;
BEGIN TRANSACTION;

-- Таблица: execution_results
CREATE TABLE execution_results (
    result_id   INTEGER  PRIMARY KEY AUTOINCREMENT,-- Уникальный идентификатор результата
    task_id     INTEGER  NOT NULL,-- Ссылка на задачу (execution_tasks)
    pg_code     TEXT     NOT NULL,-- Внутренний код приложения (например, pg_0, pg_14)
    exit_code   INTEGER,-- Системный код возврата процесса psql
    stdout_json TEXT,-- Результат запроса в формате JSON-строки
    stderr_text TEXT,-- Текст ошибки из потока stderr (если есть)
    finished_at DATETIME DEFAULT CURRENT_TIMESTAMP,-- Время завершения обработки (UTC)
    /* Реляционная связь: при удалении задачи удаляются и её результаты. */FOREIGN KEY (
        task_id
    )
    REFERENCES execution_tasks (task_id) ON DELETE CASCADE
);

INSERT INTO execution_results (result_id, task_id, pg_code, exit_code, stdout_json, stderr_text, finished_at) VALUES (21, 21, 'pg_0', 0, '[{"table_name": "aggregated_indexes", "total_size": "232 kB"}, {"table_name": "privilege_commands", "total_size": "56 kB"}, {"table_name": "postgres_log", "total_size": "16 kB"}]', '', '2026-02-18 11:09:46');
INSERT INTO execution_results (result_id, task_id, pg_code, exit_code, stdout_json, stderr_text, finished_at) VALUES (22, 22, 'pg_0', 0, '[{"datname": "postgres", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_rox", "datcollate": "en_US.UTF-8"}, {"datname": "template1", "datcollate": "en_US.UTF-8"}, {"datname": "template0", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_volna", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_monro", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_fresh", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_jet", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_izzi", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_legzo", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_starda", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_sol", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_admin", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_lex", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_1go", "datcollate": "en_US.UTF-8"}, {"datname": "demo", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_irwin", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_gizbo", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_drip", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_flagman", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_martin", "datcollate": "en_US.UTF-8"}, {"datname": "demo_test", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_beef", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_fugu", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_patang", "datcollate": "en_US.UTF-8"}, {"datname": "test", "datcollate": "en_US.UTF-8"}]', '', '2026-02-18 11:17:17');
INSERT INTO execution_results (result_id, task_id, pg_code, exit_code, stdout_json, stderr_text, finished_at) VALUES (23, 23, 'pg_0', 0, '[{"datname": "postgres", "datcollate": "en_US.UTF-8"}, {"datname": "template1", "datcollate": "en_US.UTF-8"}, {"datname": "template0", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_admin", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_1go", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_drip", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_fresh", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_gizbo", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_irwin", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_izzi", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_jet", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_legzo", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_lex", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_monro", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_rox", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_sol", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_starda", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_volna", "datcollate": "en_US.UTF-8"}]', '', '2026-02-18 11:17:17');
INSERT INTO execution_results (result_id, task_id, pg_code, exit_code, stdout_json, stderr_text, finished_at) VALUES (24, 24, 'pg_0', 0, '[{"datname": "postgres", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_rox", "datcollate": "en_US.UTF-8"}, {"datname": "template1", "datcollate": "en_US.UTF-8"}, {"datname": "template0", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_volna", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_monro", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_fresh", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_jet", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_izzi", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_legzo", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_starda", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_sol", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_admin", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_lex", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_1go", "datcollate": "en_US.UTF-8"}, {"datname": "demo", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_irwin", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_gizbo", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_drip", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_flagman", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_martin", "datcollate": "en_US.UTF-8"}, {"datname": "demo_test", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_beef", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_fugu", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_patang", "datcollate": "en_US.UTF-8"}, {"datname": "test", "datcollate": "en_US.UTF-8"}]', '', '2026-02-18 11:21:29');
INSERT INTO execution_results (result_id, task_id, pg_code, exit_code, stdout_json, stderr_text, finished_at) VALUES (25, 25, 'pg_0', 0, '[{"datname": "postgres", "datcollate": "en_US.UTF-8"}, {"datname": "template1", "datcollate": "en_US.UTF-8"}, {"datname": "template0", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_admin", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_1go", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_drip", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_fresh", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_gizbo", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_irwin", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_izzi", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_jet", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_legzo", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_lex", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_monro", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_rox", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_sol", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_starda", "datcollate": "en_US.UTF-8"}, {"datname": "messenger_volna", "datcollate": "en_US.UTF-8"}]', '', '2026-02-18 11:21:29');

-- Таблица: execution_tasks
CREATE TABLE execution_tasks (
    task_id     INTEGER  PRIMARY KEY AUTOINCREMENT,-- Уникальный идентификатор задачи
    target_host TEXT     NOT NULL,-- IP или DNS удаленного сервера
    query_text  TEXT     NOT NULL,-- Исходный текст SQL-запроса
    started_at  DATETIME DEFAULT CURRENT_TIMESTAMP-- Время инициации запроса (UTC)
);

INSERT INTO execution_tasks (task_id, target_host, query_text, started_at) VALUES (21, 'prd-msg-pg-03.maxbit.private', 'SELECT relname AS table_name, pg_size_pretty(pg_total_relation_size(relid)) AS total_size FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 10;', '2026-02-18 11:09:46');
INSERT INTO execution_tasks (task_id, target_host, query_text, started_at) VALUES (22, 'dev-msg-pg-01.maxbit.private', 'SELECT datname, datcollate FROM pg_database;', '2026-02-18 11:17:17');
INSERT INTO execution_tasks (task_id, target_host, query_text, started_at) VALUES (23, 'prd-msg-pg-03.maxbit.private', 'SELECT datname, datcollate FROM pg_database;', '2026-02-18 11:17:17');
INSERT INTO execution_tasks (task_id, target_host, query_text, started_at) VALUES (24, 'dev-msg-pg-01.maxbit.private', 'SELECT datname, datcollate FROM pg_database;', '2026-02-18 11:21:29');
INSERT INTO execution_tasks (task_id, target_host, query_text, started_at) VALUES (25, 'prd-msg-pg-03.maxbit.private', 'SELECT datname, datcollate FROM pg_database;', '2026-02-18 11:21:29');

COMMIT TRANSACTION;
PRAGMA foreign_keys = on;
