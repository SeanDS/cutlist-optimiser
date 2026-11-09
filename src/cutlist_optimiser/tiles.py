"""Tile layout: set out the tiles on each finished wall, cut round openings and count tiles and cuts.

Model:
  * Each wall's tiled face runs between its corners, allowing for the sheet and
    tile thicknesses (see geometry.py); measured boarded lengths can replace the
    calculated ones.  Inside corners get a grout joint in the corner.
  * Rows are level all round the room, so one number (where the rows start)
    sets them for every wall.  Row goals (sill, floor, ceiling, ...) pick it.
  * Columns: each wall's grid is set by where its columns start.  Walls joined
    by a "continue" corner share one grid, unfolded round the corner, so a cut
    tile carries on onto the next wall.  Each chain of such walls is set out from
    one anchor: the start feature's wall, else its highest-priority wall.  In a
    closed room where every corner continues, the pattern cannot meet itself
    again, so one corner becomes a seam: the one between the two least important
    walls.
  * Grout is one width for the whole room, chosen from the allowed options.
  * The search tries every grout width, a few row heights and anchor positions,
    and ranks layouts: fewest pieces below the minimum cut, then the start
    feature centred, then the goals in priority order, then fewest tiles.
  * Cut pieces (and reveal pieces) are packed onto tiles to reuse offcuts.
"""

import itertools
import math
from dataclasses import dataclass, field

from .config import EDGES, ConfigError
from .console import debug, em, info, warning
from .geometry import face_offset, framing_x, tile_offset
from .packing import EPS, best_pack

TOL = 0.05  # mm: positions this close count as the same


def mod_dist(a, period):
    """Distance from a to the nearest multiple of period."""
    r = a % period
    return min(r, period - r)


# --- the finished room ---------------------------------------------------------

@dataclass
class Hole:
    """A stay-out area on the finished (tiled) face."""
    name: str | None
    x0: float
    x1: float
    y0: float
    y1: float
    reveal: float | None  # width of the reveal tiles (depth + tile thickness), None = no tiled reveal


@dataclass
class Face:
    """The tiled face of one wall, in framing x coordinates."""
    index: int
    name: str
    b0: float  # boarded face ends
    b1: float
    measured: bool
    calculated_b1: float | None
    c0: float  # tile surface ends (corner lines for continuing the pattern)
    c1: float
    inside0: bool  # inside corner: a grout joint goes in the corner
    inside1: bool
    mitre0: bool  # outside corner with mitred tiles
    mitre1: bool
    holes: list
    target: float  # where this wall would like to be centred
    target_name: str


@dataclass
class Piece:
    wall: int
    row: int  # face rows count from 0 at the lowest; -1 for reveal pieces
    x0: float  # bounding box on the wall (reveal pieces: along the reveal)
    y0: float
    x1: float
    y1: float
    area: float
    notches: int
    mitres: int
    kind: str = "face"  # face | reveal
    where: str = ""

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def h(self):
        return self.y1 - self.y0


@dataclass
class WallLayout:
    full: list  # rectangles of whole tiles
    pieces: list  # cut pieces
    problems: list  # (piece, description, shortfall in mm) below the minimum size


@dataclass
class Goal:
    kind: str  # start | wall | row
    label: str
    describe: str
    deviation: float
    worst: float
    note: str = ""
    why: str = ""  # why it was not met exactly

    @property
    def closeness(self):
        return max(0.0, 1 - self.deviation / self.worst) if self.worst else 1.0


@dataclass
class Result:
    grout: float
    v: float
    u: list
    walls: list  # WallLayout per wall
    reveals: list  # reveal pieces
    tiles: list  # packed tiles (Sheets) holding the cut pieces
    full: int
    goals: list
    corners: list  # (wall index, "continue" | "fresh" | "seam" | "open")
    seam_reason: str
    chains: list
    anchors: list

    @property
    def problems(self):
        return [p for w in self.walls for p in w.problems] + self.reveal_problems

    reveal_problems: list = field(default_factory=list)

    @property
    def count(self):
        return self.full + len(self.tiles)

    @property
    def cut_pieces(self):
        return [p for w in self.walls for p in w.pieces] + self.reveals


class Tiler:
    def __init__(self, room):
        room.require_tiles()
        self.room, self.t = room, room.tiles
        self.tw, self.th = self.t.size
        self.y0, self.y1 = self.t.bottom_gap, room.height - self.t.top_gap
        self.faces = [self._face(i) for i in range(len(room.walls))]
        self._check()
        for f in self.faces:
            debug(f"{f.name}: boarded face x {f.b0:g} to {f.b1:g}, tiles x {f.c0:g} to {f.c1:g}, "
                  f"{len(f.holes)} opening(s), centre target {f.target:g} ({f.target_name})")

    # --- geometry --------------------------------------------------------

    def _face(self, i):
        room, t = self.room, self.t
        wall, ts = room.walls[i], room.sheets.thickness
        (c0, through0), (c1, through1) = room.start_corner(i), room.end_corner(i)
        b0 = -face_offset(c0, ts)
        calculated = None if wall.length is None else wall.length + face_offset(c1, ts)
        if wall.measured_length is not None:
            b1 = b0 + wall.measured_length
            if calculated is not None and abs(b1 - calculated) > 10:
                warning(f"{em(wall.name)}: measured boarded length {em(f'{wall.measured_length:g}')} mm differs "
                        f"from the {em(f'{calculated - b0:g}')} mm calculated from the framing; using the "
                        f"measured value")
        else:
            b1 = calculated
        e0 = b0 - tile_offset(c0, through0, t.thickness, t.outside_corners)
        e1 = b1 + tile_offset(c1, through1, t.thickness, t.outside_corners)
        holes = []
        for o in wall.stay_out:
            if not o.applies("tiles"):
                continue
            x0, x1 = framing_x(room, i, o.x[0]), framing_x(room, i, o.x[1])
            y0, y1 = o.y
            if o.reveal is not None:  # reveals boarded and tiled: the opening shrinks by both layers
                d = ts + t.thickness
                x0, x1 = x0 + d, x1 - d
                y0 = y0 + d if y0 > EPS else y0
                y1 = y1 - d if y1 < room.height - EPS else y1
                if x1 - x0 <= 0 or y1 - y0 <= 0:
                    raise ConfigError(o.where, "the opening is smaller than its boarded and tiled reveals",
                                      "check the opening size, or use reveal = \"none\"")
            x0, x1 = max(x0, e0), min(x1, e1)
            if x1 - x0 > EPS:
                holes.append(Hole(o.name, x0, x1, y0, y1,
                                  None if o.reveal is None else o.reveal + t.thickness))
        target, name = (e0 + e1) / 2, "wall centre"
        c = wall.tiles.centre_on
        if isinstance(c, str):
            h = next(h for h in holes if h.name == c)
            target, name = (h.x0 + h.x1) / 2, f"{c} centre"
        elif c is not None:
            target, name = framing_x(room, i, c), f"x = {c:g}"
        mitre = t.outside_corners == "mitre"
        return Face(i, wall.name, b0, b1, wall.measured_length is not None, calculated, e0, e1,
                    c0.type == "inside", c1.type == "inside",
                    mitre and c0.type == "outside", mitre and c1.type == "outside", holes, target, name)

    def _check(self):
        t = self.t
        for f, wall in zip(self.faces, self.room.walls):
            if f.c1 - f.c0 <= 0:
                raise ConfigError(wall.where, "the wall has no length left to tile once the corners are allowed for",
                                  "check length / measured_length and the corners")
            for h in f.holes:
                if h.reveal is None:
                    continue
                fits_jamb = h.reveal <= self.tw + EPS or (t.rotate and h.reveal <= self.th + EPS)
                fits_sill = h.reveal <= self.th + EPS or (t.rotate and h.reveal <= self.tw + EPS)
                if not (fits_jamb and fits_sill):
                    raise ConfigError(f"{wall.where}.stay_out", f"the reveal tiles of {h.name or 'an opening'} "
                                                                f"({h.reveal:g} mm deep) do not fit on a tile",
                                      "set rotate = true in [tiles] if the tiles can be turned, or use bigger tiles")
                if h.reveal < max(t.min_cut, t.min_mitre):
                    warning(f"{em(wall.name)}: the reveal tiles of {h.name or 'an opening'} are only "
                            f"{em(f'{h.reveal:g}')} mm wide, below the minimum mitred piece of "
                            f"{t.min_mitre:g} mm; nothing can change that except the reveal depth")
        if t.pattern == "brick" and max(self.tw, self.th) > 600 and t.offset > 0.34 and t.offset < 0.66:
            warning(f"tiles longer than 600 mm are rarely perfectly flat, so a {em('1/2')} offset can leave "
                    f"uneven edges (lippage); consider offset = {em('0.333')}")

    # --- layout of one wall --------------------------------------------------

    def pitch(self, g):
        return self.tw + g, self.th + g

    def shift(self, k, px):
        return (k % 2) * self.t.offset * px if self.t.pattern == "brick" else 0.0

    def rows(self, g, v):
        """(k, y0, y1) of every row overlapping the tiled height."""
        _, py = self.pitch(g)
        k = math.floor((self.y0 - v) / py) - 1
        out = []
        while v + k * py < self.y1 - EPS:
            ry0, ry1 = v + k * py, v + k * py + self.th
            if ry1 > self.y0 + EPS:
                out.append((k, max(ry0, self.y0), min(ry1, self.y1), ry0, ry1))
            k += 1
        return out

    def extent(self, f, g):
        return f.c0 + (g / 2 if f.inside0 else 0), f.c1 - (g / 2 if f.inside1 else 0)

    def wall_layout(self, wi, g, v, u, detail=False):
        f, t = self.faces[wi], self.t
        px, _ = self.pitch(g)
        x0, x1 = self.extent(f, g)
        full, pieces, problems = [], [], []
        mitred_x = [x for x, m in ((x0, f.mitre0), (x1, f.mitre1)) if m]
        rows = self.rows(g, v)
        for k, ry0, ry1, oy0, oy1 in rows:
            start = u + self.shift(k, px)
            j = math.floor((x0 - start) / px) - 1
            while start + j * px < x1 - EPS:
                tx0, tx1 = start + j * px, start + j * px + self.tw
                j += 1
                cx0, cx1 = max(tx0, x0), min(tx1, x1)
                if cx1 - cx0 <= EPS:
                    continue
                rects = [(cx0, ry0, cx1, ry1)]
                hit = []
                for h in f.holes:
                    if h.x0 < cx1 - EPS and h.x1 > cx0 + EPS and h.y0 < ry1 - EPS and h.y1 > ry0 + EPS:
                        hit.append(h)
                        rects = [r for rect in rects for r in _subtract(rect, (h.x0, h.y0, h.x1, h.y1))]
                if not rects:
                    continue
                tile = (tx0, oy0, tx1, oy1)
                if not hit and (cx0, ry0, cx1, ry1) == tile:
                    if detail:
                        full.append(tile)
                    else:
                        full.append(None)
                    continue
                for comp in _components(rects):
                    piece, bad = self._piece(wi, k - rows[0][0], comp, tile, hit, mitred_x)
                    pieces.append(piece)
                    problems.extend((piece, *b) for b in bad)
        return WallLayout(full, pieces, problems)

    def _piece(self, wi, k, rects, tile, holes, mitred_x):
        t = self.t
        bx0, by0 = min(r[0] for r in rects), min(r[1] for r in rects)
        bx1, by1 = max(r[2] for r in rects), max(r[3] for r in rects)
        notches = sum(1 for h in holes if h.x0 > bx0 + TOL or h.x1 < bx1 - TOL) if len(rects) > 1 else 0
        # edges that meet a mitred corner: outside room corners and tiled window reveals
        mitred = [("x", x) for x in mitred_x]
        for h in holes:
            if h.reveal is not None:
                mitred += [("x", h.x0), ("x", h.x1), ("y", h.y0), ("y", h.y1)]
        bad, mitres = [], 0

        def is_mitred(axis, pos):
            return any(a == axis and abs(pos - p) < TOL for a, p in mitred)

        for r in rects:
            for axis, lo, hi, tlo, thi, other in (("x", r[0], r[2], tile[0], tile[2], (r[1], r[3])),
                                                    ("y", r[1], r[3], tile[1], tile[3], (r[0], r[2]))):
                size = hi - lo
                full_size = thi - tlo
                cut_lo, cut_hi = lo > tlo + TOL, hi < thi - TOL
                m_lo = cut_lo and is_mitred(axis, lo)
                m_hi = cut_hi and is_mitred(axis, hi)
                mitres += m_lo + m_hi
                if size >= full_size - TOL:
                    continue
                if _joined(r, rects, axis, lo) or _joined(r, rects, axis, hi):
                    continue
                need = max(t.min_cut, t.min_mitre) if (m_lo or m_hi) else t.min_cut
                if size < need - TOL:
                    what = "wide" if axis == "x" else "tall"
                    bad.append((f"{size:.0f} mm {what} (minimum {need:g})", need - size))
        area = sum((r[2] - r[0]) * (r[3] - r[1]) for r in rects)
        return Piece(wi, k, bx0, by0, bx1, by1, area, notches, mitres), bad

    def reveal_pieces(self, g, v, u):
        """Mitred reveal tiles for each opening with a tiled reveal, jointed in line with the face tiles."""
        pieces, problems = [], []
        px, py = self.pitch(g)
        rows = self.rows(g, v)
        for f in self.faces:
            for h in f.holes:
                if h.reveal is None:
                    continue
                name = f"{f.name} {h.name or 'opening'}"
                # jambs: one piece per face row, both sides
                for side in ("left", "right"):
                    for k, ry0, ry1, _, _ in rows:
                        a, b = max(ry0, h.y0), min(ry1, h.y1)
                        if b - a > EPS:
                            p = Piece(f.index, -1, 0, a, h.reveal, b, h.reveal * (b - a), 0, 1, "reveal",
                                      f"{name} {side} reveal")
                            pieces.append(p)
                            if b - a < self.t.min_cut - TOL and b - a < self.th - TOL:
                                problems.append((p, f"{b - a:.0f} mm long (minimum {self.t.min_cut:g})",
                                                 self.t.min_cut - (b - a)))
                # sill and head: one piece per column of the neighbouring face row
                for edge, y in (("sill", h.y0), ("head", h.y1)):
                    if (edge == "sill" and y <= self.y0 + EPS) or (edge == "head" and y >= self.y1 - EPS):
                        continue
                    k = math.floor(((y - TOL if edge == "sill" else y + TOL) - v) / py)
                    start = u[f.index] + self.shift(k, px)
                    j = math.floor((h.x0 - start) / px) - 1
                    while start + j * px < h.x1 - EPS:
                        a, b = max(start + j * px, h.x0), min(start + j * px + self.tw, h.x1)
                        j += 1
                        if b - a > EPS:
                            p = Piece(f.index, -1, a, 0, b, h.reveal, h.reveal * (b - a), 0, 1, "reveal",
                                      f"{name} {edge}")
                            pieces.append(p)
                            if b - a < self.t.min_cut - TOL and b - a < self.tw - TOL:
                                problems.append((p, f"{b - a:.0f} mm long (minimum {self.t.min_cut:g})",
                                                 self.t.min_cut - (b - a)))
        return pieces, problems

    # --- goals -------------------------------------------------------------

    def centre_dev(self, target, u, g):
        """How far the target is from the nearest tile centre or joint centre (in the even rows)."""
        px, _ = self.pitch(g)
        return min(mod_dist(target - (u + self.tw / 2), px), mod_dist(target - (u + self.tw + g / 2), px))

    def row_goals(self):
        """(label, edge kind, y): 'bottom' wants a row to start at y, 'top' wants one to end there."""
        goals = []
        for ref in self.t.rows:
            if ref == "floor":
                goals.append(("floor: whole tile at the bottom", "bottom", self.y0))
            elif ref == "ceiling":
                goals.append(("ceiling: whole tile at the top", "top", self.y1))
            else:
                opening, edge = ref.rsplit(".", 1)
                wall, o = self.room.opening(opening, "tiles.rows")
                h = next(h for h in self.faces[wall.index].holes if h.name == o.name)
                if EDGES[edge] == "bottom":
                    goals.append((f"{ref}: row edge at the {edge}", "top", h.y0))
                else:
                    goals.append((f"{ref}: row edge at the {edge}", "bottom", h.y1))
        return goals

    def row_dev(self, kind, y, g, v):
        _, py = self.pitch(g)
        return mod_dist(y - v - (self.th if kind == "top" else 0), py)

    # --- chains, anchors and the seam ---------------------------------------

    def start(self):
        """(wall index, target x, description) of the start feature."""
        ref = self.t.start
        if ref is None:
            f = self.faces[0]
            return 0, f.target, f"{f.name} ({f.target_name})"
        if "." in ref:
            wall, o = self.room.opening(ref, "tiles.start")
            h = next(h for h in self.faces[wall.index].holes if h.name == o.name)
            return wall.index, (h.x0 + h.x1) / 2, ref
        f = self.faces[self.room.wall(ref, "tiles.start").index]
        return f.index, f.target, f"{f.name} ({f.target_name})"

    def rank(self, i, start_wall):
        if i == start_wall:
            return 0
        p = self.room.walls[i].tiles.priority
        return p if p is not None else math.inf

    def chains(self):
        """Split the walls into chains joined by continuing corners; pick the seam if the room loops."""
        room, n = self.room, len(self.room.walls)
        start_wall = self.start()[0]
        corners = []
        for i in range(n if room.closed else n - 1):
            c = room.walls[i].corner
            corners.append([i, "open" if c.type == "open" else c.tiles])
        reason = ""
        if room.closed and all(c[1] == "continue" for c in corners):
            def key(c):
                a, b = self.rank(c[0], start_wall), self.rank((c[0] + 1) % n, start_wall)
                distance = min((c[0] - start_wall) % n, (start_wall - c[0] - 1) % n)
                return (min(a, b), max(a, b), distance)
            seam = max(corners, key=key)
            seam[1] = "seam"
            a, b = room.walls[seam[0]], room.walls[(seam[0] + 1) % n]
            reason = (f"the pattern goes all the way round the room, so it restarts at the "
                      f"{a.name}/{b.name} corner, between the two least important walls")
        breaks = {c[0] for c in corners if c[1] != "continue"}
        if not room.closed:
            breaks.add(n - 1)
        if not breaks:  # closed room with no break cannot happen after choosing a seam
            breaks = {n - 1}
        first = (max(breaks) + 1) % n
        chains, chain = [], []
        for step in range(n):
            i = (first + step) % n
            chain.append(i)
            if i in breaks:
                chains.append(chain)
                chain = []
        if chain:
            chains.append(chain)
        anchors = []
        for chain in chains:
            anchors.append(min(chain, key=lambda i: (self.rank(i, start_wall), chain.index(i))))
        return corners, reason, chains, anchors

    def propagate(self, chain, anchor, u_anchor, g):
        """Column origin of every wall in a chain, carrying the grid round its corners."""
        px, _ = self.pitch(g)
        u = {anchor: u_anchor}
        pos = chain.index(anchor)
        for a, b in zip(chain[pos:], chain[pos + 1:]):
            u[b] = (u[a] - self.faces[a].c1 + self.faces[b].c0) % px
        for a, b in zip(reversed(chain[:pos + 1]), reversed(chain[:pos])):
            u[b] = (u[a] - self.faces[a].c0 + self.faces[b].c1) % px
        return u

    # --- search --------------------------------------------------------------

    def solve(self, progress=None):
        t = self.t
        start_wall, start_x, start_name = self.start()
        corners, seam_reason, chains, anchors = self.chains()
        row_goals = self.row_goals()
        prioritised = sorted((w.tiles.priority, w.index) for w in self.room.walls
                             if w.tiles.priority is not None and w.index != start_wall)
        combos = []
        for g in t.grout_options:
            px, py = self.pitch(g)
            vs = []
            for i, (_, kind, y) in enumerate(row_goals):
                base = (y - (self.th if kind == "top" else 0)) % py
                vs.append(base)
                if i == 0:
                    vs.extend((base + k * py / 16) % py for k in range(1, 16))
            vs = sorted({round(v, 3) for v in vs})
            anchor_us = []
            for anchor in anchors:
                target = start_x if anchor == start_wall else self.faces[anchor].target
                base = target - self.tw / 2
                if anchor == start_wall:  # the start feature is always centred on a tile or a joint
                    steps = {"tile": (0,), "joint": (4,), "either": (0, 4)}[t.start_align]
                else:
                    steps = range(8)
                anchor_us.append([(base + k * px / 8) % px for k in steps])
            for v in vs:
                for us in itertools.product(*anchor_us):
                    combos.append((g, v, us))
        info(f"trying {em(len(combos))} layouts ({len(t.grout_options)} grout widths, "
             f"{len(chains)} chain{'s' if len(chains) > 1 else ''} of walls)")
        for chain, anchor in zip(chains, anchors):
            debug(f"chain {' -> '.join(self.faces[i].name for i in chain)}, set out from "
                  f"{self.faces[anchor].name}")
        cache, scored = {}, []
        for n, (g, v, us) in enumerate(combos):
            if progress:
                progress(n, len(combos), scored and min(scored)[0][0])
            u = {}
            for chain, anchor, ua in zip(chains, anchors, us):
                u.update(self.propagate(chain, anchor, ua, g))
            layouts = []
            for wi in range(len(self.faces)):
                key = (wi, g, round(v, 2), round(u[wi], 2))
                if key not in cache:
                    cache[key] = self.wall_layout(wi, g, v, u[wi])
                layouts.append(cache[key])
            ulist = [u[i] for i in range(len(self.faces))]
            reveals, reveal_problems = self.reveal_pieces(g, v, ulist)
            problems = sum(len(w.problems) for w in layouts) + len(reveal_problems)
            shortfall = sum(s for w in layouts for *_, s in w.problems) + sum(s for *_, s in reveal_problems)
            devs = [round(self.centre_dev(start_x, u[start_wall], g), 1),
                    round(self.row_dev(row_goals[0][1], row_goals[0][2], g, v), 1)]
            devs += [round(self.centre_dev(self.faces[i].target, u[i], g), 1) for _, i in prioritised]
            devs += [round(self.row_dev(kind, y, g, v), 1) for _, kind, y in row_goals[1:]]
            tiles = sum(len(w.full) + len(w.pieces) for w in layouts) + len(reveals)
            score = (problems, *devs, abs(g - t.grout), round(shortfall, 1), tiles)
            scored.append((score, n))
        if progress:
            progress(len(combos), len(combos), min(scored)[0][0])
        scored.sort()
        # pack the best few for real: offcut reuse can change the order on tile count
        best = None
        for score, n in scored[:6]:
            g, v, us = combos[n]
            res = self.result(g, v, us, chains, anchors, corners, seam_reason)
            key = (score[:-1], res.count, sum(len(s.cuts) for s in res.tiles))
            if best is None or key < best[0]:
                best = (key, res, score)
        _, res, chosen = best
        info(f"chose grout {em(res.grout)} mm; best score {chosen}")
        res.goals = self.goals(res, start_wall, start_x, start_name, prioritised, row_goals)
        for i, goal in enumerate(res.goals):
            if goal.deviation >= 0.05:
                goal.why = self._why(i, res.goals, chosen, scored, combos, (chains, anchors, corners, seam_reason))
        return res

    def continues_from(self, res, i):
        """'North (North/East corner)': the neighbour wall i takes its grid from, towards its chain's anchor."""
        chain, anchor = next((c, a) for c, a in zip(res.chains, res.anchors) if i in c)
        pos, apos = chain.index(i), chain.index(anchor)
        j = chain[pos - 1] if apos < pos else chain[pos + 1]
        a, b = (j, i) if apos < pos else (i, j)
        return f"{self.faces[j].name} ({self.faces[a].name}/{self.faces[b].name} corner)"

    def _why(self, i, goals, chosen, scored, combos, layout_args):
        """Explain why goal i was not met exactly, by comparing with the best layout that does meet it."""
        goal = goals[i]
        alt = next((sc for sc, n in scored if sc[1 + i] < 0.05), None)
        if alt is None:
            if goal.kind == "wall" and goal.note.startswith("continues from"):
                corner = goal.note.split("(")[1].rstrip(")")
                return (f"this wall carries the pattern on round the {corner}, so only the grout width can move "
                        f"it; set tiles = \"fresh\" on that corner to centre it exactly")
            return "no layout tried meets it exactly"
        n = next(n for sc, n in scored if sc is alt)
        reasons = []
        for j in range(i):  # more important goals it would break
            if alt[1 + j] > chosen[1 + j] + 0.05:
                other = goals[j]
                reasons.append(f"put {other.label} ({other.describe.split(':')[0]}) {alt[1 + j]:.1f} mm off")
        if alt[0] > chosen[0]:
            res = self.result(*combos[n], *layout_args)
            piece, desc, _ = max(res.problems, key=lambda p: p[2])
            more = alt[0] - chosen[0]
            reasons.append(f"leave {more} more piece{'s' if more > 1 else ''} below the minimum size, "
                           f"e.g. {desc} at {piece.where}")
        if not reasons:
            return "the layouts that meet it exactly need more tiles or cuts"
        return "lining it up exactly would " + " and ".join(reasons)
        if j == 0:
            res = self.result(*combos[n], *layout_args)
            piece, desc, _ = max(res.problems, key=lambda p: p[2])
            more = alt[0] - chosen[0]
            return (f"lining it up exactly would leave {more} more piece{'s' if more > 1 else ''} below the minimum "
                    f"size, e.g. {desc} at {piece.where}")
        if j <= len(goals):
            other = goals[j - 1]
            return (f"lining it up exactly would put {other.label} ({other.describe.split(':')[0]}) "
                    f"{alt[j]:.1f} mm off instead of {chosen[j]:.1f} mm")
        return "the layouts that meet it exactly need more tiles or cuts"

    def result(self, g, v, us, chains, anchors, corners, seam_reason):
        u = {}
        for chain, anchor, ua in zip(chains, anchors, us):
            u.update(self.propagate(chain, anchor, ua, g))
        ulist = [u[i] for i in range(len(self.faces))]
        walls = [self.wall_layout(wi, g, v, ulist[wi], detail=True) for wi in range(len(self.faces))]
        reveals, reveal_problems = self.reveal_pieces(g, v, ulist)
        cut = [p for w in walls for p in w.pieces] + reveals
        for i, p in enumerate(cut):
            p.where = p.where or f"{self.faces[p.wall].name} row {p.row + 1}"
        packed = best_pack([(str(i), p.w, p.h) for i, p in enumerate(cut)], self.tw, self.th, self.t.kerf,
                           self.t.rotate) if cut else []
        full = sum(len(w.full) for w in walls)
        return Result(g, v, ulist, walls, reveals, packed, full, [], corners, seam_reason, chains, anchors,
                      reveal_problems)

    def goals(self, res, start_wall, start_x, start_name, prioritised, row_goals):
        px, py = self.pitch(res.grout)
        u, g, v = res.u, res.grout, res.v
        out = []
        kind = "tile" if mod_dist(start_x - (u[start_wall] + self.tw / 2), px) < TOL else "joint"
        out.append(Goal("start", "start", f"{start_name}: {kind} centred",
                        self.centre_dev(start_x, u[start_wall], g), px / 4))
        label, k, y = row_goals[0]
        out.append(Goal("row", "rows 1", label, self.row_dev(k, y, g, v), py / 2))
        for p, i in prioritised:
            f = self.faces[i]
            how = "anchor of its chain" if i in res.anchors else f"continues from {self.continues_from(res, i)}"
            out.append(Goal("wall", f"priority {p}", f"{f.name} ({f.target_name}): tile or joint centred",
                            self.centre_dev(f.target, u[i], g), px / 4, how))
        for n, (label, k, y) in enumerate(row_goals[1:], 2):
            out.append(Goal("row", f"rows {n}", label, self.row_dev(k, y, g, v), py / 2))
        return out


# --- rectangle helpers -----------------------------------------------------------

def _subtract(r, h):
    """r minus h, as up to four rectangles."""
    x0, y0, x1, y1 = r
    hx0, hy0, hx1, hy1 = max(h[0], x0), max(h[1], y0), min(h[2], x1), min(h[3], y1)
    if hx1 - hx0 <= EPS or hy1 - hy0 <= EPS:
        return [r]
    out = [(x0, y0, hx0, y1), (hx1, y0, x1, y1), (hx0, y0, hx1, hy0), (hx0, hy1, hx1, y1)]
    return [o for o in out if o[2] - o[0] > EPS and o[3] - o[1] > EPS]


def _touch(a, b):
    """Whether two rectangles share part of an edge."""
    if abs(a[2] - b[0]) < TOL or abs(b[2] - a[0]) < TOL:
        return min(a[3], b[3]) - max(a[1], b[1]) > TOL
    if abs(a[3] - b[1]) < TOL or abs(b[3] - a[1]) < TOL:
        return min(a[2], b[2]) - max(a[0], b[0]) > TOL
    return False


def _components(rects):
    groups = []
    for r in rects:
        joined = [g for g in groups if any(_touch(r, o) for o in g)]
        merged = [r] + [o for g in joined for o in g]
        groups = [g for g in groups if g not in joined] + [merged]
    return groups


def _joined(r, rects, axis, pos):
    """Whether rectangle r's edge at pos (an x edge if axis is x) is shared with another of rects."""
    for o in rects:
        if o is r:
            continue
        if axis == "x" and (abs(o[2] - pos) < TOL or abs(o[0] - pos) < TOL) and \
                min(o[3], r[3]) - max(o[1], r[1]) > TOL and (o[0] < pos - TOL or o[2] > pos + TOL):
            return True
        if axis == "y" and (abs(o[3] - pos) < TOL or abs(o[1] - pos) < TOL) and \
                min(o[2], r[2]) - max(o[0], r[0]) > TOL and (o[1] < pos - TOL or o[3] > pos + TOL):
            return True
    return False
