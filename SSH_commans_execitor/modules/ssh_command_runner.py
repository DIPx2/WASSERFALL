"""
Модуль выполнения произвольных SSH-команд.
Использует существующее SSH-соединение от getter.py.
"""
from typing import Dict, Any, Tuple
from paramiko import SSHClient


def _classify_ssh_command_error(stderr: str, exit_code: int) -> str:
    """Классифицировать ошибку выполнения SSH-команды."""
    err = stderr.lower()
    
    if "permission denied" in err:
        return "cmd_12"
    if "not found" in err or "no such file" in err:
        return "cmd_10"
    if "timeout" in err:
        return "cmd_16"
    if "sudo" in err and "password" in err:
        return "cmd_12"
    if exit_code != 0:
        return "cmd_18"
    
    return "cmd_99"


def run_ssh_command(
    ssh_client: SSHClient,
    command: str,
    sudo: bool = False,
    sudo_user: str = "root",
    timeout: int = 60,
    get_pty: bool = False,
) -> Tuple[Dict[str, Any], str]:
    """
    Выполнить команду на удалённом хосте через SSH.
    """
    if sudo:
        full_command = "sudo -u " + sudo_user + " " + command
    else:
        full_command = command
    
    try:
        stdin, stdout, stderr = ssh_client.exec_command(
            full_command,
            timeout=timeout,
            get_pty=get_pty
        )
        
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()
        
        result = {
            "stdout": out,
            "stderr": err,
            "exit_code": exit_code,
            "command": command
        }
        
        if exit_code == 0:
            return result, "cmd_0"
        else:
            return result, _classify_ssh_command_error(err, exit_code)
            
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "command": command
        }, "ssh_99"