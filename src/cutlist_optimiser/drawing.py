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
