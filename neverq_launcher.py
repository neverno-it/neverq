import ctypes
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path


APP_URL = "http://127.0.0.1:8000/"
SERVER_BIND = "127.0.0.1:8000"
STARTUP_TIMEOUT_SECONDS = 25


def _message_box(title, text, flags=0x10):
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, flags)
    except Exception:
        pass


def _project_root():
    source = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()
    return source.parent


def _server_is_ready():
    try:
        with urllib.request.urlopen(APP_URL, timeout=1) as response:
            return 200 <= response.status < 500
    except Exception:
        return False


def _wait_for_server():
    deadline = time.time() + STARTUP_TIMEOUT_SECONDS
    while time.time() < deadline:
        if _server_is_ready():
            return True
        time.sleep(0.5)
    return False


def _start_server_console(project_root):
    bundled_server = project_root / "NeverQ Server.exe"
    if bundled_server.exists():
        env = os.environ.copy()
        env.setdefault("NEVERQ_BIND", SERVER_BIND)
        env.setdefault("NEVERQ_BASE_DIR", str(project_root))
        subprocess.Popen(
            [str(bundled_server)],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            cwd=str(project_root),
            env=env,
        )
        return True

    python_exe = project_root / "venv_server" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = project_root / "venv" / "Scripts" / "python.exe"
    manage_py = project_root / "manage.py"

    if not python_exe.exists():
        _message_box(
            "NeverQ",
            f"Could not find the virtual environment Python at:\n{python_exe}",
        )
        return False

    if not manage_py.exists():
        _message_box(
            "NeverQ",
            f"Could not find manage.py at:\n{manage_py}",
        )
        return False

    server_py = project_root / "neverq_server.py"
    command = f'cd /d "{project_root}" && "{python_exe}" "{server_py}"'
    subprocess.Popen(
        ["cmd.exe", "/k", command],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        cwd=str(project_root),
    )
    return True


def main():
    project_root = _project_root()
    os.chdir(project_root)

    if not _server_is_ready():
        started = _start_server_console(project_root)
        if not started:
            return
        _wait_for_server()

    try:
        webbrowser.open(APP_URL)
    except Exception:
        _message_box(
            "NeverQ",
            f"NeverQ started, but the browser could not be opened automatically.\n\nOpen this URL manually:\n{APP_URL}",
            flags=0x40,
        )


if __name__ == "__main__":
    main()
