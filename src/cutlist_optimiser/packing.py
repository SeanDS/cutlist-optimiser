"""Guillotine 2D bin packing of rectangular pieces onto fixed-size sheets."""

from dataclasses import dataclass, field

EPS = 1e-6


@dataclass
class Placement:
    label: str
    x: float
    y: float
    w: float  # size as laid on the sheet (after rotation)
    h: float
    rotated: bool


@dataclass
class Sheet:
    width: float
    height: float
    placements: list = field(default_factory=list)
    free: list = field(default_factory=list)  # (x, y, w, h) offcut rectangles
    cuts: list = field(default_factory=list)  # (x0, y0, x1, y1) guillotine cut lines, in cutting order

    def __post_init__(self):
        if not self.free:
            self.free = [(0.0, 0.0, self.width, self.height)]

    def largest_offcut(self):
        return max((w * h for _, _, w, h in self.free), default=0.0)


def _split(free, w, h, kerf):
    """Split a free rectangle after placing w x h in its corner.

    Picks the guillotine direction that leaves the biggest single offcut.
    Returns the new free rectangles and the cuts (along the kerf centre) needed.
    """
    fx, fy, fw, fh = free
    rw, th = fw - w - kerf, fh - h - kerf
    along = [(fx + w + kerf, fy, rw, h), (fx, fy + h + kerf, fw, th)]
    across = [(fx + w + kerf, fy, rw, fh), (fx, fy + h + kerf, w, th)]

    def valid(rects):
        return [r for r in rects if r[2] > EPS and r[3] > EPS]

    def biggest(rects):
        return max((r[2] * r[3] for r in valid(rects)), default=0.0)

    cx, cy = fx + w + kerf / 2, fy + h + kerf / 2
    if biggest(along) >= biggest(across):
        rects, cuts = along, [(fx, cy, fx + fw, cy, fh - h), (cx, fy, cx, fy + h, fw - w)]
    else:
        rects, cuts = across, [(cx, fy, cx, fy + fh, fw - w), (fx, cy, fx + w, cy, fh - h)]
    # a cut is only needed if there is material beyond the piece on that side
    return valid(rects), [c[:4] for c in cuts if c[4] > EPS]


def _place(sheets, label, w, h, kerf):
    best = None
    for s in sheets:
        for i, (_, _, fw, fh) in enumerate(s.free):
            for pw, ph, rot in ((w, h, False), (h, w, True)):
                if pw <= fw + EPS and ph <= fh + EPS:
                    score = (min(fw - pw, fh - ph), max(fw - pw, fh - ph))
                    if best is None or score < best[0]:
                        best = (score, s, i, pw, ph, rot)
    if best is None:
        return False
    _, s, i, pw, ph, rot = best
    free = s.free.pop(i)
    s.placements.append(Placement(label, free[0], free[1], pw, ph, rot))
    rects, cuts = _split(free, pw, ph, kerf)
    s.free.extend(rects)
    s.cuts.extend(cuts)
    return True


def pack(pieces, sheet_w, sheet_h, kerf, key):
    """Pack (label, w, h) pieces in the order given by `key` (descending)."""
    sheets = []
    for label, w, h in sorted(pieces, key=key, reverse=True):
        if not _place(sheets, label, w, h, kerf):
            sheets.append(Sheet(sheet_w, sheet_h))
            if not _place(sheets[-1:], label, w, h, kerf):
                raise ValueError(f"piece {label} ({w:g} x {h:g}) does not fit on a sheet")
    return sheets


ORDERS = [
    lambda p: p[1] * p[2],
    lambda p: max(p[1], p[2]),
    lambda p: (p[2], p[1]),
    lambda p: (p[1], p[2]),
]


def best_pack(pieces, sheet_w, sheet_h, kerf):
    """Try several sort orders, return the packing with fewest sheets."""
    results = [pack(pieces, sheet_w, sheet_h, kerf, key) for key in ORDERS]
    return min(results, key=lambda ss: (len(ss), -max(s.largest_offcut() for s in ss)))
