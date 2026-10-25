from cutlist_optimiser.solver import Settings, Solver, Wall, stack_options


def solve(walls, **kw):
    return Solver(Settings(**kw), walls).solve(500)


def test_full_sheets_600_centres():
    res = solve([Wall("a", [600] * 6)], kerf=0, joint_gap=0)
    assert len(res.sheets) == res.lower_bound == 9
    assert abs(res.used_area - 3600 * 2398) < 1e-6
    assert abs(res.utilisation - 3600 * 2398 / (9 * 1200 * 800)) < 1e-9


def test_narrow_bays_share_sheets():
    # two 400 mm wide walls: their pieces fit side by side on 800 wide sheets
    res = solve([Wall("a", [400]), Wall("b", [400])], kerf=0, joint_gap=0)
    assert len(res.sheets) == 2


def test_noggin_joint_preferred():
    opts = stack_options(2398, 1200, [[1198]], 100, "prefer")
    assert opts[0].heights == (1198, 1200) and opts[0].off_noggin == 0


def test_joint_between_staggered_noggins_catches_both():
    opts = stack_options(2398, 1200, [[1190], [1206]], 100, "require", tol=10)
    assert opts and opts[0].heights[0] == 1198


def test_noggins_must_be_given_per_bay():
    try:
        Solver(Settings(), [Wall("a", [600, 600], noggins=[[1200]])])
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_require_without_noggins_fails():
    try:
        solve([Wall("a", [1200])], noggin_joints="require")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_stay_out_area_is_not_sheeted():
    # 1200 wall, window over the right 600 mm bay from 900 to 2100 mm
    wall = Wall("a", [600, 600], stay_out=[(600, 1200, 900, 2100)])
    res = solve([wall], kerf=0, joint_gap=0, bottom_gap=0)
    pieces = [p for col in res.walls[0] for p in col]
    area = sum((p.x1 - p.x0) * (p.y1 - p.y0) for p in pieces)
    assert area == 1200 * 2400 - 600 * 1200
    for p in pieces:
        assert p.x1 <= 600 or p.y1 <= 900 or p.y0 >= 2100


def test_stay_out_edge_must_be_on_stud():
    try:
        Solver(Settings(), [Wall("a", [600, 600], stay_out=[(500, 1200, 900, 2100)])])
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_door_to_ceiling_leaves_empty_column():
    wall = Wall("a", [600, 600], stay_out=[(600, 1200, 0, 2400)])
    res = solve([wall])
    assert all(p.x1 <= 600 for col in res.walls[0] for p in col)
