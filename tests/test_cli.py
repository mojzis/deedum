from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import typer.main
from typer.testing import CliRunner

from deedum import cli
from deedum.config import _KNOWN
from deedum.guide import Topic, detect, render

runner = CliRunner()
SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" fill="#cc3333"/></svg>'
)
BASE = "/demo/"
TOML = 'title = "Demo"\nbase_url = "https://example.test"\nbase_path = "/demo/"\n'


def put(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "site"
    put(root / "deedum.toml", TOML)
    put(root / "content" / "index.md", "# Home\n\nHello.\n")
    put(root / "content" / "blog" / "one.md", "# One\n\nPost.\n")
    put(root / "static" / "robots-extra.txt", "static")
    monkeypatch.chdir(root)
    return root


def track(site: Path) -> None:
    """Make git track ``_site/kept.txt`` in a fresh repo at ``site``."""
    for args in (["init", "-q"], ["add", "-f", "_site/kept.txt"]):
        subprocess.run(["git", *args], cwd=site, check=True)  # noqa: S603, S607 -- test repo


def run(*args: str):
    return runner.invoke(cli.app, list(args))


def test_help_lists_commands_and_points_at_guide():
    result = run("--help")
    assert result.exit_code == 0
    assert all(name in result.stdout for name in ("build", "extras", "guide"))
    assert "deedum guide" in result.stdout


@pytest.mark.parametrize("command", ["build", "extras", "guide"])
def test_short_help_on_every_command(command):
    result = run(command, "-h")
    assert result.exit_code == 0
    assert "Usage" in result.stdout


def test_no_args_prints_help():
    assert "Usage" in run().stdout


def test_build_prints_exactly_three_lines(site):
    result = run("build")
    lines = result.stdout.splitlines()
    assert (result.exit_code, result.stderr, len(lines)) == (0, "", 3)
    assert lines[:2] == ["pages 2", "static 1"]
    assert re.fullmatch(r"extras \d+: .*", lines[2])
    assert (site / "_site" / "blog" / "one" / "index.html").is_file()


def test_build_summary_lists_the_always_written_extras(site):
    extras = run("build").stdout.splitlines()[2]
    names = ("404.html", "sitemap.xml", "robots.txt", ".nojekyll")
    assert [n for n in names if n not in extras] == []


def test_build_out_is_relative_to_the_current_folder(site, tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = run("build", "--config", str(site / "deedum.toml"), "--out", "dist")
    assert result.exit_code == 0
    assert (elsewhere / "dist" / "index.html").is_file()
    assert not (site / "_site").exists()


def test_build_config_makes_its_folder_the_site_root(site, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert run("build", "--config", "site/deedum.toml").exit_code == 0
    assert (site / "_site" / "index.html").is_file()


def test_base_flags_end_up_in_the_sitemap(site):
    result = run("build", "--base-url", "https://x.test", "--base-path", "pre")
    assert result.exit_code == 0
    sitemap = (site / "_site" / "sitemap.xml").read_text()
    assert "https://x.test/pre/blog/one/" in sitemap


def test_env_beats_file(site, monkeypatch):
    sitemap = site / "_site" / "sitemap.xml"
    monkeypatch.setenv("DEEDUM_BASE_URL", "https://env.test")
    assert run("build").exit_code == 0
    assert "https://env.test/demo/" in sitemap.read_text()


def test_flag_beats_env(site, monkeypatch):
    monkeypatch.setenv("DEEDUM_BASE_URL", "https://env.test")
    assert run("build", "--base-url", "https://flag.test").exit_code == 0
    text = (site / "_site" / "sitemap.xml").read_text()
    assert ("https://flag.test/demo/" in text, "env.test" in text) == (True, False)


@pytest.mark.parametrize("flag", ["--base-url", "--base-path"])
def test_empty_base_flags_are_rejected(site, flag):
    result = run("build", flag, "")
    assert result.exit_code == 2
    assert result.stderr == f"error: {flag} must not be empty\n"
    assert not (site / "_site").exists()


def test_extras_rejects_empty_flags_too(site):
    result = run("extras", ".", "--base-url", "")
    assert (result.exit_code, result.stderr) == (
        2,
        "error: --base-url must not be empty\n",
    )


def test_force_clear_bypasses_the_tracked_files_guard(site):
    out = site / "_site"
    put(out / "kept.txt", "tracked")
    track(site)
    refused = run("build")
    assert (refused.exit_code, out.joinpath("kept.txt").exists()) == (2, True)
    assert "tracked file" in refused.stderr
    assert run("build", "--force-clear").exit_code == 0
    assert not (out / "kept.txt").exists()


def test_tracked_refusal_comes_with_a_hint(site):
    put(site / "_site" / "kept.txt", "tracked")
    track(site)
    assert "hint: set allow_tracked_out" in run("build").stderr


def test_missing_config_is_exit_2_with_a_hint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("build")
    first, second = result.stderr.splitlines()
    assert result.exit_code == 2
    assert first.startswith("error: no deedum config in ")
    assert second.startswith("hint: create ")
    assert "Traceback" not in result.stderr


def test_render_failure_is_exit_1_with_the_page_named(site):
    put(site / "templates" / "page.html", "{{ nope.attr }}")
    result = run("build")
    assert result.exit_code == 1
    assert result.stderr.startswith("error: cannot render 'page.html' for page ''")
    assert result.stdout == ""
    assert not (site / "_site" / "sitemap.xml").exists()


def test_hook_failure_is_exit_1_naming_the_hook(site):
    put(site / "deedum.toml", TOML + 'app = "site:Site"\n')
    put(
        site / "site.py",
        "import deedum\nclass Site(deedum.App):\n"
        "    def after_build(self, out):\n        raise ValueError('boom')\n",
    )
    result = run("build")
    assert result.exit_code == 1
    assert "app hook 'after_build' (site:Site) failed: ValueError: boom" in (
        result.stderr
    )


def test_bad_app_is_exit_2(site):
    put(site / "deedum.toml", TOML + 'app = "nosuch:Site"\n')
    result = run("build")
    assert result.exit_code == 2
    assert result.stderr.startswith("error: app 'nosuch:Site'")
    assert "hint: " in result.stderr


def test_interrupt_is_exit_130(site, monkeypatch):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "build_site", interrupted)
    result = run("build")
    assert (result.exit_code, result.stdout) == (130, "")


def test_os_errors_are_exit_1_without_a_traceback(site, monkeypatch):
    def broken(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(cli, "build_site", broken)
    result = run("build")
    assert result.exit_code == 1
    assert "error: [Errno 13] Permission denied" in result.stderr


def test_agent_mode_prints_a_corrected_example(site, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDECODE", "1")
    with pytest.raises(SystemExit) as stop:
        cli.main(["build", "--bogus"])
    err = capsys.readouterr().err
    assert stop.value.code == 2
    assert "Usage error in `" in err
    assert "No such option: --bogus" in err
    assert "╭" not in err


@pytest.fixture
def foreign(tmp_path: Path) -> Path:
    root = put(tmp_path / "foreign" / "index.html", "<p>hi</p>").parent
    put(root / "a" / "index.html", "<p>a</p>")
    put(root / "hidden.html", '<meta name="robots" content="NOINDEX, follow">')
    put(root / "404.html", "<p>gone</p>")
    return root


def test_extras_prints_pages_written_and_skipped(site, foreign):
    put(site / "icon.svg", SVG)
    put(site / "deedum.toml", TOML + 'favicon = "icon.svg"\n')
    result = run("extras", str(foreign))
    lines = result.stdout.splitlines()
    assert (result.exit_code, lines[0], lines[2], lines[3]) == (
        0,
        "pages 2",
        "skipped 0",
        "",
    )
    assert lines[1].startswith("written 9: sitemap.xml, robots.txt, .nojekyll, ")
    assert lines[4] == '<link rel="icon" href="/demo/favicon.ico" sizes="32x32">'


def test_extras_without_favicon_prints_no_links(site, foreign):
    result = run("extras", str(foreign))
    assert result.stdout.splitlines() == [
        "pages 2",
        "written 3: sitemap.xml, robots.txt, .nojekyll",
        "skipped 0",
    ]


def test_extras_skips_then_overwrites(site, foreign):
    put(foreign / "sitemap.xml", "MINE")
    plain = run("extras", str(foreign))
    assert "skipped 1: sitemap.xml" in plain.stdout.splitlines()
    assert (foreign / "sitemap.xml").read_text() == "MINE"
    again = run("extras", str(foreign))
    assert (again.exit_code, "written 0" in again.stdout.splitlines()) == (0, True)


def test_extras_overwrite_flag_replaces_files(site, foreign):
    put(foreign / "sitemap.xml", "MINE")
    forced = run("extras", str(foreign), "--overwrite")
    assert "skipped 0" in forced.stdout.splitlines()
    assert (foreign / "sitemap.xml").read_text().startswith("<?xml")


def test_extras_flags_change_the_urls(site, foreign):
    run("extras", str(foreign), "--base-url", "https://x.test", "--base-path", "qq")
    assert "https://x.test/qq/a/" in (foreign / "sitemap.xml").read_text()


def test_extras_refusals_are_exit_2(site, tmp_path):
    missing = tmp_path / "missing"
    result = run("extras", str(missing))
    assert result.exit_code == 2
    assert str(missing) in result.stderr
    assert result.stderr.startswith("error: ")


def test_extras_with_config_elsewhere(site, foreign, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("extras", str(foreign), "--config", str(site / "deedum.toml"))
    assert result.exit_code == 0
    assert "https://example.test/demo/a/" in (foreign / "sitemap.xml").read_text()


def test_guide_in_an_empty_folder_says_setup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("guide")
    assert result.exit_code == 0
    assert result.stdout.splitlines()[0].endswith("-> setup")
    assert list(tmp_path.iterdir()) == []


def test_guide_in_a_configured_folder_says_use(site):
    first = run("guide").stdout.splitlines()[0]
    assert first == "# deedum guide: configured via deedum.toml -> use"


def test_guide_detects_the_pyproject_table(tmp_path):
    put(tmp_path / "pyproject.toml", "[tool.deedum]\ntitle = 'x'\n")
    assert detect(tmp_path) == (
        Topic.USE,
        "configured via pyproject.toml [tool.deedum]",
    )


def test_guide_ignores_a_pyproject_without_the_table(tmp_path):
    put(tmp_path / "pyproject.toml", "[tool.other]\nx = 1\n")
    assert detect(tmp_path)[0] is Topic.SETUP


def test_guide_tune_lists_every_config_key():
    page = run("guide", "tune").stdout
    assert [key for key in _KNOWN if f"`{key}`" not in page] == []


@pytest.mark.parametrize("topic", list(Topic))
def test_every_topic_prints_and_ends_with_next(topic, tmp_path):
    result = run("guide", topic.value)
    last = result.stdout.rstrip().splitlines()[-1]
    assert result.exit_code == 0
    assert result.stdout.startswith(f"# deedum guide: topic requested -> {topic}")
    assert last.startswith("next: `")


def test_unknown_topic_is_a_usage_error():
    assert run("guide", "nope").exit_code == 2


def test_every_command_named_in_the_pages_exists(tmp_path):
    commands = set(typer.main.get_group(cli.app).commands)
    pages = "\n".join(render(topic, tmp_path) for topic in Topic)
    named = set(re.findall(r"\bdeedum ([a-z][\w-]*)", pages))
    assert named
    assert named <= commands
    assert {"build", "extras", "guide"} <= named


def test_extras_rerun_hints_at_overwrite(site, foreign):
    run("extras", str(foreign))
    result = run("extras", str(foreign))
    assert result.exit_code == 0
    assert "hint:" in result.stderr
    assert "--overwrite" in result.stderr


def test_check_after_build_is_clean_but_for_warnings(site):
    assert run("build").exit_code == 0
    result = run("check")
    assert result.exit_code == 0
    assert result.stdout.splitlines()[-1] == "checked 3 pages: 0 errors, 2 warnings"
    assert "warning index.html: missing og:image" in result.stdout


def test_check_strict_turns_warnings_into_exit_1(site):
    run("build")
    assert run("check", "--strict").exit_code == 1


def test_check_without_a_build_is_exit_2(site):
    result = run("check")
    assert result.exit_code == 2
    assert "cannot check" in result.stderr
    assert "hint:" in result.stderr


def test_check_dir_uses_the_config_base_path(site):
    put(site / "content" / "index.md", "# Home\n\n[x](/demo/blog/one/) [y](/other/)\n")
    run("build")
    result = run("check", "_site")
    assert result.exit_code == 1
    assert "/other/ is outside base path /demo/" in result.stdout
    assert "blog/one/ is" not in result.stdout


def test_check_dir_without_config_defaults_to_the_root(tmp_path, monkeypatch):
    put(tmp_path / "built" / "index.html", '<a href="/y/">y</a><a href="/">h</a>')
    monkeypatch.chdir(tmp_path)
    result = run("check", "built")
    assert result.stdout.count("is missing") == 1


def test_check_dir_without_config_takes_the_base_path_flag(tmp_path, monkeypatch):
    put(tmp_path / "built" / "index.html", '<a href="/y/">y</a>')
    monkeypatch.chdir(tmp_path)
    flagged = run("check", "built", "--base-path", BASE)
    assert f"is outside base path {BASE}" in flagged.stdout


def test_check_dir_rejects_an_empty_base_path(tmp_path, monkeypatch):
    (tmp_path / "built").mkdir()
    monkeypatch.chdir(tmp_path)
    assert run("check", "built", "--base-path", "").exit_code == 2


def test_check_with_an_invalid_config_is_exit_2(site):
    put(site / "deedum.toml", 'title = "x"\n')
    run_ = run("check", "_site")
    assert run_.exit_code == 2


def test_check_bad_dir_is_exit_2(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("check", "nope")
    assert (result.exit_code, "nope" in result.stderr) == (2, True)


def test_build_check_prints_check_lines_after_build_lines(site):
    put(site / "content" / "index.md", "# Home\n\n[x](../gone/)\n")
    result = run("build", "--check")
    lines = result.stdout.splitlines()
    assert result.exit_code == 1
    assert [lines[0], lines[1]] == ["pages 2", "static 1"]
    assert lines[2].startswith("extras ")
    assert "../gone/ climbs above the site root" in result.stdout


def test_build_check_warnings_do_not_fail(site):
    result = run("build", "--check")
    assert result.exit_code == 0
    assert "warning" in result.stdout


def test_build_check_follows_out(site, tmp_path):
    put(site / "content" / "index.md", "# Home\n\n[x](../gone/)\n")
    result = run("build", "--check", "--out", str(tmp_path / "elsewhere"))
    assert result.exit_code == 1
