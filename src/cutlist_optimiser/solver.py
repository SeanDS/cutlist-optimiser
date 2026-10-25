"""Split walls into sheet-sized pieces and search for the layout needing fewest sheets.

Model:
  * Vertical joints may only fall on studs (or the wall ends).  A wall is split
    into "columns" spanning one or more stud bays, each no wider than a sheet.
  * Each column is filled from bottom gap to ceiling with a stack of pieces of
    the column's width.  Stay-out areas (windows, doors, ...) have their sides on
    studs, which always carry a joint; columns under one are filled separately
    below and above it.  Horizontal joints may fall anywhere, but joints on a
    noggin are preferred (or required, depending on settings).
  * All pieces are then packed onto sheets; offcuts are reused.
"""

import math
import random
from dataclasses import dataclass, field

from .packing import EPS, best_pack


@dataclass
class Settings:
    height: float = 2400
    sheet: tuple = (1200, 800)
    bottom_gap: float = 2
    top_gap: float = 0
    kerf: float = 3
    joint_gap: float = 3
    min_piece: float = 100
    noggin_joints: str = "prefer"  # prefer | require | ignore


@dataclass
class Wall:
    name: str
    studs: list  # separations between consecutive studs (centre to centre), wall end to wall end
    noggins: list = field(default_factory=list)  # noggin centre heights from floor
    stay_out: list = field(default_factory=list)  # (x0, x1, y0, y1) areas left unsheeted

    @property
    def positions(self):
        pos = [0.0]
        for s in self.studs:
            pos.append(pos[-1] + s)
        return pos


@dataclass(frozen=True)
class Stack:
    heights: tuple  # nominal piece heights, bottom to top
    off_noggin: int  # horizontal joints not backed by a noggin


@dataclass
class Piece:
    label: str
    x0: float  # nominal joint lines, wall coordinates (mm from floor / wall start)
    x1: float
    y0: float
    y1: float
    w: float  # actual cut size (joint gap removed)
    h: float
    joint_on_noggin: bool | None  # for the joint at the top of this piece; None = no joint


@dataclass
class Result:
    walls: list  # per wall: list of columns, each a list of Pieces bottom to top (may be empty)
    sheets: list
    lower_bound: int
    off_noggin: int


def stack_options(H, hmax, joints, min_piece, mode, keep=8):
    """Ways to fill height H with pieces <= hmax. `joints` are noggin heights relative to the panel bottom."""
    nmin = math.ceil(H / hmax - EPS)
    cands = set(joints)
    for n in (nmin, nmin + 1):
        cands.update(round(H * k / n) for k in range(1, n))
    for k in range(1, nmin + 2):
        cands.update((k * hmax, H - k * hmax))
        for j in joints:
            cands.update((j + k * hmax, j - k * hmax))
    cands = sorted(c for c in cands if min_piece - EPS <= c <= H - min_piece + EPS)

    def on_noggin(c):
        return any(abs(c - j) < 0.5 for j in joints)

    found = {}

    def dfs(pos, cuts):
        if H - pos <= hmax + EPS:
            heights = tuple(b - a for a, b in zip([0, *cuts], [*cuts, H]))
            off = sum(not on_noggin(c) for c in cuts)
            key = tuple(sorted(round(h, 1) for h in heights))
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
    def __init__(self, settings: Settings, walls: list, seed=0):
        self.s = settings
        self.walls = walls
        self.rng = random.Random(seed)
        self.L, self.S = max(settings.sheet), min(settings.sheet)
        self.bottom, self.top = settings.bottom_gap, settings.height - settings.top_gap
        self.positions = [w.positions for w in walls]
        self.forced = []  # per wall: stud indices that must carry a vertical joint
        self._segments = {}
        self._stacks = {}
        self._packs = {}
        for w, pos in zip(walls, self.positions):
            if not w.studs or any(s <= 0 or s > self.L + EPS for s in w.studs):
                raise ValueError(f"wall {w.name!r}: stud separations must be > 0 and <= {self.L:g}")
            forced = set()
            for x0, x1, y0, y1 in w.stay_out:
                if not (x0 < x1 and y0 < y1):
                    raise ValueError(f"wall {w.name!r}: stay-out area {x0:g}-{x1:g} x {y0:g}-{y1:g} is empty")
                for x in (x0, x1):
                    idx = [i for i, p in enumerate(pos) if abs(p - x) < 0.5]
                    if not idx:
                        raise ValueError(f"wall {w.name!r}: stay-out area edge x={x:g} is not on a stud "
                                         f"(studs at {', '.join(f'{p:g}' for p in pos)})")
                    forced.add(idx[0])
            self.forced.append(forced - {0, len(pos) - 1})

    # --- layout generation -------------------------------------------------

    def hmax(self, width):
        return self.L if width <= self.S + EPS else self.S

    def segments(self, wi, i, j):
        """Height ranges (from floor) to fill in the column between studs i and j."""
        key = (wi, i, j)
        if key not in self._segments:
            x0, x1 = self.positions[wi][i], self.positions[wi][j]
            segs = [(self.bottom, self.top)]
            for sx0, sx1, sy0, sy1 in self.walls[wi].stay_out:
                if sx0 - 0.5 <= x0 and x1 <= sx1 + 0.5:
                    segs = [part for a, b in segs
                            for part in ((a, min(b, sy0)), (max(a, sy1), b)) if part[1] - part[0] > EPS]
            self._segments[key] = segs
        return self._segments[key]

    def stacks(self, wi, width, seg):
        hmax = self.hmax(width)
        key = (wi, hmax, seg)
        if key not in self._stacks:
            a, b = seg
            joints = [] if self.s.noggin_joints == "ignore" else [
                n - a for n in self.walls[wi].noggins if a < n < b]
            opts = stack_options(b - a, hmax, joints, self.s.min_piece, self.s.noggin_joints)
            if not opts:
                raise ValueError(
                    f"wall {self.walls[wi].name!r}: no way to put every horizontal joint on a noggin "
                    f"between {a:g} and {b:g} mm for {hmax:g} mm tall pieces; add noggins or use "
                    f"noggin_joints = 'prefer'")
            self._stacks[key] = opts
        return self._stacks[key]

    def column_stacks(self, wi, i, j):
        """Stack options for each segment of a column."""
        width = self.positions[wi][j] - self.positions[wi][i]
        return [self.stacks(wi, width, seg) for seg in self.segments(wi, i, j)]

    def partition(self, wi, greedy=False):
        """Choose which studs carry vertical joints: list of (i, j) position indices."""
        pos = self.positions[wi]
        cols, i = [], 0
        while i < len(pos) - 1:
            stop = min([f for f in self.forced[wi] if f > i], default=len(pos) - 1)
            cands = [j for j in range(i + 1, stop + 1) if pos[j] - pos[i] <= self.L + EPS]
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
                x0, x1 = pos[i], pos[j]
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
                            on = any(abs(y + h - nog) < 0.5 for nog in self.walls[wi].noggins)
                        label = f"{wi + 1}.{ci + 1}{chr(ord('a') + len(col))}"
                        col.append(Piece(label, x0, x1, y, y + h, w, h - g * (k > 0) - g * top, on))
                        y += h
                cols.append(col)
            walls.append(cols)
        return walls, off

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
        return (n, off, len(pieces), -offcut)

    def solve(self, iterations=3000, progress=None):
        """Search for the best layout. `progress(done, total, best_sheets)` is called each iteration."""
        current = tuple(self.random_wall(wi, greedy=True) for wi in range(len(self.walls)))
        cur_score = self.evaluate(current)
        best, best_score = current, cur_score
        for it in range(iterations):
            if progress:
                progress(it, iterations, best_score[0])
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
            progress(iterations, iterations, best_score[0])
        return self.result(best)

    def result(self, state):
        walls, off = self.build(state)
        pieces = [(p.label, p.w, p.h) for cols in walls for col in cols for p in col]
        # same input order as evaluate() so the packing is identical
        pieces.sort(key=lambda p: (round(p[1], 1), round(p[2], 1)))
        sheets = best_pack(pieces, self.L, self.S, self.s.kerf)
        area = sum(w * h for _, w, h in pieces)
        lower = math.ceil(area / (self.L * self.S) - EPS)
        return Result(walls, sheets, lower, off)
