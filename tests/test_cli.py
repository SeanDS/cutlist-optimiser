from click.testing import CliRunner

from cutlist_optimiser.cli import main

ROOM = """
height = 2400
closed = false
[sheets]
thickness = 12
[[walls]]
name = "a"
length = 1200
studs = [600]
"""


def run(tmp_path, *args, text=ROOM):
    path = tmp_path / "room.toml"
    path.write_text(text)
    return CliRunner().invoke(main, [a if a != "ROOM" else str(path) for a in args])


def test_sheets_runs(tmp_path):
    res = run(tmp_path, "sheets", "ROOM", "-n", "50")
    assert res.exit_code == 0, res.output
    assert "CUT LIST" in res.output and "Random seed 0" in res.output


def test_verbosity_before_or_after_subcommand(tmp_path):
    for args in (["-v", "sheets", "ROOM", "-n", "10"], ["sheets", "ROOM", "-n", "10", "-v"]):
        res = run(tmp_path, *args)
        assert "info: read 1 walls" in res.output, args
    assert "info:" not in run(tmp_path, "sheets", "ROOM", "-n", "10").output


def test_config_error_is_explained_without_traceback(tmp_path):
    res = run(tmp_path, "sheets", "ROOM", text=ROOM.replace("[600]", "[600, 500]"))
    assert res.exit_code == 1
    assert "error:" in res.output and "fix:" in res.output and "Traceback" not in res.output


def test_debug_shows_traceback(tmp_path):
    res = run(tmp_path, "--debug", "sheets", "ROOM", text=ROOM.replace("[600]", "[600, 500]"))
    assert res.exit_code == 1 and "Traceback" in res.output


def test_missing_file(tmp_path):
    res = CliRunner().invoke(main, ["sheets", str(tmp_path / "nope.toml")])
    assert res.exit_code == 1 and "cannot read" in res.output
