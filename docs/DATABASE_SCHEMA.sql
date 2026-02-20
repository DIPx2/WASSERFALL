-- Конфигурационная БД: wasserfall_config.db
CREATE TABLE hosts (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT    UNIQUE NOT NULL,
    toggle INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE ssh_variables (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    id_host  INTEGER NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
    variable TEXT    NOT NULL,
    value    TEXT    NOT NULL,
    description TEXT,
    UNIQUE(id_host, variable)
);

CREATE TABLE postgre_variables (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    id_host  INTEGER NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
    variable TEXT    NOT NULL,
    value    TEXT    NOT NULL,
    description TEXT,
    UNIQUE(id_host, variable)
);

CREATE TABLE sql_commands (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    UNIQUE NOT NULL,
    template    TEXT    NOT NULL,
    description TEXT
);

-- БД Логирования: wasserfall_logger.db
CREATE TABLE execution_tasks (
    task_id     INTEGER  PRIMARY KEY AUTOINCREMENT,
    target_host TEXT     NOT NULL,
    query_text  TEXT     NOT NULL,
    started_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE execution_results (
    result_id   INTEGER  PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER  NOT NULL,
    pg_code     TEXT     NOT NULL,
    exit_code   INTEGER,
    stdout_json TEXT,
    stderr_text TEXT,
    finished_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(task_id) REFERENCES execution_tasks(task_id) ON DELETE CASCADE
);