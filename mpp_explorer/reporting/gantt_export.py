from __future__ import annotations

import socket
import socketserver
import threading
import webbrowser
from functools import lru_cache, partial
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

from ..analysis.gantt_graph import build_gantt_payload
from ..analysis.schedule import ScheduleAnalysisOptions
from ..model.project import Project
from .gantt_builder import build_gantt_html


_SERVER_LOCK = threading.Lock()
_SERVER: socketserver.TCPServer | None = None
_SERVER_THREAD: threading.Thread | None = None
_SERVER_PORT: int | None = None


def export_static_gantt(
    project: Project,
    output_html: str | Path,
    options: ScheduleAnalysisOptions | None = None,
) -> Path:
    payload = build_gantt_payload(project, options=options)
    html = build_gantt_html(payload)

    output_path = Path(output_html)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path.resolve()


def open_dynamic_gantt(
    project: Project,
    reports_dir: Path,
    filename: str = "_preview_3d_gantt.html",
    options: ScheduleAnalysisOptions | None = None,
) -> str:
    payload = build_gantt_payload(project, options=options)
    html = build_gantt_html(payload)

    reports_path = Path(reports_dir)
    reports_path.mkdir(parents=True, exist_ok=True)

    output_path = reports_path / filename
    output_path.write_text(html, encoding="utf-8")

    port = _ensure_server(reports_path)
    url = f"http://127.0.0.1:{port}/{filename}"
    webbrowser.open(url)
    return url


@lru_cache(maxsize=1)
def _cached_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _ensure_server(reports_dir: Path) -> int:
    global _SERVER, _SERVER_THREAD, _SERVER_PORT

    with _SERVER_LOCK:
        if _SERVER is not None and _SERVER_THREAD is not None and _SERVER_THREAD.is_alive():
            return _SERVER_PORT if _SERVER_PORT is not None else _cached_port()

        port = _cached_port()

        class SilentHandler(SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                del format, args

        handler_factory = partial(SilentHandler, directory=str(reports_dir))
        httpd = socketserver.TCPServer(("127.0.0.1", port), handler_factory)
        httpd.daemon_threads = True

        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        _SERVER = httpd
        _SERVER_THREAD = thread
        _SERVER_PORT = port

        return port
