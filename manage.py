#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path


def _delegate_runserver_if_needed():
    """
    Keep the normal `python manage.py runserver` command working on this PC.

    The original venv uses a Python 3.12 build whose socket server path exits
    after system checks here. For runserver only, hand off to the clean local
    Python 3.11 runtime and the numeric-only server wrapper.
    """
    if len(sys.argv) < 2 or sys.argv[1] != 'runserver':
        return

    project_root = Path(__file__).resolve().parent
    server_py = project_root / 'neverq_server.py'
    preferred_python = project_root / 'venv_server' / 'Scripts' / 'python.exe'
    target_python = preferred_python if preferred_python.exists() else Path(sys.executable)

    bind = ''
    for arg in sys.argv[2:]:
        if not arg.startswith('-'):
            bind = arg
            break
    if bind:
        os.environ['NEVERQ_BIND'] = bind

    os.environ.setdefault('NEVERQ_BASE_DIR', str(project_root))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'neverq.settings')
    os.execv(str(target_python), [str(target_python), str(server_py)])

def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'neverq.settings')
    _delegate_runserver_if_needed()
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
