import os
import socket
import socketserver
import sys
from pathlib import Path


def _project_root():
    source = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()
    return source.parent


def _parse_bind(value):
    value = (value or "127.0.0.1:8000").strip()
    if value.isdigit():
        return "127.0.0.1", int(value)
    if value.startswith("[") and "]:" in value:
        host, port = value.rsplit(":", 1)
        return host.strip("[]") or "127.0.0.1", int(port)
    if ":" in value:
        host, port = value.rsplit(":", 1)
        host = (host or "127.0.0.1").strip()
        if host.lower() == "localhost":
            host = "127.0.0.1"
        return host, int(port)
    return "127.0.0.1", int(value)


def _run_local_wsgi_server(bind):
    """
    Run Django without Django's dev-server name lookups.

    This machine's Python socket name-resolution path can hard-crash while
    Django runserver is binding to 127.0.0.1. The WSGI app itself is fine, so
    keep the local dev server numeric-only and avoid socket.getfqdn/getaddrinfo.
    """
    import django
    from django.conf import settings
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from django.core.checks import run_checks
    from django.core.handlers.wsgi import WSGIHandler
    from django.core.management import color_style
    from django.core.servers.basehttp import WSGIRequestHandler, WSGIServer

    django.setup()

    errors = run_checks()
    style = color_style()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        raise SystemExit(1)
    print("System check identified no issues (0 silenced).")

    class NeverQLocalServer(socketserver.ThreadingMixIn, WSGIServer):
        daemon_threads = True
        allow_reuse_address = True

        def server_bind(self):
            if hasattr(socket, "SO_REUSEADDR"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(self.server_address)
            self.server_name = "localhost"
            self.server_port = self.server_address[1]
            self.setup_environ()

        def server_activate(self):
            self.socket.listen(self.request_queue_size)

    host, port = _parse_bind(bind)
    app = WSGIHandler()
    if settings.DEBUG:
        app = StaticFilesHandler(app)

    try:
        httpd = NeverQLocalServer((host, port), WSGIRequestHandler, ipv6=False)
    except OSError as exc:
        print(style.ERROR(f"Error: {exc}"), file=sys.stderr)
        raise SystemExit(1)

    httpd.set_app(app)
    print(f"Serving NeverQ at http://127.0.0.1:{port}/")
    print("Quit the server with CTRL-BREAK.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        httpd.server_close()


def main():
    project_root = _project_root()
    os.chdir(project_root)

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    os.environ.setdefault("NEVERQ_BASE_DIR", str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "neverq.settings")

    server_bind = os.environ.get("NEVERQ_BIND", "127.0.0.1:8000")
    _run_local_wsgi_server(server_bind)


if __name__ == "__main__":
    main()
