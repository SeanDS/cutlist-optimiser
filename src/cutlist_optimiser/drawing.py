"""Plain SVG drawings of the wall layouts and the cutting diagrams."""

from .report import f

MARGIN = 20


class Svg:
    def __init__(self):
        self.parts = []
        self.width = self.height = 0

    def _grow(self, x, y):
        self.width, self.height = max(self.width, x), max(self.height, y)

    def text(self, x, y, t, size=12, anchor="start", colour="#000", bold=False):
        weight = ' font-weight="bold"' if bold else ""
        self.parts.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-family="sans-serif" '
                          f'text-anchor="{anchor}" fill="{colour}"{weight}>{t}</text>')
        self._grow(x + len(str(t)) * size * 0.6, y)

    def rect(self, x, y, w, h, style):
        self.parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" {style}/>')
        self._grow(x + w, y + h)

    def line(self, x0, y0, x1, y1, style):
        self.parts.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" {style}/>')
        self._grow(max(x0, x1), max(y0, y1))

    def raw(self, s):
        self.parts.append(s)

    def crossed(self, x, y, w, h, colour="#c33"):
        self.rect(x, y, w, h, f'fill="#fff" stroke="{colour}"')
        self.line(x, y, x + w, y + h, f'stroke="{colour}"')
        self.line(x, y + h, x + w, y, f'stroke="{colour}"')

    def save(self, path):
        with open(path, "w") as fh:
            fh.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width + MARGIN:.0f}" '
                     f'height="{self.height + MARGIN:.0f}"><rect width="100%" height="100%" fill="#fff"/>'
                     f'{"".join(self.parts)}</svg>\n')


WASTE = ('<defs><pattern id="waste" width="8" height="8" patternUnits="userSpaceOnUse" '
         'patternTransform="rotate(45)"><rect width="8" height="8" fill="#ddd"/>'
         '<line x1="0" y1="0" x2="0" y2="8" stroke="#999" stroke-width="3"/></pattern></defs>')


def cutting_diagrams(svg, sheets, y, title, scale, per_row=3, labels=True):
    """Each stock sheet or tile whole: pieces labelled, offcuts hatched, cuts dashed and numbered."""
    svg.raw(WASTE)
    if not sheets:
        return y
    cell_w = sheets[0].width * scale + 30
    cell_h = sheets[0].height * scale + 40
    for i, (sh, name) in enumerate(zip(sheets, title)):
        bx, by = MARGIN + (i % per_row) * cell_w, y + (i // per_row) * cell_h
        svg.text(bx, by + 12, name, 13, bold=True)
        by += 20
        svg.rect(bx, by, sh.width * scale, sh.height * scale, 'fill="#f4ead2"')
        for fx, fy, fw, fh in sh.free:
            svg.rect(bx + fx * scale, by + fy * scale, fw * scale, fh * scale, 'fill="url(#waste)"')
        for pl in sh.placements:
            cx, cy = bx + (pl.x + pl.w / 2) * scale, by + (pl.y + pl.h / 2) * scale
            size = 12 if min(pl.w, pl.h) * scale > 40 else 9
            if labels:
                svg.text(cx, cy - 2, pl.label, size, "middle", bold=True)
            svg.text(cx, cy + size, f"{f(pl.w)} x {f(pl.h)}", size - 2, "middle")
        for n, (x0, y0, x1, y1) in enumerate(sh.cuts, 1):
            svg.line(bx + x0 * scale, by + y0 * scale, bx + x1 * scale, by + y1 * scale,
                     'stroke="#c00" stroke-width="1.5" stroke-dasharray="6 3"')
            mx, my = bx + (x0 + x1) / 2 * scale, by + (y0 + y1) / 2 * scale
            svg.raw(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="7" fill="#c00"/>')
            svg.text(mx, my + 3.5, n, 9, "middle", "#fff", bold=True)
        svg.rect(bx, by, sh.width * scale, sh.height * scale, 'fill="none" stroke="#000" stroke-width="1.5"')
    rows = (len(sheets) + per_row - 1) // per_row
    return y + rows * cell_h


def sheets_svg(solver, res, path, scale=0.1, sheet_scale=0.25):
    """Wall elevations with studs, noggins and pieces, then each sheet with its cut lines."""
    room, svg, y = solver.room, Svg(), 10
    x0 = MARGIN + 2 * room.sheets.thickness * scale
    for wi, (wall, cols) in enumerate(zip(room.walls, res.walls)):
        svg.text(MARGIN, y + 12, wall.name, 14, bold=True)
        y += 20
        top = y + room.height * scale
        pos = solver.positions[wi]
        svg.rect(x0, y, pos[-1] * scale, room.height * scale, 'fill="#eee" stroke="#999"')
        for col in cols:
            for pc in col:
                px, py = x0 + pc.x0 * scale, top - pc.y1 * scale
                svg.rect(px, py, (pc.x1 - pc.x0) * scale, (pc.y1 - pc.y0) * scale,
                         'fill="#9bd" fill-opacity="0.6" stroke="#000"')
                if (pc.y1 - pc.y0) * scale >= 16:
                    svg.text(px + 4, py + 14, pc.label)
        # framing drawn over the pieces so it shows through
        for x in pos:
            svg.line(x0 + x * scale, y, x0 + x * scale, top, 'stroke="#a0522d" stroke-width="1.5" stroke-opacity="0.7"')
        for a, b, bay in zip(pos, pos[1:], wall.noggins):
            for n in bay:
                svg.line(x0 + a * scale, top - n * scale, x0 + b * scale, top - n * scale,
                         'stroke="#a0522d" stroke-width="3"')
        for sx0, sx1, sy0, sy1 in solver.stay_out[wi]:
            sy1 = min(sy1, room.height)
            svg.crossed(x0 + sx0 * scale, top - sy1 * scale, (sx1 - sx0) * scale, (sy1 - sy0) * scale)
        y = top + 30
    names = [f"Sheet {i}  ({sh.used_area / sh.area:.1%} used, {len(sh.cuts)} cuts)"
             for i, sh in enumerate(res.sheets, 1)]
    cutting_diagrams(svg, res.sheets, y, names, sheet_scale)
    svg.save(path)


def tiles_svg(tiler, res, path, scale=0.15):
    """Each wall's tiled face: whole tiles, cut pieces with sizes, mitred edges, openings and centre lines."""
    svg, y = Svg(), 10
    room = tiler.room
    start_wall, start_x, _ = tiler.start()
    for f_, layout in zip(tiler.faces, res.walls):
        x0, x1 = tiler.extent(f_, res.grout)
        ox = MARGIN - f_.b0 * scale  # draw from the boarded start corner
        svg.text(MARGIN, y + 12, f"{f_.name}  (tiled face {f(f_.c1 - f_.c0)} mm)", 14, bold=True)
        y += 20
        top = y + room.height * scale
        svg.rect(ox + f_.b0 * scale, y, (f_.b1 - f_.b0) * scale, room.height * scale, 'fill="#ccc"')
        for tx0, ty0, tx1, ty1 in layout.full:
            svg.rect(ox + tx0 * scale, top - ty1 * scale, (tx1 - tx0) * scale, (ty1 - ty0) * scale,
                     'fill="#e8f0f7" stroke="#567" stroke-width="0.5"')
        for pc in layout.pieces:
            px, py, pw, ph = ox + pc.x0 * scale, top - pc.y1 * scale, pc.w * scale, pc.h * scale
            colour = "#f2c4c4" if any(pc is q for q, *_ in layout.problems) else "#b9d3e8"
            svg.rect(px, py, pw, ph, f'fill="{colour}" stroke="#345" stroke-width="0.5"')
            if pw > 34 and ph > 10:
                svg.text(px + pw / 2, py + ph / 2 + 3, f"{f(pc.w)}x{f(pc.h)}", 7, "middle")
            elif ph > 34 and pw > 8:
                svg.raw(f'<text x="{px + pw / 2 + 2:.1f}" y="{py + ph / 2:.1f}" font-size="7" '
                        f'font-family="sans-serif" text-anchor="middle" '
                        f'transform="rotate(-90 {px + pw / 2 + 2:.1f} {py + ph / 2:.1f})">{f(pc.w)}x{f(pc.h)}</text>')
        for h in f_.holes:
            svg.crossed(ox + h.x0 * scale, top - h.y1 * scale, (h.x1 - h.x0) * scale, (h.y1 - h.y0) * scale)
            if h.reveal:
                svg.rect(ox + h.x0 * scale, top - h.y1 * scale, (h.x1 - h.x0) * scale, (h.y1 - h.y0) * scale,
                         'fill="none" stroke="#c00" stroke-width="2"')
            if h.name:
                svg.text(ox + (h.x0 + h.x1) / 2 * scale, top - (h.y0 + h.y1) / 2 * scale, h.name, 10, "middle",
                         "#c33")
        for x, m in ((x0, f_.mitre0), (x1, f_.mitre1)):
            if m:
                svg.line(ox + x * scale, y, ox + x * scale, top, 'stroke="#c00" stroke-width="2"')
        if f_.index == start_wall or room.walls[f_.index].tiles.priority is not None:
            cx = ox + (start_x if f_.index == start_wall else f_.target) * scale
            svg.line(cx, y - 4, cx, top + 4, 'stroke="#06c" stroke-dasharray="5 3"')
        y = top + 34
    svg.text(MARGIN, y, "whole tiles pale; cut pieces blue with sizes; too small in red; mitred edges red; "
                        "dashed blue: centre line", 10, colour="#555")
    svg.save(path)
