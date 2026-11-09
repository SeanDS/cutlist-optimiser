import pytest

from cutlist_optimiser.config import ConfigError, loads
from helpers import room

TILES = '[tiles]\nsize = [600, 300]\nthickness = 10\ngrout = 2\n'


def test_studs_must_be_increasing_positions():
    with pytest.raises(ConfigError, match="increasing positions") as e:
        room('[[walls]]\nname = "a"\nlength = 3600\nstuds = [600, 600, 600]')
    assert e.value.fix


def test_noggins_must_be_given_per_bay():
    with pytest.raises(ConfigError, match="2 lists"):
        room('[[walls]]\nname = "a"\nlength = 1200\nstuds = [600]\nnoggins = [[1200]]')


def test_closed_room_needs_corners():
    with pytest.raises(ConfigError, match="no corner given"):
        room('[[walls]]\nname = "a"\nlength = 1200\n[[walls]]\nname = "b"\nlength = 1200', closed=True)


def test_corner_needs_through():
    with pytest.raises(ConfigError, match="runs through"):
        room('[[walls]]\nname = "a"\nlength = 1200\ncorner = { type = "inside" }\n[[walls]]\nname = "b"\nlength = 600')


def test_unknown_setting_is_named():
    with pytest.raises(ConfigError, match="kerf"):
        loads('height = 2400\nkerf = 3\n[[walls]]\nlength = 1000')


def test_bad_toml_is_explained():
    with pytest.raises(ConfigError, match="not valid TOML"):
        loads('height = \n')


def test_duplicate_priorities():
    with pytest.raises(ConfigError, match="more than once"):
        room('[[walls]]\nname = "a"\nlength = 1200\ntiles = { priority = 1 }\ncorner = { type = "open" }\n'
             '[[walls]]\nname = "b"\nlength = 1200\ntiles = { priority = 1 }')


def test_tiles_need_reveal_choice():
    r = room('[[walls]]\nname = "a"\nlength = 1200\nstay_out = [{ x = [100, 500], y = [900, 1500] }]', extra=TILES)
    with pytest.raises(ConfigError, match="reveal"):
        r.require_tiles()


def test_tile_references_must_exist():
    r = room('[[walls]]\nname = "a"\nlength = 1200\n'
             'stay_out = [{ name = "window", x = [100, 500], y = [900, 1500], reveal = "none" }]',
             extra=TILES + 'rows = ["a.door.sill"]\n')
    with pytest.raises(ConfigError, match="door"):
        r.require_tiles()


def test_measured_length_alone_is_enough_for_tiles():
    r = room('[[walls]]\nname = "a"\nmeasured_length = 1180', extra=TILES)
    r.require_tiles()
    with pytest.raises(ConfigError, match="framing length"):
        r.require_sheets()
