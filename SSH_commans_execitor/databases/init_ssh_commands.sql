-- Добавить SSH-команды в существующую таблицу sql_commands
-- (переиспользуем структуру DATABASE_SCHEMA.sql)

INSERT OR IGNORE INTO sql_commands (name, template, description) VALUES
    ('ssh_check_disk', 'df -h /', 'Проверка места на диске'),
    ('ssh_check_memory', 'free -m', 'Проверка памяти'),
    ('ssh_check_uptime', 'uptime', 'Время работы системы'),
    ('ssh_check_load', 'cat /proc/loadavg', 'Загрузка CPU'),
    ('ssh_restart_service', 'systemctl restart {{service_name}}', 'Перезапуск сервиса'),
    ('ssh_check_logs', 'tail -n {{lines}} /var/log/syslog', 'Просмотр логов'),
    ('ssh_whoami', 'whoami', 'Текущий пользователь'),
    ('ssh_hostname', 'hostname', 'Имя хоста'),
    ('ssh_check_services', 'systemctl list-units --type=service --state=running', 'Список активных сервисов'),
    ('ssh_check_network', 'ip addr show', 'Сетевые интерфейсы');
