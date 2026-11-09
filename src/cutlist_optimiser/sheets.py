"""Split walls into sheet-sized pieces and search for the layout needing fewest sheets.

Model:
  * Vertical joints may only fall on studs (or the wall ends).  A wall is split
    into "columns" spanning one or more stud bays, each no wider than a sheet.
  * Each column is filled from bottom gap to ceiling with a stack of pieces of
    the column's width.  Stay-out areas (windows, doors, ...) have their sides on
    studs, which always carry a joint; columns under one are filled separately
    below and above it.  Horizontal joints may fall anywhere, but joints on a
    noggin are preferred (or required, depending on settings).  Noggins are
    given per stud bay; a joint across a column spanning several bays is
    checked bay by bay.
  * At a corner a wall's sheets can stop short by the sheet thickness (butting
    against the other wall's sheets) or run past by it (covering the other
    wall's sheet edge).
  * Optionally, horizontal joints in neighbouring columns are staggered.
  * All pieces are then packed onto sheets; offcuts are reused.
"""

import math
import random
from dataclasses import dataclass

from .config import ConfigError
from .geometry import framing_x, sheet_offset
from .packing import EPS, best_pack


@dataclass(frozen=True)
class Stack:
    heights: tuple  # nominal piece heights, bottom to top
    off_noggin: int  # bays crossed by a horizontal joint with no noggin there


@dataclass
class Piece:
    label: str
    x0: float  # nominal joint lines, wall coordinates (mm from floor / wall start)
    x1: float
    y0: float
    y1: float
    w: float  # actual cut size (joint gap removed)
    h: float
    joint_support: tuple | None  # joint at the top of this piece: (bays with noggin, bays); None = no joint


@dataclass
class Result:
    walls: list  # per wall: list of columns, each a list of Pieces bottom to top (may be empty)
    sheets: list
    lower_bound: int
    off_noggin: int
    aligned: int  # pairs of joints in neighbouring columns closer than the stagger distance

    @property
    def sheet_area(self):
        return sum(s.area for s in self.sheets)

    @property
    def used_area(self):
        """Area of all sheets that ends up in pieces; the rest is offcuts and saw kerf."""
        return sum(s.used_area for s in self.sheets)

    @property
    def cuts(self):
        return sum(len(s.cuts) for s in self.sheets)

    @property
    def utilisation(self):
        return self.used_area / self.sheet_area if self.sheets else 0.0


def joint_support(y, bays, tol):
    """Number of bays (each a list of noggin heights) with a noggin within tol of height y."""
    return sum(any(abs(y - n) <= tol + EPS for n in bay) for bay in bays)


def stack_options(H, hmax, bays, min_piece, mode, tol=10, keep=8, ordered=False):
    """Ways to fill height H with pieces <= hmax.

    `bays` holds the noggin heights (relative to the panel bottom) of each stud bay the column spans.
    With `ordered`, stacks with the same pieces in a different order (so joints at different
    heights) are kept as separate options; otherwise only the best order is kept.
    """
    joints = sorted({n for bay in bays for n in bay})
    nmin = math.ceil(H / hmax - EPS)
    cands = set(joints)
    # a joint between two nearby noggins in different bays can catch both
    cands.update((a + b) / 2 for a in joints for b in joints if 0 < b - a <= 2 * tol)
    for n in (nmin, nmin + 1):
        cands.update(round(H * k / n) for k in range(1, n))
    for k in range(1, 2 * nmin + 2):
        cands.update((k * hmax / 2, H - k * hmax / 2))
        for j in joints:
            cands.update((j + k * hmax, j - k * hmax))
    cands = sorted(c for c in cands if min_piece - EPS <= c <= H - min_piece + EPS)

    def unsupported(c):
        return len(bays) - joint_support(c, bays, tol)

    found = {}

    def dfs(pos, cuts):
        if H - pos <= hmax + EPS:
            heights = tuple(b - a for a, b in zip([0, *cuts], [*cuts, H]))
            off = sum(unsupported(c) for c in cuts)
            key = tuple(round(h, 1) for h in heights)
            if not ordered:
                key = tuple(sorted(key))
            if key not in found or off < found[key].off_noggin:
                found[key] = Stack(heights, off)
        if len(cuts) + 1 >= nmin + 1:  # allow at most one piece more than the minimum
            return
        for c in cands:
            if c - pos >= min_piece - EPS and c - pos <= hmax + EPS:
                dfs(c, [*cuts, c])

    dfs(0.0, [])
    opts = list(found.values())
    if mode == "require":
        opts = [o for o in opts if o.off_noggin == 0]
    opts.sort(key=lambda o: (o.off_noggin, len(o.heights)))
    return opts[:keep]


class Solver:
    def __init__(self, room, seed=0):
        room.require_sheets()
        self.room = room
        self.s = s = room.sheets
        self.walls = room.walls
        self.rng = random.Random(seed)
        self.L, self.S = max(s.size), min(s.size)
        self.bottom, self.top = s.bottom_gap, room.height - s.top_gap
        self.positions = [[0.0, *w.studs, w.length] for w in self.walls]
        self.ends = []  # per wall: how far the sheets run past the framing at (start, end)
        self.stay_out = []  # per wall: (x0, x1, y0, y1) framing rectangles left unsheeted
        self.forced = []  # per wall: stud indices that must carry a vertical joint
        self._segments = {}
        self._stacks = {}
        self._packs = {}
        for wi, (w, pos) in enumerate(zip(self.walls, self.positions)):
            (c0, t0), (c1, t1) = room.start_corner(wi), room.end_corner(wi)
            self.ends.append((sheet_offset(c0, t0, s.thickness), sheet_offset(c1, t1, s.thickness)))
            for a, b in zip(pos, pos[1:]):
                width = b - a + (self.ends[-1][0] if a == 0 else 0) + (self.ends[-1][1] if b == pos[-1] else 0)
                if width > self.L + EPS:
                    raise ConfigError(f"{w.where}.studs", f"the bay from {a:g} to {b:g} is {width:g} mm wide, "
                                                          f"wider than a {self.L:g} mm sheet",
                                      "add the studs in that bay (sheet edges can only land on studs)")
            forced, rects = set(), []
            for o in w.stay_out:
                if not o.applies("sheets"):
                    continue
                x = [framing_x(room, wi, v) for v in o.x]
                for v in x:
                    idx = [i for i, p in enumerate(pos) if abs(p - v) < 0.5]
                    if not idx:
                        raise ConfigError(o.where, f"its edge at x = {v:g} is not on a stud",
                                          "stay-out edges must be on stud centres in sheet mode (studs at "
                                          + ", ".join(f"{p:g}" for p in pos) + "); add the trimmer stud or "
                                          "set only = \"tiles\" if sheets go behind it")
                    forced.add(idx[0])
                rects.append((*x, *o.y))
            self.stay_out.append(rects)
            self.forced.append(forced - {0, len(pos) - 1})

    # --- layout generation -------------------------------------------------

    def hmax(self, width):
        return self.L if width <= self.S + EPS else self.S

    def extent(self, wi, i, j):
        """Sheeted x range of the column between studs i and j, allowing for corners."""
        pos = self.positions[wi]
        x0, x1 = pos[i], pos[j]
        if i == 0:
            x0 -= self.ends[wi][0]
        if j == len(pos) - 1:
            x1 += self.ends[wi][1]
        return x0, x1

    def segments(self, wi, i, j):
        """Height ranges (from floor) to fill in the column between studs i and j."""
        key = (wi, i, j)
        if key not in self._segments:
            x0, x1 = self.positions[wi][i], self.positions[wi][j]
            segs = [(self.bottom, self.top)]
            for sx0, sx1, sy0, sy1 in self.stay_out[wi]:
                if sx0 - 0.5 <= x0 and x1 <= sx1 + 0.5:
                    segs = [part for a, b in segs
                            for part in ((a, min(b, sy0)), (max(a, sy1), b)) if part[1] - part[0] > EPS]
            self._segments[key] = segs
        return self._segments[key]

    def bays(self, wi, i, j, a=0.0):
        """Noggin heights (relative to a) for each stud bay between studs i and j."""
        if self.s.noggin_joints == "ignore":
            return [[] for _ in range(i, j)]
        return [[n - a for n in self.walls[wi].noggins[k]] for k in range(i, j)]

    def stacks(self, wi, i, j, seg):
        x0, x1 = self.extent(wi, i, j)
        hmax = self.hmax(x1 - x0)
        key = (wi, i, j, seg)
        if key not in self._stacks:
            a, b = seg
            bays = [[n for n in bay if 0 < n < b - a] for bay in self.bays(wi, i, j, a)]
            stagger = self.s.stagger > 0
            opts = stack_options(b - a, hmax, bays, self.s.min_piece, self.s.noggin_joints,
                                 self.s.noggin_tolerance, keep=40 if stagger else 8, ordered=stagger)
            if not opts:
                raise ConfigError(
                    self.walls[wi].where, f"no way to put every horizontal joint on a noggin between {a:g} "
                                          f"and {b:g} mm high for {hmax:g} mm tall pieces",
                    "add noggins at suitable heights, or set noggin_joints = \"prefer\" in [sheets]")
            self._stacks[key] = opts
        return self._stacks[key]

    def column_stacks(self, wi, i, j):
        """Stack options for each segment of a column."""
        return [self.stacks(wi, i, j, seg) for seg in self.segments(wi, i, j)]

    def partition(self, wi, greedy=False):
        """Choose which studs carry vertical joints: list of (i, j) position indices."""
        pos = self.positions[wi]
        cols, i = [], 0
        while i < len(pos) - 1:
            stop = min([f for f in self.forced[wi] if f > i], default=len(pos) - 1)
            cands = [j for j in range(i + 1, stop + 1)
                     if self.extent(wi, i, j)[1] - self.extent(wi, i, j)[0] <= self.L + EPS]
            if not cands:
                raise ConfigError(self.walls[wi].where, f"the bay starting at {pos[i]:g} is wider than a "
                                                        f"sheet once the corner is allowed for",
                                  "add a stud in that bay")
            if greedy:
                j = cands[-1]
            else:
                def weight(j):
                    w = pos[j] - pos[i]
                    exact = min(abs(w - self.L), abs(w - self.S)) < 0.5
                    return w * (4 if exact else 1)
                j = self.rng.choices(cands, [weight(j) for j in cands])[0]
            cols.append((i, j))
            i = j
        return cols

    def random_wall(self, wi, greedy=False):
        part = self.partition(wi, greedy)
        opts = [tuple(0 if greedy else self.rng.randrange(len(o)) for o in self.column_stacks(wi, i, j))
                for i, j in part]
        return (tuple(part), tuple(opts))

    # --- evaluation -------------------------------------------------------

    def build(self, state):
        g = self.s.joint_gap / 2
        walls, off = [], 0
        for wi, (part, opts) in enumerate(state):
            pos = self.positions[wi]
            cols = []
            for ci, ((i, j), seg_opts) in enumerate(zip(part, opts)):
                x0, x1 = self.extent(wi, i, j)
                w = x1 - x0 - g * (i > 0) - g * (j < len(pos) - 1)
                col = []
                for seg, stack_opts, oi in zip(self.segments(wi, i, j), self.column_stacks(wi, i, j), seg_opts):
                    st = stack_opts[oi]
                    off += st.off_noggin
                    y, n = seg[0], len(st.heights)
                    for k, h in enumerate(st.heights):
                        top = k < n - 1
                        on = None
                        if top:
                            on = (joint_support(y + h, self.walls[wi].noggins[i:j], self.s.noggin_tolerance),
                                  j - i)
                        label = f"{wi + 1}.{ci + 1}{chr(ord('a') + len(col))}"
                        col.append(Piece(label, x0, x1, y, y + h, w, h - g * (k > 0) - g * top, on))
                        y += h
                cols.append(col)
            walls.append(cols)
        return walls, off

    def aligned(self, walls):
        """Count joint pairs in neighbouring columns that are closer than the stagger distance."""
        if self.s.stagger <= 0:
            return 0
        count = 0
        for cols in walls:
            joints = [[p.y1 for p in col if p.joint_support is not None] for col in cols]
            for left, right in zip(joints, joints[1:]):
                count += sum(abs(a - b) < self.s.stagger - EPS for a in left for b in right)
        return count

    def evaluate(self, state):
        walls, off = self.build(state)
        pieces = [(p.label, p.w, p.h) for cols in walls for col in cols for p in col]
        key = tuple(sorted((round(w, 1), round(h, 1)) for _, w, h in pieces))
        if key not in self._packs:
            # pack anonymised pieces so the result can be cached by size alone
            sheets = best_pack([(str(i), w, h) for i, (w, h) in enumerate(key)],
                               self.L, self.S, self.s.kerf)
            self._packs[key] = (len(sheets), max((s.largest_offcut() for s in sheets), default=0))
        n, offcut = self._packs[key]
        if self.s.noggin_joints == "ignore":
            off = 0
        return (self.aligned(walls), n, off, len(pieces), -offcut)

    def solve(self, iterations=3000, progress=None):
        """Search for the best layout. `progress(done, total, best_sheets)` is called each iteration."""
        current = tuple(self.random_wall(wi, greedy=True) for wi in range(len(self.walls)))
        cur_score = self.evaluate(current)
        best, best_score = current, cur_score
        for it in range(iterations):
            if progress:
                progress(it, iterations, best_score[1])
            cand = list(current)
            r = self.rng.random()
            if r < 0.1:
                cand = [self.random_wall(wi) for wi in range(len(self.walls))]
            else:
                wi = self.rng.randrange(len(self.walls))
                part, opts = cand[wi]
                ci = self.rng.randrange(len(part))
                choices = self.column_stacks(wi, *part[ci])
                if r < 0.55 or not choices:
                    cand[wi] = self.random_wall(wi)
                else:
                    si = self.rng.randrange(len(choices))
                    seg_opts = list(opts[ci])
                    seg_opts[si] = self.rng.randrange(len(choices[si]))
                    opts = list(opts)
                    opts[ci] = tuple(seg_opts)
                    cand[wi] = (part, tuple(opts))
            cand = tuple(cand)
            score = self.evaluate(cand)
            if score <= cur_score:
                current, cur_score = cand, score
                if score < best_score:
                    best, best_score = cand, score
        if progress:
            progress(iterations, iterations, best_score[1])
        return self.result(best)

    def result(self, state):
        walls, off = self.build(state)
        pieces = [(p.label, p.w, p.h) for cols in walls for col in cols for p in col]
        # same input order as evaluate() so the packing is identical
        pieces.sort(key=lambda p: (round(p[1], 1), round(p[2], 1)))
        sheets = best_pack(pieces, self.L, self.S, self.s.kerf)
        area = sum(w * h for _, w, h in pieces)
        lower = math.ceil(area / (self.L * self.S) - EPS)
        return Result(walls, sheets, lower, off, self.aligned(walls))
