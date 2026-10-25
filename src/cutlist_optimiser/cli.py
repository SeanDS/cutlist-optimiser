"""Command line entry point: read a TOML room description, print layout and cut list."""

import argparse
import sys
import tomllib

from .solver import Settings, Solver, Wall


def load(path):
    with open(path, "rb") as f:
        data = tomllib.load(f)
    s = Settings()
    for key in ("height", "bottom_gap", "top_gap", "kerf", "joint_gap", "min_piece", "noggin_joints"):
        if key in data:
            setattr(s, key, data[key])
    if "sheet" in data:
        s.sheet = tuple(data["sheet"])
    if s.noggin_joints not in ("prefer", "require", "ignore"):
        raise ValueError("noggin_joints must be 'prefer', 'require' or 'ignore'")
    walls = []
    for i, w in enumerate(data.get("walls", [])):
        walls.append(Wall(w.get("name", f"Wall {i + 1}"), list(w["studs"]),
                          list(w.get("noggins", data.get("noggins", [])))))
    if not walls:
        raise ValueError("no [[walls]] defined")
    return s, walls


def f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def report(s, walls, res, out=sys.stdout):
    p = lambda *a: print(*a, file=out)
    H = s.height - s.bottom_gap - s.top_gap
    p(f"Sheet size {f(max(s.sheet))} x {f(min(s.sheet))} mm, wall height {f(s.height)} mm, "
      f"bottom gap {f(s.bottom_gap)}, top gap {f(s.top_gap)} -> {f(H)} mm to cover")
    p(f"Kerf {f(s.kerf)} mm, joint gap {f(s.joint_gap)} mm (half taken off each side of a joint)")
    p()
    p("WALL LAYOUT  (x from wall start, y from floor; piece labels are wall.column+letter, a = bottom)")
    for wall, cols in zip(walls, res.walls):
        p(f"\n{wall.name}: length {f(wall.positions[-1])} mm, studs at "
          + ", ".join(f(x) for x in wall.positions))
        for col in cols:
            c = col[0]
            p(f"  x {f(c.x0):>6} - {f(c.x1):<6}")
            for pc in col:
                joint = ""
                if pc.joint_on_noggin is not None:
                    joint = f"  joint at {f(pc.y1)}" + (" (on noggin)" if pc.joint_on_noggin else " (NO noggin)")
                p(f"    {pc.label:<6} y {f(pc.y0):>6} - {f(pc.y1):<6}  cut {f(pc.w)} x {f(pc.h)}{joint}")
    p()
    status = "optimal" if len(res.sheets) == res.lower_bound else f"area lower bound {res.lower_bound}"
    p(f"CUT LIST: {len(res.sheets)} sheets ({status})")
    if res.off_noggin and s.noggin_joints != "ignore":
        p(f"  note: {res.off_noggin} horizontal joint(s) not on a noggin - add blocking there")
    for i, sh in enumerate(res.sheets, 1):
        p(f"\nSheet {i}:  (x along the {f(sh.width)} edge, y along the {f(sh.height)} edge)")
        for pl in sorted(sh.placements, key=lambda q: (q.y, q.x)):
            p(f"  {pl.label:<6} {f(pl.w):>6} x {f(pl.h):<6} at x={f(pl.x)}, y={f(pl.y)}")
        offcuts = [r for r in sh.free if min(r[2], r[3]) >= 50]
        if offcuts:
            p("  offcuts: " + ", ".join(f"{f(w)} x {f(h)}" for _, _, w, h in offcuts))


def svg(s, walls, res, path, scale=0.1):
    """Very plain drawing: wall elevations on top, sheets below."""
    parts, y = [], 10
    text = lambda x, y, t, size=12: parts.append(
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-family="sans-serif">{t}</text>')
    for wall, cols in zip(walls, res.walls):
        text(10, y + 12, wall.name, 14)
        y += 20
        top = y + s.height * scale
        parts.append(f'<rect x="10" y="{y}" width="{wall.positions[-1] * scale:.1f}" '
                     f'height="{s.height * scale:.1f}" fill="#eee" stroke="#999"/>')
        for x in wall.positions:
            parts.append(f'<line x1="{10 + x * scale:.1f}" y1="{y}" x2="{10 + x * scale:.1f}" '
                         f'y2="{top:.1f}" stroke="#c96" stroke-width="2"/>')
        for n in wall.noggins:
            parts.append(f'<line x1="10" y1="{top - n * scale:.1f}" x2="{10 + wall.positions[-1] * scale:.1f}" '
                         f'y2="{top - n * scale:.1f}" stroke="#c96" stroke-dasharray="4"/>')
        for col in cols:
            for pc in col:
                px, py = 10 + pc.x0 * scale, top - pc.y1 * scale
                parts.append(f'<rect x="{px:.1f}" y="{py:.1f}" width="{(pc.x1 - pc.x0) * scale:.1f}" '
                             f'height="{(pc.y1 - pc.y0) * scale:.1f}" fill="#9bd" fill-opacity="0.6" stroke="#000"/>')
                text(px + 4, py + 14, pc.label)
        y = top + 30
    for i, sh in enumerate(res.sheets):
        bx, by = 10 + (i % 4) * (sh.width * scale + 20), y + (i // 4) * (sh.height * scale + 40)
        text(bx, by + 12, f"Sheet {i + 1}", 14)
        by += 20
        parts.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{sh.width * scale:.1f}" '
                     f'height="{sh.height * scale:.1f}" fill="#ddd" stroke="#000"/>')
        for pl in sh.placements:
            parts.append(f'<rect x="{bx + pl.x * scale:.1f}" y="{by + pl.y * scale:.1f}" width="{pl.w * scale:.1f}" '
                         f'height="{pl.h * scale:.1f}" fill="#9bd" stroke="#000"/>')
            text(bx + pl.x * scale + 3, by + pl.y * scale + 13, f"{pl.label} {f(pl.w)}x{f(pl.h)}", 10)
    rows = (len(res.sheets) + 3) // 4
    height = y + rows * (max(s.sheet) * scale + 40) + 10
    width = max([w.positions[-1] * scale + 20 for w in walls] + [4 * (max(s.sheet) * scale + 20) + 10])
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
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--svg", metavar="FILE", help="also write a drawing of the layout and sheets")
    args = ap.parse_args(argv)
    try:
        s, walls = load(args.config)
        progress = progress_bar if sys.stderr.isatty() else None
        res = Solver(s, walls, args.seed).solve(args.iterations, progress)
    except (ValueError, KeyError, OSError, tomllib.TOMLDecodeError) as e:
        sys.exit(f"error: {e}")
    report(s, walls, res)
    if args.svg:
        svg(s, walls, res, args.svg)
        print(f"\nDrawing written to {args.svg}")


if __name__ == "__main__":
    main()
