import pytest

from cutlist_optimiser.config import ConfigError, loads
from cutlist_optimiser.tiles import Tiler, mod_dist

BASE = """
height = 2400
closed = {closed}
[sheets]
thickness = 12
[tiles]
size = [600, 300]
thickness = 10
grout = 2
kerf = 0
{tiles}
"""


def room(walls, closed=False, tiles=""):
    if "min_cut" not in tiles:
        tiles += "\nmin_cut = 50"
    return loads(BASE.format(closed=str(closed).lower(), tiles=tiles) + walls)


def edge_pieces(tiler, res, wi, row=0):
    """Widths of the first and last piece in a row of wall wi."""
    pieces = sorted((p for p in res.walls[wi].pieces if p.row == row), key=lambda p: p.x0)
    return pieces[0].w, pieces[-1].w


def test_start_wall_is_centred_on_tile_or_joint():
    r = room('[[walls]]\nname = "a"\nlength = 3000')
    res = Tiler(r).solve()
    start = res.goals[0]
    assert start.deviation < 0.05
    # symmetrical: the first and last pieces in each row match
    first, last = edge_pieces(Tiler(r), res, 0)
    assert abs(first - last) < 0.1


def test_window_centred_with_mitred_reveal():
    r = room('[[walls]]\nname = "a"\nlength = 3000\n'
             'stay_out = [{ name = "w", x = [1000, 1900], y = [900, 2100], reveal = { depth = 100 } }]',
             tiles='start = "a.w"\nrows = ["a.w.sill"]')
    tiler = Tiler(r)
    hole = tiler.faces[0].holes[0]
    assert (hole.x0, hole.x1, hole.y0, hole.y1) == (1022, 1878, 922, 2078)  # framing minus 12 + 10 each side
    assert hole.reveal == 110  # depth + tile thickness, to the arris
    res = tiler.solve()
    assert res.goals[0].deviation < 0.05
    # reveal pieces: two jambs and a sill and head, all mitred along the arris
    assert res.reveals and all(p.mitres == 1 for p in res.reveals)
    assert {p.where.split()[-1] for p in res.reveals} >= {"reveal", "sill", "head"}
    # face pieces cut along the opening's edges are mitred too
    assert any(p.mitres for w in res.walls for p in w.pieces)


def test_pattern_continues_round_inside_corner():
    # a then b, inside corner with a running through; the pattern carries on from a to b
    r = room('[[walls]]\nname = "a"\nlength = 2150\ncorner = { type = "inside", through = "this" }\n'
             '[[walls]]\nname = "b"\nlength = 2000', tiles='pattern = "grid"')
    tiler = Tiler(r)
    res = tiler.solve()
    _, last_a = edge_pieces(tiler, res, 0)
    first_b, _ = edge_pieces(tiler, res, 1)
    # one tile cut in two at the corner, less the grout joint in the corner
    assert abs(last_a + first_b - (600 - res.grout)) < 0.1


def test_fresh_corner_lets_priority_wall_centre():
    walls = ('[[walls]]\nname = "a"\nlength = 2000\ncorner = { type = "inside", through = "this"%s }\n'
             '[[walls]]\nname = "b"\nlength = 1700\ntiles = { priority = 1 }')
    continued = Tiler(room(walls % "")).solve()
    fresh = Tiler(room(walls % ', tiles = "fresh"')).solve()
    assert fresh.goals[2].deviation < 0.05
    assert continued.goals[2].deviation >= fresh.goals[2].deviation


def test_seam_between_least_important_walls():
    walls = ""
    for name, prio, nxt in (("a", None, "this"), ("b", 1, "this"), ("c", None, "this"), ("d", None, "this")):
        walls += f'[[walls]]\nname = "{name}"\nlength = 2000\ncorner = {{ type = "inside", through = "{nxt}" }}\n'
        if prio:
            walls += f"tiles = {{ priority = {prio} }}\n"
    tiler = Tiler(room(walls, closed=True, tiles='start = "a"'))
    corners, reason, chains, anchors = tiler.chains()
    seams = [i for i, kind in corners if kind == "seam"]
    assert seams == [2]  # c/d: both unprioritised and furthest from the start
    assert "c/d" in reason
    assert chains and anchors[0] == 0


def test_inside_corner_thickness_shortens_butting_wall():
    r = room('[[walls]]\nname = "a"\nlength = 2000\ncorner = { type = "inside", through = "next" }\n'
             '[[walls]]\nname = "b"\nlength = 2000')
    a, b = Tiler(r).faces
    assert a.b1 == 2000 - 12  # boarded face stops at b's boarded face
    assert a.c1 == 2000 - 12 - 10  # a's tiles butt against b's tiles
    assert b.c0 == 12  # b runs through: its tiles reach a's boarded face


def test_measured_length_replaces_calculated():
    r = room('[[walls]]\nname = "a"\nlength = 2000\nmeasured_length = 1990')
    f = Tiler(r).faces[0]
    assert f.measured and f.b1 - f.b0 == 1990


def test_boarded_measurements_converted_to_framing():
    r = room('[[walls]]\nname = "x"\nlength = 1000\ncorner = { type = "inside", through = "this" }\n'
             '[[walls]]\nname = "a"\nlength = 3000\nmeasured_from = "boarded"\n'
             'stay_out = [{ name = "w", x = [988, 1888], y = [900, 2100], reveal = "none" }]')
    hole = Tiler(r).faces[1].holes[0]
    assert (hole.x0, hole.x1) == (1000, 1900)  # 12 mm sheet at the start corner


def test_short_pieces_are_reported():
    # a 640 mm wall: whichever way it is centred, a 20 mm or 320 mm edge piece appears
    r = room('[[walls]]\nname = "a"\nlength = 640', tiles='min_cut = 100\ngrout_options = [2]')
    res = Tiler(r).solve()
    assert all(p[1] for p in res.problems)  # descriptions present
    assert res.goals[0].deviation < 0.05  # the start stays centred even so


def test_reveal_too_deep_for_tile():
    r = room('[[walls]]\nname = "a"\nlength = 3000\n'
             'stay_out = [{ name = "w", x = [1000, 1900], y = [900, 2100], reveal = { depth = 400 } }]')
    with pytest.raises(ConfigError, match="do not fit"):
        Tiler(r)


def test_counts_and_efficiency_add_up():
    r = room('[[walls]]\nname = "a"\nlength = 2400')
    res = Tiler(r).solve()
    area = res.full * 600 * 300 + sum(p.area for p in res.cut_pieces)
    g = res.grout
    # tiles cover the wall less the grout joints: about (600 x 300) / (602 x 302) of it
    assert 2400 * 2400 * (600 * 300) / ((600 + g) * (300 + g)) * 0.99 < area < 2400 * 2400
    assert res.count * 600 * 300 >= area


def test_mod_dist():
    assert mod_dist(10, 100) == 10 and mod_dist(95, 100) == 5 and mod_dist(-5, 100) == 5


def test_outside_corner_mitred_both_walls_reach_arris():
    r = room('[[walls]]\nname = "a"\nlength = 2150\ncorner = { type = "outside", through = "this" }\n'
             '[[walls]]\nname = "b"\nlength = 2000', tiles='pattern = "grid"')
    tiler = Tiler(r)
    a, b = tiler.faces
    assert a.c1 == 2150 + 12 + 10 and b.c0 == -12 - 10  # to the arris of sheet + tile
    assert a.mitre1 and b.mitre0
    res = tiler.solve()
    _, last_a = edge_pieces(tiler, res, 0)
    first_b, _ = edge_pieces(tiler, res, 1)
    assert abs(last_a + first_b - 600) < 0.1  # one tile, mitred round the corner: no corner joint
    corner_pieces = [p for p in res.walls[0].pieces if p.x1 > a.c1 - 0.1]
    assert corner_pieces and all(p.mitres for p in corner_pieces)


def test_brick_rows_alternate():
    r = room('[[walls]]\nname = "a"\nlength = 3000', tiles='pattern = "brick"\noffset = 0.5')
    tiler = Tiler(r)
    res = tiler.solve()
    first = [edge_pieces(tiler, res, 0, row)[0] for row in (1, 2, 3)]
    assert abs(first[0] - first[2]) < 0.1 and abs(first[0] - first[1]) > 1


@pytest.mark.parametrize("align", ["tile", "joint"])
def test_start_align(align):
    r = room('[[walls]]\nname = "a"\nlength = 3000', tiles=f'start_align = "{align}"')
    res = Tiler(r).solve()
    assert res.goals[0].deviation < 0.05 and f"{align} centred" in res.goals[0].describe
