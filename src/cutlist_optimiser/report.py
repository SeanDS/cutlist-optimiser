"""Text reports of the results, printed to stdout."""

import click

from .console import em, heading
from .geometry import describe


def f(v):
    """A length in mm without needless decimals."""
    return f"{v:.1f}".rstrip("0").rstrip(".")


def m2(area):
    return f"{area / 1e6:.2f} m²"


def note(text):
    return click.style(text, fg="yellow")


def good(text):
    return click.style(text, fg="green")


def sheets_report(solver, res, seed):
    p = click.echo
    room, s = solver.room, solver.s
    H = room.height - s.bottom_gap - s.top_gap
    p(f"Sheet size {em(f(max(s.size)) + ' x ' + f(min(s.size)))} mm, {f(s.thickness)} mm thick; "
      f"wall height {f(room.height)} mm, bottom gap {f(s.bottom_gap)}, top gap {f(s.top_gap)} "
      f"-> {em(f(H))} mm to cover")
    p(f"Kerf {f(s.kerf)} mm, joint gap {f(s.joint_gap)} mm (half taken off each side of a joint)")
    if s.stagger:
        p(f"Staggering horizontal joints in neighbouring columns by at least {em(f(s.stagger))} mm")
    p(f"Random seed {em(seed)}")
    p()
    p(heading("WALL LAYOUT") + "  (x from the framing corner at the wall start, y from the floor; "
                               "piece labels are wall.column+letter, a = bottom)")
    for wi, (wall, cols) in enumerate(zip(room.walls, res.walls)):
        pos = solver.positions[wi]
        p(f"\n{em(wall.name)}: framing length {f(wall.length)} mm, studs at " + ", ".join(f(x) for x in pos))
        for side, (corner, through) in (("start", room.start_corner(wi)), ("end", room.end_corner(wi))):
            ext = solver.ends[wi][0 if side == "start" else 1]
            if ext:
                how = f"run {f(ext)} mm past" if ext > 0 else f"stop {f(-ext)} mm short of"
                p(f"  {side}: {describe(corner, through)}; sheets {how} the framing")
        for o, rect in zip([o for o in wall.stay_out if o.applies("sheets")], solver.stay_out[wi]):
            name = f" {o.name}" if o.name else ""
            p(f"  stay out{name}: x {f(rect[0])} - {f(rect[1])}, y {f(rect[2])} - {f(rect[3])}")
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
                        support = good("on noggin")
                    elif ok == 0:
                        support = note("NO noggin")
                    else:
                        support = note(f"on noggin in {ok} of {bays} bays")
                    joint = f"  joint at {f(pc.y1)} ({support})"
                p(f"    {em(f'{pc.label:<6}')} y {f(pc.y0):>6} - {f(pc.y1):<6}  cut {f(pc.w)} x {f(pc.h)}{joint}")
    p()
    status = good("optimal") if len(res.sheets) == res.lower_bound else f"area lower bound {res.lower_bound}"
    p(f"{heading('CUT LIST')}: {em(len(res.sheets))} sheets ({status})")
    waste = res.sheet_area - res.used_area
    p(f"  utilisation: {m2(res.used_area)} of {m2(res.sheet_area)} used in pieces ({em(f'{res.utilisation:.1%}')}), "
      f"{m2(waste)} wasted as offcuts and kerf ({1 - res.utilisation:.1%})")
    p(f"  cuts: {em(res.cuts)} in total")
    if res.off_noggin and s.noggin_joints != "ignore":
        p(note(f"  note: {res.off_noggin} place(s) where a horizontal joint crosses a bay with no noggin "
               f"- add blocking there"))
    if res.aligned:
        p(note(f"  note: {res.aligned} pair(s) of joints in neighbouring columns are less than "
               f"{f(s.stagger)} mm apart"))
    for i, sh in enumerate(res.sheets, 1):
        p(f"\n{em(f'Sheet {i}')}:  {sh.used_area / sh.area:.1%} used, {len(sh.cuts)} cut"
          f"{'' if len(sh.cuts) == 1 else 's'}  (x along the {f(sh.width)} edge, y along the {f(sh.height)} edge)")
        for pl in sorted(sh.placements, key=lambda q: (q.y, q.x)):
            p(f"  {pl.label:<6} {f(pl.w):>6} x {f(pl.h):<6} at x={f(pl.x)}, y={f(pl.y)}")
        offcuts = [r for r in sh.free if min(r[2], r[3]) >= 50]
        if offcuts:
            p("  offcuts: " + ", ".join(f"{f(w)} x {f(h)}" for _, _, w, h in offcuts))
