from cutlist_optimiser.solver import Settings, Solver, Wall, stack_options


def solve(walls, **kw):
    return Solver(Settings(**kw), walls).solve(500)


def test_full_sheets_600_centres():
    res = solve([Wall("a", [600] * 6)], kerf=0, joint_gap=0)
    assert len(res.sheets) == res.lower_bound == 9


def test_narrow_bays_share_sheets():
    # two 400 mm wide walls: their pieces fit side by side on 800 wide sheets
    res = solve([Wall("a", [400]), Wall("b", [400])], kerf=0, joint_gap=0)
    assert len(res.sheets) == 2


def test_noggin_joint_preferred():
    opts = stack_options(2398, 1200, [1198], 100, "prefer")
    assert opts[0].heights == (1198, 1200) and opts[0].off_noggin == 0


def test_require_without_noggins_fails():
    try:
        solve([Wall("a", [1200])], noggin_joints="require")
    except ValueError:
        return
    raise AssertionError("expected ValueError")
