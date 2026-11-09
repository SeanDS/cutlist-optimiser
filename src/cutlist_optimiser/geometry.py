"""Where each layer ends at a corner, relative to the bare framing.

All offsets are outward from the framing corner line at that end of the wall:
positive runs past it, negative stops short of it.

At an inside corner the wall that runs through takes its sheets to the corner
line; the other wall's sheets butt against them, so its sheets stop short by the
sheet thickness.  The boarded face of both walls then ends at the other wall's
boarded face.  Tiles work the same way one layer further out.

At an outside corner the wall that runs through covers the other wall's edge.
Tiles are mitred there by default, so both walls' tiles run to the arris.
"""


def sheet_offset(corner, through, thickness):
    """How far this wall's sheets run past the framing corner line."""
    if corner.type == "inside":
        return 0.0 if through else -thickness
    if corner.type == "outside":
        return thickness if through else 0.0
    return 0.0


def face_offset(corner, thickness):
    """How far this wall's boarded face runs past the framing corner line (to the inside face or arris)."""
    if corner.type == "inside":
        return -thickness
    if corner.type == "outside":
        return thickness
    return 0.0


def tile_offset(corner, through, tile_thickness, outside_corners):
    """How far this wall's tiles run past its boarded face end."""
    if corner.type == "inside":
        return 0.0 if through else -tile_thickness
    if corner.type == "outside":
        if outside_corners == "mitre" or (outside_corners == "overlap" and through):
            return tile_thickness
        return 0.0
    return 0.0


def describe(corner, through):
    if corner.type == "open":
        return "open end"
    who = "runs through" if through else "butts against the other wall"
    return f"{corner.type} corner, this wall {who}"


def boarded_start(room, wi):
    """Framing x of the boarded face's start corner (inside face or arris) on wall wi."""
    corner, _ = room.start_corner(wi)
    return -face_offset(corner, room.sheets.thickness)


def framing_x(room, wi, x):
    """Convert an x position on wall wi, as measured in the input, to framing coordinates."""
    if room.walls[wi].measured_from == "boarded":
        return x + boarded_start(room, wi)
    return x
