"""Build into temp folders, serve the newest good build, rebuild on change (R22).

See decision 0015. Binds ``127.0.0.1`` only, serves only files that resolve
inside the current build folder, and never touches the configured ``out`` folder.
"""

from __future__ import annotations

import mimetypes
import shutil
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from watchfiles import watch

from deedum.app import build as build_site
from deedum.builder import BuildReport
from deedum.errors import DeedumError
from deedum.site import Site

HOST = "127.0.0.1"
DEBOUNCE_MS = 300
_SKIP_PARTS = frozenset({"__pycache__", "node_modules"})
_NOT_FOUND = "404.html"
_INDEX = "index.html"


@dataclass(frozen=True)
class _Reply:
    status: int
    body: bytes = b""
    content_type: str = "text/plain; charset=utf-8"
    location: str = ""


def _inside(root: Path, path: Path) -> bool:
    return path.resolve().is_relative_to(root)


def _slurp(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _missing(root: Path) -> _Reply:
    page = root / _NOT_FOUND
    body = _slurp(page) if _inside(root, page) else None
    if body is None:
        return _Reply(404, b"not found\n")
    return _Reply(404, body, "text/html; charset=utf-8")


def _redirect(status: int, where: str, query: str = "") -> _Reply:
    return _Reply(
        status, location=quote(where, safe="/") + (f"?{query}" if query else "")
    )


def _redirect_for(base_path: str, path: str, query: str) -> _Reply | None:
    if path == "/" and base_path != "/":
        return _redirect(302, base_path)
    if f"{path}/" == base_path:
        return _redirect(301, base_path, query)
    return None


def _target(root: Path, base_path: str, path: str) -> Path | None:
    """The file or folder ``path`` names inside ``root``, or None when it is not ok."""
    if "\0" in path or not path.startswith(base_path):
        return None
    rel = path[len(base_path) :].lstrip("/")
    target = root / rel
    return None if ".." in rel.split("/") or not _inside(root, target) else target


def _read(root: Path, target: Path) -> _Reply:
    body = _slurp(target)
    if body is None:
        return _missing(root)
    kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if kind.startswith("text/"):
        kind += "; charset=utf-8"
    return _Reply(200, body, kind)


def _resolve(root: Path, base_path: str, raw: str) -> _Reply:
    """The reply for request target ``raw`` against the build folder ``root``."""
    split = urlsplit(raw)
    path = unquote(split.path)
    if redirect := _redirect_for(base_path, path, split.query):
        return redirect
    target = _target(root, base_path, path)
    if target is None:
        return _missing(root)
    if target.is_dir():
        if not path.endswith("/"):
            return _redirect(301, f"{path}/", split.query)
        target /= _INDEX
    if not (_inside(root, target) and target.is_file()):
        return _missing(root)
    return _read(root, target)


class _Builds:
    """The current and the previous build folder, and what the handler needs."""

    def __init__(self, complain: Callable[[str], None]) -> None:
        self.complain = complain
        self.out = Path()
        self._lock = threading.Lock()
        self._current: Path | None = None
        self._previous: Path | None = None
        self._base_path = "/"

    def reply(self, raw: str) -> _Reply:
        with self._lock:
            if self._current is None:  # unreachable once serving starts
                return _Reply(503, b"building\n")
            return _resolve(self._current, self._base_path, raw)

    def install(self, folder: Path, site: Site) -> None:
        """Switch to ``folder``; delete the build before the previous one."""
        with self._lock:
            old = self._previous
            self._previous, self._current = self._current, folder.resolve()
            self._base_path = site.base_path
            self.out = (site.root / site.out).resolve()
            if old is not None:
                shutil.rmtree(old, ignore_errors=True)

    def close(self) -> None:
        """Delete every build folder this object still knows."""
        with self._lock:
            for folder in (self._current, self._previous):
                if folder is not None:
                    shutil.rmtree(folder, ignore_errors=True)
            self._current = self._previous = None


class _Handler(BaseHTTPRequestHandler):
    def __init__(self, builds: _Builds, *args: Any, **kwargs: Any) -> None:
        self.builds = builds
        super().__init__(*args, **kwargs)

    def _answer(self, *, head: bool) -> None:
        reply = self.builds.reply(self.path)
        self.send_response(reply.status)
        if reply.location:
            self.send_header("Location", reply.location)
        self.send_header("Content-Type", reply.content_type)
        self.send_header("Content-Length", str(len(reply.body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head:
            self.wfile.write(reply.body)

    def do_GET(self) -> None:
        self._answer(head=False)

    def do_HEAD(self) -> None:
        self._answer(head=True)

    def log_message(self, format: str, *args: Any) -> None:
        """No per-request logging."""

    def log_error(self, format: str, *args: Any) -> None:
        self.builds.complain(f"error: {format % args}")


def watched(root: Path, out: Path, path: str) -> bool:
    """Whether a change at ``path`` should trigger a rebuild."""
    here = Path(path)
    if not here.is_relative_to(root) or here.is_relative_to(out):
        return False
    parts = here.relative_to(root).parts
    return not (
        here.name.endswith("~")
        or any(p.startswith(".") or p in _SKIP_PARTS for p in parts)
    )


def _build(load: Callable[[str], Site], port: int, builds: _Builds) -> BuildReport:
    """Build into a fresh temp folder and switch to it only when that succeeds."""
    site = load(f"http://localhost:{port}")
    folder = Path(tempfile.mkdtemp(prefix="deedum-serve-"))
    try:
        report = build_site(site, folder)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    builds.install(folder, site)
    return report


def _listen(port: int, builds: _Builds) -> ThreadingHTTPServer:
    try:
        return ThreadingHTTPServer((HOST, port), partial(_Handler, builds))
    except OSError as err:
        msg = f"cannot listen on port {port}: {err.strerror or err}"
        raise DeedumError(msg, hint="pass --port with a free port") from err


def serve(  # noqa: PLR0913 -- one keyword per seam the CLI and the tests use
    load: Callable[[str], Site],
    *,
    port: int,
    say: Callable[[str], None],
    complain: Callable[[str], None],
    stop_event: threading.Event | None = None,
    ready: Callable[[int], None] | None = None,
) -> None:
    """Serve ``load(base_url)`` on ``127.0.0.1:port`` until ``stop_event`` is set.

    ``load`` loads the Site afresh, given the ``base_url`` to build with. A failed
    first build raises; a failed rebuild is reported and the old build stays.
    ``ready`` gets the bound port once the first build is being served.
    """
    stop = stop_event or threading.Event()
    builds = _Builds(complain)
    httpd = _listen(port, builds)
    bound = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, args=(0.1,), daemon=True)
    try:
        _build(load, bound, builds)
        site = load(f"http://localhost:{bound}")
        root = site.root.resolve()
        thread.start()
        say(f"serving http://localhost:{bound}{site.base_path}")
        say(f"watching {root}")
        if ready is not None:
            ready(bound)
        changes = watch(
            root,
            watch_filter=lambda _kind, path: watched(root, builds.out, path),
            debounce=DEBOUNCE_MS,
            stop_event=stop,
        )
        for _ in changes:
            try:
                report = _build(load, bound, builds)
            except (DeedumError, OSError) as failure:
                complain(f"error: {failure}")
                if isinstance(failure, DeedumError) and failure.hint:
                    complain(f"hint: {failure.hint}")
            else:
                say(f"rebuilt: pages {report.pages}")
    finally:
        if thread.is_alive():
            httpd.shutdown()
            thread.join()
        httpd.server_close()
        builds.close()
