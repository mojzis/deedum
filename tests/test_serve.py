from __future__ import annotations

import http.client
import socket
import tempfile
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from deedum import DeedumError, Site, load_site
from deedum import serve as serve_mod
from deedum.serve import _Builds, _read, _resolve, serve, watched

BASE = "/demo/"
TOML = f'title = "Demo"\nbase_url = "https://example.test"\nbase_path = "{BASE}"\n'
WAIT = 15.0
HOME = "/"
NO_SLASH = "/demo"
BLOG = f"{BASE}blog/one/"
BLOG_BARE = f"{BASE}blog/one"
A_TXT = f"{BASE}a.txt"
SITEMAP = f"{BASE}sitemap.xml"
BLOB = f"{BASE}blob.zzz"
NOPE = f"{BASE}nope/"
OTHER = "/other/"
DEMONIC = "/demonic/"
MOVED = "/moved/"
MARKER = f"{BASE}marker/"
PAGE = (
    '{% extends "deedum/base.html" %}{% block content %}'
    "<p>{{ page.title }} {{ extra | default('') }}</p>{% endblock %}"
)


def put(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def until(condition: Callable[[], object], timeout: float = WAIT) -> bool:
    """Poll ``condition`` until it is truthy or ``timeout`` seconds pass."""
    waiter = threading.Event()
    for _ in range(int(timeout / 0.05)):
        if condition():
            return True
        waiter.wait(0.05)
    return bool(condition())


class Running:
    """A serve() in a thread on port 0, with its output and any failure."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.said: list[str] = []
        self.complained: list[str] = []
        self.stop = threading.Event()
        self.up = threading.Event()
        self.port = 0
        self.failure: BaseException | None = None
        self.thread = threading.Thread(target=self._run)

    def _run(self) -> None:
        def ready(port: int) -> None:
            self.port = port
            self.up.set()

        try:
            serve(
                lambda url: load_site(self.root, base_url=url),
                port=0,
                say=self.said.append,
                complain=self.complained.append,
                stop_event=self.stop,
                ready=ready,
            )
        except BaseException as failure:
            self.failure = failure
            self.up.set()

    def start(self) -> Running:
        self.thread.start()
        assert self.up.wait(WAIT)
        assert self.failure is None
        return self

    def close(self) -> None:
        self.stop.set()
        self.thread.join(WAIT)
        assert not self.thread.is_alive()

    def get(
        self, path: str, method: str = "GET"
    ) -> tuple[int, str, http.client.HTTPMessage]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=WAIT)
        try:
            conn.request(method, path)
            reply = conn.getresponse()
            return reply.status, reply.read().decode("utf-8", "replace"), reply.msg
        finally:
            conn.close()

    def body(self, path: str = BASE) -> str:
        return self.get(path)[1]

    def serving(self, text: str, path: str = BASE) -> bool:
        return text in self.body(path)

    def rebuilds(self) -> int:
        return sum(line.startswith("rebuilt: ") for line in self.said)


@pytest.fixture(autouse=True)
def tmp_builds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Send serve's temp build folders to a folder the test can inspect."""
    folder = tmp_path / "tmp"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "site"
    put(path / "deedum.toml", TOML)
    put(path / "content" / "index.md", "# Home\n\nHello.\n")
    put(path / "content" / "blog" / "one.md", "# One\n\nPost.\n")
    put(path / "static" / "a.txt", "plain")
    put(path / "templates" / "page.html", PAGE)
    return path


@pytest.fixture
def running(root: Path) -> Iterator[Running]:
    run = Running(root).start()
    yield run
    run.close()


def save_many(root: Path, times: int) -> None:
    """Write the home page ``times`` times in a row, with no pause."""
    for i in range(times):
        put(root / "content" / "index.md", f"# Home\n\nsave {i}\n")


def builds_on_disk(tmp_builds: Path) -> list[str]:
    return sorted(p.name for p in tmp_builds.iterdir())


# ---- requests --------------------------------------------------------------


def test_startup_prints_the_url_and_the_watched_folder(running, root):
    assert running.said[:2] == [
        f"serving http://localhost:{running.port}{BASE}",
        f"watching {root.resolve()}",
    ]


def test_pages_carry_the_localhost_absolute_url(running):
    status, body, headers = running.get(BASE)
    assert status == 200
    assert f'href="http://localhost:{running.port}{BASE}"' in body
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert headers["Cache-Control"] == "no-store"


def test_root_redirects_to_the_base_path(running):
    status, _, headers = running.get(HOME)
    assert (status, headers["Location"]) == (302, BASE)


def test_base_path_without_slash_redirects(running):
    status, _, headers = running.get(f"{NO_SLASH}?x=1")
    assert (status, headers["Location"]) == (301, f"{BASE}?x=1")


def test_folder_without_slash_redirects_to_the_slash_form(running):
    status, _, headers = running.get(f"{BLOG_BARE}?x=1")
    assert (status, headers["Location"]) == (301, f"{BLOG}?x=1")


def test_folder_and_file_responses(running):
    assert running.get(BLOG)[0] == 200
    status, body, headers = running.get(A_TXT)
    assert (status, body) == (200, "plain")
    assert headers["Content-Type"] == "text/plain; charset=utf-8"
    sitemap = running.get(SITEMAP)
    assert sitemap[2]["Content-Type"] == "text/xml; charset=utf-8"


def test_unknown_extension_is_octet_stream(running, root):
    (root / "static" / "blob.zzz").write_bytes(b"\x00\x01")
    assert until(lambda: running.get(BLOB)[0] == 200)
    assert running.get(BLOB)[2]["Content-Type"] == "application/octet-stream"


def test_missing_file_serves_the_404_page_with_status_404(running):
    status, body, headers = running.get(NOPE)
    assert status == 404
    assert "Back to Demo" in body
    assert headers["Content-Type"] == "text/html; charset=utf-8"


def test_path_outside_the_base_path_is_404(running):
    assert running.get(OTHER)[0] == 404
    assert running.get(DEMONIC)[0] == 404


def test_head_has_no_body_but_a_length(running):
    status, body, headers = running.get(BASE, "HEAD")
    assert (status, body) == (200, "")
    assert int(headers["Content-Length"]) > 100


@pytest.mark.parametrize(
    "path",
    [
        "/demo/../deedum.toml",
        "/demo/%2e%2e/deedum.toml",
        "/demo/..%2fdeedum.toml",
        "/demo/%2E%2E/%2E%2E/etc/passwd",
        "/demo/../../../../etc/passwd",
        "/demo//etc/passwd",
        "/demo/a.txt%00.html",
    ],
)
def test_traversal_never_leaves_the_build_folder(running, path):
    status, body, _ = running.get(path)
    assert status == 404
    assert "root:" not in body
    assert "Demo" not in body or "Back to Demo" in body


def test_unsupported_method_is_reported_on_stderr(running):
    status, _, _ = running.get(BASE, "PUT")
    assert status == 501
    assert any(line.startswith("error: ") for line in running.complained)


def test_requests_are_not_logged(running):
    running.get(BASE)
    assert [line for line in running.said if "GET" in line] == []


# ---- _resolve, _read and _Builds as units ----------------------------------


@pytest.fixture
def build_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "build"
    put(folder / "index.html", "home")
    put(folder / "x" / "index.html", "x")
    outside = tmp_path / "outside"
    put(outside / "secret.txt", "secret")
    put(outside / "index.html", "secret index")
    (folder / "link.txt").symlink_to(outside / "secret.txt")
    (folder / "linkdir").symlink_to(outside)
    return folder.resolve()


def test_symlink_to_a_file_outside_is_404(build_dir):
    assert _resolve(build_dir, HOME, f"{HOME}link.txt").status == 404


def test_symlinked_folder_outside_is_404(build_dir):
    assert _resolve(build_dir, HOME, f"{HOME}linkdir/secret.txt").status == 404
    assert _resolve(build_dir, HOME, f"{HOME}linkdir/").status == 404
    assert _resolve(build_dir, HOME, f"{HOME}linkdir").status == 404


def test_symlinked_404_page_outside_is_not_served(build_dir, tmp_path):
    (build_dir / "404.html").symlink_to(tmp_path / "outside" / "secret.txt")
    reply = _resolve(build_dir, HOME, f"{HOME}missing")
    assert (reply.status, reply.body) == (404, b"not found\n")


def test_unreadable_target_is_a_404(build_dir):
    assert _read(build_dir, build_dir / "x").status == 404


def test_builds_before_the_first_install_say_building(tmp_path):
    assert _Builds(print).reply(HOME).status == 503


def test_builds_keep_two_and_delete_the_rest(tmp_path):
    builds = _Builds(print)
    site = Site(title="T", base_url="https://e.test", root=tmp_path)
    folders = [tmp_path / name for name in "abc"]
    list(map(Path.mkdir, folders))
    builds.install(folders[0], site)
    builds.install(folders[1], site)
    builds.install(folders[2], site)
    assert [f.exists() for f in folders] == [False, True, True]
    builds.close()
    assert [f.exists() for f in folders] == [False, False, False]


# ---- the watch filter ------------------------------------------------------


@pytest.fixture
def folders(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "site", tmp_path / "site" / "_site"


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("content/index.md", True),
        ("deedum.toml", True),
        ("app.py", True),
        ("_site/index.html", False),
        ("_site/a/b.html", False),
        ("__pycache__/app.cpython-313.pyc", False),
        ("pkg/__pycache__/x.pyc", False),
        (".git/index", False),
        (".venv/lib/x.py", False),
        ("node_modules/x/y.js", False),
        (".hidden", False),
        ("content/.index.md.swp", False),
        ("content/index.md~", False),
        ("_siteX/index.html", True),
    ],
)
def test_watch_filter(folders, rel, expected):
    root, out = folders
    assert watched(root, out, str(root / rel)) is expected


def test_watch_filter_ignores_paths_outside_the_root(folders, tmp_path):
    root, out = folders
    assert watched(root, out, str(tmp_path / "elsewhere" / "x.md")) is False


def test_a_dotted_parent_of_the_root_does_not_hide_everything(tmp_path):
    root = tmp_path / ".orch" / "site"
    assert watched(root, root / "_site", str(root / "content" / "a.md")) is True


# ---- rebuilds --------------------------------------------------------------


def test_edit_is_served_after_a_rebuild(running, root):
    put(root / "content" / "index.md", "# Changed\n\nText.\n")
    assert until(lambda: running.serving("Changed"))
    assert running.said[-1] == "rebuilt: pages 2"


def test_failed_rebuild_keeps_the_old_build_and_fixing_it_rebuilds(running, root):
    put(root / "templates" / "page.html", "{% if %}")
    assert until(lambda: running.complained)
    assert running.complained[0].startswith("error: cannot render 'page.html'")
    status, body, _ = running.get(BASE)
    assert (status, "Home" in body) == (200, True)
    put(root / "templates" / "page.html", PAGE.replace("<p>", "<p>FIXED "))
    assert until(lambda: running.serving("FIXED"))


def test_failed_rebuild_prints_the_hint(running, root):
    put(root / "deedum.toml", TOML + 'titel = "x"\n')
    assert until(lambda: len(running.complained) >= 2)
    assert running.complained[0].startswith("error: ")
    assert running.complained[1].startswith("hint: ")


def test_invalid_config_mid_serve_keeps_serving_and_restoring_rebuilds(running, root):
    put(root / "deedum.toml", "title = [")
    assert until(lambda: running.complained)
    assert running.get(BASE)[0] == 200
    put(root / "deedum.toml", TOML)
    assert until(lambda: running.rebuilds() >= 1)


def test_config_change_moves_the_base_path(running, root):
    put(root / "deedum.toml", TOML.replace(BASE, MOVED))
    assert until(lambda: running.get(MOVED)[0] == 200)
    assert running.get(HOME)[2]["Location"] == MOVED
    assert running.get(BASE)[0] == 404


def test_os_error_in_a_rebuild_is_reported_without_a_hint(running, root, monkeypatch):
    def boom(site: Site, out: Path) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(serve_mod, "build_site", boom)
    put(root / "content" / "index.md", "# Changed\n")
    assert until(lambda: running.complained)
    assert running.complained == ["error: denied"]
    assert running.get(BASE)[0] == 200


def test_app_hook_failure_mid_serve_keeps_the_old_page(tmp_path):
    root = tmp_path / "hooked"
    put(root / "deedum.toml", TOML + 'app = "app:Mine"\n')
    put(root / "content" / "index.md", "# Home\n")
    put(root / "templates" / "page.html", PAGE)
    good = (
        "from deedum import App\n\nclass Mine(App):\n"
        "    def context(self, page):\n        return {'extra': 'GOOD'}\n"
    )
    put(root / "app.py", good)
    run = Running(root).start()
    try:
        assert run.serving("GOOD")
        put(
            root / "app.py",
            good.replace("return {", "raise ValueError('bad'); return {"),
        )
        assert until(lambda: any("context" in line for line in run.complained))
        assert run.serving("GOOD")
        put(root / "app.py", good.replace("GOOD", "BETTER"))
        assert until(lambda: run.serving("BETTER"))
    finally:
        run.close()


def test_edited_helper_module_is_reloaded_between_rebuilds(tmp_path):
    root = tmp_path / "helped"
    put(root / "deedum.toml", TOML + 'app = "app:Mine"\n')
    put(root / "content" / "index.md", "# Home\n")
    put(root / "templates" / "page.html", PAGE)
    put(root / "helper.py", "VALUE = 'one'\n")
    put(
        root / "app.py",
        "from deedum import App\nfrom helper import VALUE\n\n"
        "class Mine(App):\n    def context(self, page):\n"
        "        return {'extra': VALUE}\n",
    )
    run = Running(root).start()
    try:
        assert run.serving("one")
        put(root / "helper.py", "VALUE = 'two'\n")
        assert until(lambda: run.serving("two"))
    finally:
        run.close()


def test_burst_of_saves_gives_at_most_two_rebuilds(root, monkeypatch):
    count = []
    real = serve_mod.build_site

    def counting(site: Site, out: Path):
        count.append(1)
        return real(site, out)

    monkeypatch.setattr(serve_mod, "build_site", counting)
    run = Running(root).start()
    try:
        save_many(root, 20)
        assert until(lambda: run.serving("save 19"))
        settled = threading.Event()
        settled.wait(1.0)
        assert 2 <= len(count) <= 3
    finally:
        run.close()


def test_writes_into_out_and_pycache_do_not_rebuild(running, root):
    put(root / "_site" / "index.html", "x")
    put(root / "__pycache__" / "m.pyc", "x")
    put(root / "content" / ".hidden.md~", "x")
    put(root / "content" / "marker.md", "# Marker\n")
    assert until(lambda: running.serving("Marker", MARKER))
    assert running.rebuilds() <= 1


def edit_rounds(run: Running, root: Path, tmp_builds: Path, rounds: int) -> int:
    """Edit and wait ``rounds`` times; the most build folders seen on disk."""
    most = 0
    for i in range(rounds):
        put(root / "content" / "index.md", f"# Round{i}\n")
        assert until(lambda i=i: run.serving(f"Round{i}"))
        most = max(most, len(builds_on_disk(tmp_builds)))
    return most


def test_only_two_build_folders_exist_and_none_after_stop(root, tmp_builds):
    run = Running(root).start()
    try:
        most = edit_rounds(run, root, tmp_builds, 4)
    finally:
        run.close()
    assert most <= 2
    assert builds_on_disk(tmp_builds) == []


def test_the_configured_out_folder_is_never_touched(root):
    run = Running(root).start()
    try:
        put(root / "content" / "index.md", "# Again\n")
        assert until(lambda: run.serving("Again"))
    finally:
        run.close()
    assert not (root / "_site").exists()


# ---- startup failures and exit ---------------------------------------------


def test_port_in_use_is_an_error_naming_the_port(root, tmp_builds):
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        port = holder.getsockname()[1]
        with pytest.raises(DeedumError, match=f"port {port}") as caught:
            serve(
                lambda url: load_site(root, base_url=url),
                port=port,
                say=print,
                complain=print,
            )
    assert caught.value.hint == "pass --port with a free port"
    assert builds_on_disk(tmp_builds) == []


def test_first_build_failure_raises_and_cleans_up(root, tmp_builds):
    put(root / "templates" / "page.html", "{% if %}")
    run = Running(root)
    run.thread.start()
    run.thread.join(WAIT)
    assert isinstance(run.failure, DeedumError)
    assert builds_on_disk(tmp_builds) == []


def test_first_config_failure_raises(root):
    put(root / "deedum.toml", "title = [")
    run = Running(root)
    run.thread.start()
    run.thread.join(WAIT)
    assert isinstance(run.failure, DeedumError)


def test_interrupt_stops_everything_and_cleans_up(root, tmp_builds, monkeypatch):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(serve_mod, "watch", interrupted)
    with pytest.raises(KeyboardInterrupt):
        serve(
            lambda url: load_site(root, base_url=url),
            port=0,
            say=print,
            complain=print,
        )
    assert builds_on_disk(tmp_builds) == []


def test_stop_event_releases_the_port(root):
    run = Running(root).start()
    port = run.port
    run.close()
    with socket.socket() as again:
        again.bind(("127.0.0.1", port))
        assert again.getsockname()[1] == port
