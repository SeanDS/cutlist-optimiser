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


def _rows_text(parity_rows):
    rows = ", ".join(str(r) for r in parity_rows[:3])
    return f"rows {rows}{', ...' if len(parity_rows) > 3 else ''}"


def tiles_report(tiler, res):
    import math

    from .tiles import TOL, mod_dist

    p = click.echo
    room, t = tiler.room, tiler.t
    tw, th, g = tiler.tw, tiler.th, res.grout
    px, py = tiler.pitch(g)
    pattern = "grid" if t.pattern == "grid" else f"brick, {t.offset:g} offset"
    chosen = f" (chosen from {', '.join(f(o) for o in t.grout_options)})" if len(t.grout_options) > 1 else ""
    p(f"Tiles {em(f(tw) + ' x ' + f(th))} mm, {f(t.thickness)} mm with adhesive; {pattern}; "
      f"grout {em(f(g) + ' mm')}{chosen}")
    p(f"Smallest cut piece {f(t.min_cut)} mm, smallest mitred piece {f(t.min_mitre)} mm; kerf {f(t.kerf)} mm; "
      f"tiles {'may' if t.rotate else 'may not'} be turned when cutting")

    p()
    p(heading("PRIORITIES") + " (as understood, most important first)")
    for goal in res.goals:
        if goal.deviation < 0.05:
            result = good("exact")
        else:
            result = note(f"{goal.deviation:.1f} mm off ({goal.closeness:.0%})")
        extra = click.style(f"  [{goal.note}]", dim=True) if goal.note else ""
        p(f"  {goal.label:<11} {goal.describe:<58} {result}{extra}")
        if goal.why:
            p(click.style(f"  {'':<11} why: {goal.why}", fg="yellow", dim=True))
    p(f"  {'grout':<11} {f(g)} mm" + (f", the width that best met the goals above{chosen}" if chosen else ""))
    names = [w.name for w in room.walls]
    for i, kind in res.corners:
        a, b = names[i], names[(i + 1) % len(names)]
        text = {"continue": "pattern continues round the corner", "fresh": "pattern restarts (fresh)",
                "seam": note("seam: pattern restarts here"), "open": "open end"}[kind]
        p(f"  {'corner':<11} {a} / {b}: {text}")
    if res.seam_reason:
        p(f"  {'':<11} {click.style(res.seam_reason, dim=True)}")

    p()
    p(heading("FINISHED SIZES") + " (x from the corner at each wall's start, y from the floor)")
    for f_ in tiler.faces:
        wall = room.walls[f_.index]
        framing = f"framing {f(wall.length)} mm, " if wall.length is not None else ""
        source = "measured" if f_.measured else "calculated"
        p(f"  {em(f_.name)}: {framing}boarded face {em(f(f_.b1 - f_.b0))} mm ({source}), "
          f"tiled face {em(f(f_.c1 - f_.c0))} mm")
        if not f_.measured:
            p(click.style(f"    to check: measure the boarded face corner to corner (into the corners, before "
                          f"tiling) at about 1 m high; expect {f(f_.b1 - f_.b0)} mm, or put the measurement in "
                          f"measured_length", dim=True))
        for h in f_.holes:
            reveal = f", reveal tiles {f(h.reveal)} mm wide, mitred" if h.reveal else ", no tiled reveal"
            p(f"    {h.name or 'opening'}: finished opening {f(h.x1 - h.x0)} x {f(h.y1 - h.y0)} mm, "
              f"sill at {f(h.y0)}, head at {f(h.y1)}{reveal}")

    p()
    p(heading("SETTING OUT"))
    rows = tiler.rows(g, res.v)
    k0 = rows[0][0]
    p(f"  {len(rows)} rows. Lowest row: {f(rows[0][2] - rows[0][1])} mm tall from {f(rows[0][1])} mm; "
      f"top row: {f(rows[-1][2] - rows[-1][1])} mm tall up to {f(rows[-1][2])} mm")
    level = next((r for r in rows if r[4] <= rows[-1][2] and r[3] >= rows[0][1]), rows[0])
    p(f"  Level line: bottom of row {level[0] - k0 + 1} at {em(f(level[3]))} mm above the floor "
      f"(rows every {f(py)} mm)")
    for f_, u in zip(tiler.faces, res.u):
        x0, x1 = tiler.extent(f_, g)
        p(f"  {em(f_.name)} (x measured from its boarded start corner):")
        for parity in (k0, k0 + 1) if t.pattern == "brick" else (k0,):
            ks = [k for k, *_ in rows if (k - parity) % 2 == 0]
            if not ks:
                continue
            start = u + tiler.shift(ks[0], px)
            first_tile = start + math.floor((x0 - start) / px) * px
            first = min(tw, first_tile + tw - x0) if first_tile + tw > x0 + TOL else tw
            last_tile = start + math.floor((x1 - start) / px) * px
            last = min(tw, x1 - last_tile)
            centred = "tile" if mod_dist(f_.target - (start + tw / 2), px) < TOL else (
                "joint" if mod_dist(f_.target - (start + tw + g / 2), px) < TOL else None)
            at = f"; a {centred} is centred on the {f_.target_name}" if centred else ""
            joint = start + math.ceil((x0 - start + TOL) / px) * px - g / 2  # first joint inside the wall
            p(f"    {_rows_text([k - k0 + 1 for k in ks])}: first piece {em(f(first))} mm, last piece "
              f"{em(f(last))} mm, first vertical joint centred at {f(joint - f_.b0)} mm{at}")

    p()
    p(heading("TILES"))
    pieces = res.cut_pieces
    area = res.full * tw * th + sum(pc.area for pc in pieces)
    stock = res.count * tw * th
    order = math.ceil(res.count * (1 + t.spare / 100))
    p(f"  tiles needed: {em(res.count)} ({res.full} whole, {len(res.tiles)} cut into {len(pieces)} pieces); "
      f"order {em(order)} with {f(t.spare)}% spare")
    p(f"  efficiency: {m2(area)} tiled from {m2(stock)} of tiles ({em(f'{area / stock:.1%}')}), "
      f"{m2(stock - area)} wasted as offcuts and kerf")
    straight = sum(len(s.cuts) for s in res.tiles)
    notches = sum(pc.notches for pc in pieces)
    mitres = sum(pc.mitres for pc in pieces)
    p(f"  cuts: {em(straight + 2 * notches)} ({straight} straight cuts"
      + (f", {notches} notch{'es' if notches != 1 else ''} at 2 cuts each" if notches else "")
      + f"), plus {em(mitres)} mitred edge{'s' if mitres != 1 else ''}")
    problems = res.problems
    if problems:
        p(note(f"  {len(problems)} piece(s) are below the minimum size:"))
        for pc, what, _ in problems[:12]:
            where = pc.where or f"{tiler.faces[pc.wall].name} row {pc.row + 1}"
            p(note(f"    {where} at x {f(pc.x0 - tiler.faces[pc.wall].b0)}: {what}"))
        if len(problems) > 12:
            p(note(f"    ... and {len(problems) - 12} more"))
        p(note("  to fix: try other grout_options, another offset or pattern, a different start feature or "
               "tile size, a fresh corner, or a smaller min_cut"))

    p()
    p(heading("CUT LIST") + " (each line: how many tiles, and the pieces cut from each)")
    groups = {}
    for s in res.tiles:
        key = tuple(sorted(((round(pl.w, 1), round(pl.h, 1), bool(pieces[int(pl.label)].mitres),
                             bool(pieces[int(pl.label)].notches)) for pl in s.placements), reverse=True))
        groups.setdefault(key, []).append(s)
    for key, tiles in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        parts = " + ".join(f"{f(w)} x {f(h)}" + (" notched" if nt else "") + (" (mitred)" if m else "")
                           for w, h, m, nt in key)
        cuts = len(tiles[0].cuts) + 2 * sum(nt for *_, nt in key)
        p(f"  {em(f'{len(tiles):>3} x')}  {parts}  ({cuts} cut{'s' if cuts != 1 else ''})")
