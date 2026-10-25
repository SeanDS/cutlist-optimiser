"""Command line entry point: read a TOML room description, print layout and cut list."""

import argparse
import sys
import tomllib

from .solver import Settings, Solver, Wall


def load(path):
    with open(path, "rb") as f:
        data = tomllib.load(f)
    s = Settings()
    if "noggins" in data:
        raise ValueError("noggins must be set per wall, as one list of heights per stud bay")
    for key in ("height", "bottom_gap", "top_gap", "kerf", "joint_gap", "min_piece", "noggin_joints",
                "noggin_tolerance"):
        if key in data:
            setattr(s, key, data[key])
    if "sheet" in data:
        s.sheet = tuple(data["sheet"])
    if s.noggin_joints not in ("prefer", "require", "ignore"):
        raise ValueError("noggin_joints must be 'prefer', 'require' or 'ignore'")
    walls = []
    for i, w in enumerate(data.get("walls", [])):
        stay_out = [(*a["x"], *a["y"]) for a in w.get("stay_out", [])]
        walls.append(Wall(w.get("name", f"Wall {i + 1}"), list(w["studs"]),
                          list(w.get("noggins", [])), stay_out))
    if not walls:
        raise ValueError("no [[walls]] defined")
    return s, walls


def f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def report(s, walls, res, seed, out=sys.stdout):
    p = lambda *a: print(*a, file=out)
    H = s.height - s.bottom_gap - s.top_gap
    p(f"Sheet size {f(max(s.sheet))} x {f(min(s.sheet))} mm, wall height {f(s.height)} mm, "
      f"bottom gap {f(s.bottom_gap)}, top gap {f(s.top_gap)} -> {f(H)} mm to cover")
    p(f"Kerf {f(s.kerf)} mm, joint gap {f(s.joint_gap)} mm (half taken off each side of a joint)")
    p(f"Random seed {seed}")
    p()
    p("WALL LAYOUT  (x from wall start, y from floor; piece labels are wall.column+letter, a = bottom)")
    for wall, cols in zip(walls, res.walls):
        p(f"\n{wall.name}: length {f(wall.positions[-1])} mm, studs at "
          + ", ".join(f(x) for x in wall.positions))
        for x0, x1, y0, y1 in wall.stay_out:
            p(f"  stay out: x {f(x0)} - {f(x1)}, y {f(y0)} - {f(y1)}")
        for col in cols:
            if not col:
                continue
            c = col[0]
            p(f"  x {f(c.x0):>6} - {f(c.x1):<6}")
            for pc in col:
                joint = ""
                if pc.joint_support is not None:
                    ok, bays = pc.joint_support
                    if ok == bays:
                        support = "on noggin"
                    elif ok == 0:
                        support = "NO noggin"
                    else:
                        support = f"on noggin in {ok} of {bays} bays"
                    joint = f"  joint at {f(pc.y1)} ({support})"
                p(f"    {pc.label:<6} y {f(pc.y0):>6} - {f(pc.y1):<6}  cut {f(pc.w)} x {f(pc.h)}{joint}")
    p()
    status = "optimal" if len(res.sheets) == res.lower_bound else f"area lower bound {res.lower_bound}"
    p(f"CUT LIST: {len(res.sheets)} sheets ({status})")
    m2 = lambda a: f"{a / 1e6:.2f} m²"
    waste = res.sheet_area - res.used_area
    p(f"  utilisation: {m2(res.used_area)} of {m2(res.sheet_area)} used in pieces ({res.utilisation:.1%}), "
      f"{m2(waste)} wasted as offcuts and kerf ({1 - res.utilisation:.1%})")
    if res.off_noggin and s.noggin_joints != "ignore":
        p(f"  note: {res.off_noggin} place(s) where a horizontal joint crosses a bay with no noggin "
          f"- add blocking there")
    for i, sh in enumerate(res.sheets, 1):
        p(f"\nSheet {i}:  {sh.used_area / sh.area:.1%} used  "
          f"(x along the {f(sh.width)} edge, y along the {f(sh.height)} edge)")
        for pl in sorted(sh.placements, key=lambda q: (q.y, q.x)):
            p(f"  {pl.label:<6} {f(pl.w):>6} x {f(pl.h):<6} at x={f(pl.x)}, y={f(pl.y)}")
        offcuts = [r for r in sh.free if min(r[2], r[3]) >= 50]
        if offcuts:
            p("  offcuts: " + ", ".join(f"{f(w)} x {f(h)}" for _, _, w, h in offcuts))


def svg(s, walls, res, path, scale=0.1, sheet_scale=0.25, per_row=3):
    """Plain drawing: wall elevations on top, then each sheet with its cut lines."""
    parts, y = [], 10

    def text(x, y, t, size=12, anchor="start", colour="#000", bold=False):
        weight = ' font-weight="bold"' if bold else ""
        parts.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-family="sans-serif" '
                     f'text-anchor="{anchor}" fill="{colour}"{weight}>{t}</text>')

    def rect(x, y, w, h, style):
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" {style}/>')

    def line(x0, y0, x1, y1, style):
        parts.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" {style}/>')

    for wall, cols in zip(walls, res.walls):
        text(10, y + 12, wall.name, 14)
        y += 20
        top = y + s.height * scale
        length = wall.positions[-1] * scale
        rect(10, y, length, s.height * scale, 'fill="#eee" stroke="#999"')
        # framing drawn over the pieces so it shows through
        for col in cols:
            for pc in col:
                px, py = 10 + pc.x0 * scale, top - pc.y1 * scale
                rect(px, py, (pc.x1 - pc.x0) * scale, (pc.y1 - pc.y0) * scale,
                     'fill="#9bd" fill-opacity="0.6" stroke="#000"')
                if (pc.y1 - pc.y0) * scale >= 16:
                    text(px + 4, py + 14, pc.label)
        for x in wall.positions:
            line(10 + x * scale, y, 10 + x * scale, top, 'stroke="#a0522d" stroke-width="1.5" stroke-opacity="0.7"')
        for x0, x1, bay in zip(wall.positions, wall.positions[1:], wall.noggins):
            for n in bay:
                line(10 + x0 * scale, top - n * scale, 10 + x1 * scale, top - n * scale,
                     'stroke="#a0522d" stroke-width="3"')
        for x0, x1, y0, y1 in wall.stay_out:
            y1 = min(y1, s.height)
            sx, sy, sw, sh = 10 + x0 * scale, top - y1 * scale, (x1 - x0) * scale, (y1 - y0) * scale
            rect(sx, sy, sw, sh, 'fill="#fff" stroke="#c33"')
            line(sx, sy, sx + sw, sy + sh, 'stroke="#c33"')
            line(sx, sy + sh, sx + sw, sy, 'stroke="#c33"')
        y = top + 30

    # sheets: the whole uncut sheet, offcuts hatched, cut lines dashed and numbered in cutting order
    parts.append('<defs><pattern id="waste" width="8" height="8" patternUnits="userSpaceOnUse" '
                 'patternTransform="rotate(45)"><rect width="8" height="8" fill="#ddd"/>'
                 '<line x1="0" y1="0" x2="0" y2="8" stroke="#999" stroke-width="3"/></pattern></defs>')
    L, S = max(s.sheet), min(s.sheet)
    cell_w, cell_h = L * sheet_scale + 30, S * sheet_scale + 40
    for i, sh in enumerate(res.sheets):
        bx, by = 10 + (i % per_row) * cell_w, y + (i // per_row) * cell_h
        text(bx, by + 12, f"Sheet {i + 1}  ({sh.used_area / sh.area:.1%} used)", 14, bold=True)
        by += 20
        rect(bx, by, sh.width * sheet_scale, sh.height * sheet_scale, 'fill="#f4ead2"')
        for fx, fy, fw, fh in sh.free:
            rect(bx + fx * sheet_scale, by + fy * sheet_scale, fw * sheet_scale, fh * sheet_scale,
                 'fill="url(#waste)"')
        for pl in sh.placements:
            cx, cy = bx + (pl.x + pl.w / 2) * sheet_scale, by + (pl.y + pl.h / 2) * sheet_scale
            size = 12 if min(pl.w, pl.h) * sheet_scale > 40 else 9
            text(cx, cy - 2, pl.label, size, "middle", bold=True)
            text(cx, cy + size, f"{f(pl.w)} x {f(pl.h)}", size - 2, "middle")
        for n, (x0, y0, x1, y1) in enumerate(sh.cuts, 1):
            line(bx + x0 * sheet_scale, by + y0 * sheet_scale, bx + x1 * sheet_scale, by + y1 * sheet_scale,
                 'stroke="#c00" stroke-width="1.5" stroke-dasharray="6 3"')
            mx, my = bx + (x0 + x1) / 2 * sheet_scale, by + (y0 + y1) / 2 * sheet_scale
            parts.append(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="7" fill="#c00"/>')
            text(mx, my + 3.5, n, 9, "middle", "#fff", bold=True)
        rect(bx, by, sh.width * sheet_scale, sh.height * sheet_scale, 'fill="none" stroke="#000" stroke-width="1.5"')
    rows = (len(res.sheets) + per_row - 1) // per_row
    height = y + rows * cell_h + 10
    width = max([w.positions[-1] * scale + 20 for w in walls] + [per_row * cell_w + 10])
    with open(path, "w") as fh:
        fh.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}">'
                 f'<rect width="100%" height="100%" fill="#fff"/>{"".join(parts)}</svg>\n')


def progress_bar(done, total, best, width=30):
    """Draw a one-line progress bar on stderr, redrawn about once per percent."""
    if done != total and done % max(1, total // 100):
        return
    filled = width * done // max(total, 1)
    end = "\n" if done == total else ""
    print(f"\rSearching [{'#' * filled}{'.' * (width - filled)}] {done}/{total}  best: {best} sheets",
          end=end, file=sys.stderr, flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cutlist Optimiser: sheet material layout and cut list for stud walls")
    ap.add_argument("config", help="TOML file describing walls (see example.toml)")
    ap.add_argument("-n", "--iterations", type=int, default=3000, help="search iterations (default 3000)")
    ap.add_argument("--seed", type=int, default=0, help="random seed for the search (default 0)")
    ap.add_argument("--svg", metavar="FILE", help="also write a drawing of the layout and sheets")
    args = ap.parse_args(argv)
    try:
        s, walls = load(args.config)
        progress = progress_bar if sys.stderr.isatty() else None
        res = Solver(s, walls, args.seed).solve(args.iterations, progress)
    except (ValueError, KeyError, OSError, tomllib.TOMLDecodeError) as e:
        sys.exit(f"error: {e}")
    report(s, walls, res, args.seed)
    if args.svg:
        svg(s, walls, res, args.svg)
        print(f"\nDrawing written to {args.svg}")


if __name__ == "__main__":
    main()
