import pytest

from cutlist_optimiser.config import ConfigError
from cutlist_optimiser.sheets import Solver, stack_options
from helpers import room


def solve(r, stagger=0):
    r.sheets.stagger = stagger
    return Solver(r).solve(500)


def test_full_sheets_600_centres():
    r = room('[[walls]]\nname = "a"\nlength = 3600\nstuds = [600, 1200, 1800, 2400, 3000]', kerf=0, joint_gap=0)
    res = solve(r)
    assert len(res.sheets) == res.lower_bound == 9
    assert abs(res.used_area - 3600 * 2398) < 1e-6
    assert res.cuts == 3  # only the three 798 mm pieces need a cut; the rest are whole sheets
    assert abs(res.utilisation - 3600 * 2398 / (9 * 1200 * 800)) < 1e-9


def test_narrow_bays_share_sheets():
    # two separate 400 mm wide walls: their pieces fit side by side on 800 wide sheets
    r = room('[[walls]]\nname = "a"\nlength = 400\ncorner = { type = "open" }\n'
             '[[walls]]\nname = "b"\nlength = 400', kerf=0, joint_gap=0)
    assert len(solve(r).sheets) == 2


def test_noggin_joint_preferred():
    opts = stack_options(2398, 1200, [[1198]], 100, "prefer")
    assert opts[0].heights == (1198, 1200) and opts[0].off_noggin == 0


def test_joint_between_staggered_noggins_catches_both():
    opts = stack_options(2398, 1200, [[1190], [1206]], 100, "require", tol=10)
    assert opts and opts[0].heights[0] == 1198


def test_require_without_noggins_fails():
    r = room('[[walls]]\nname = "a"\nlength = 1200', noggin_joints="require")
    with pytest.raises(ConfigError, match="noggin"):
        solve(r)


def test_stay_out_area_is_not_sheeted():
    # 1200 wall, window over the right 600 mm bay from 900 to 2100 mm
    r = room('[[walls]]\nname = "a"\nlength = 1200\nstuds = [600]\n'
             'stay_out = [{ x = [600, 1200], y = [900, 2100] }]', kerf=0, joint_gap=0, bottom_gap=0)
    pieces = [p for col in solve(r).walls[0] for p in col]
    area = sum((p.x1 - p.x0) * (p.y1 - p.y0) for p in pieces)
    assert area == 1200 * 2400 - 600 * 1200
    for p in pieces:
        assert p.x1 <= 600 or p.y1 <= 900 or p.y0 >= 2100


def test_stay_out_only_for_tiles_is_sheeted():
    r = room('[[walls]]\nname = "a"\nlength = 1200\nstuds = [600]\n'
             'stay_out = [{ x = [100, 1200], y = [0, 500], only = "tiles" }]')
    assert solve(r).walls[0]  # no error even though the edge is off a stud


def test_stay_out_edge_must_be_on_stud():
    r = room('[[walls]]\nname = "a"\nlength = 1200\nstuds = [600]\nstay_out = [{ x = [500, 1200], y = [900, 2100] }]')
    with pytest.raises(ConfigError, match="not on a stud"):
        Solver(r)


def test_door_to_ceiling_leaves_empty_column():
    r = room('[[walls]]\nname = "a"\nlength = 1200\nstuds = [600]\nstay_out = [{ x = [600, 1200], y = [0, 2400] }]')
    assert all(p.x1 <= 600 for col in solve(r).walls[0] for p in col)


def test_corners_shrink_and_extend_walls():
    # a inside-corner with b, b runs through; b outside-corner with c, b runs through
    r = room('[[walls]]\nname = "a"\nlength = 1200\nstuds = [600]\ncorner = { type = "inside", through = "next" }\n'
             '[[walls]]\nname = "b"\nlength = 1200\nstuds = [600]\ncorner = { type = "outside", through = "this" }\n'
             '[[walls]]\nname = "c"\nlength = 600', joint_gap=0)
    res = solve(r)
    a, b = res.walls[0], res.walls[1]
    assert a[-1][0].x1 == 1200 - 12  # a butts against b's sheets
    assert b[0][0].x0 == 0 and b[-1][0].x1 == 1212  # b runs through both corners


def test_bay_wider_than_sheet():
    r = room('[[walls]]\nname = "a"\nlength = 1300')
    with pytest.raises(ConfigError, match="wider than"):
        Solver(r)


def test_stagger_offsets_neighbouring_joints():
    r = room('[[walls]]\nname = "a"\nlength = 2400\nstuds = [800, 1600]\nnoggins = [[1200], [1200], [1200]]')
    res = solve(r, stagger=200)
    assert res.aligned == 0
    cols = [[p.y1 for p in col if p.joint_support] for col in res.walls[0]]
    for left, right in zip(cols, cols[1:]):
        assert all(abs(a - b) >= 200 for a in left for b in right)
