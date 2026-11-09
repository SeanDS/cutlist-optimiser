"""The room description: loading and checking the TOML input file.

One file describes the room for both modes.  Everything is measured in mm from
the bare framing: x from the corner at the start of each wall, y from the floor.
"""

import tomllib
from dataclasses import dataclass, field

EPS = 1e-6
MISSING = object()


class ConfigError(Exception):
    """A problem with the input file, with where it is and how to fix it."""

    def __init__(self, where, problem, fix=None):
        self.where, self.problem, self.fix = where, problem, fix
        super().__init__(f"{where}: {problem}" if where else problem)


# --- data ---------------------------------------------------------------------

@dataclass
class Corner:
    type: str = "open"  # inside | outside | open
    through: str | None = None  # which wall's layers run to the corner line: this | next
    tiles: str = "continue"  # continue | fresh: whether the tile pattern carries on round the corner


@dataclass
class Opening:
    """A stay-out area: a window, door, bath or anything else left uncovered."""
    name: str | None
    x: tuple  # in the wall's measured_from coordinates as given; see Wall.framing_x
    y: tuple
    only: str | None  # sheets | tiles | None (both)
    reveal: float | None  # depth of a tiled reveal (boarded face to frame); None = no tiled reveal
    reveal_given: bool
    where: str

    def applies(self, mode):
        return self.only in (None, mode)


@dataclass
class WallTiles:
    priority: int | None = None
    centre_on: str | float | None = None  # an opening name or an x position


@dataclass
class Wall:
    name: str
    index: int
    length: float | None  # bare framing, corner to corner
    measured_length: float | None  # boarded face, corner to corner, before tiling
    measured_from: str  # framing | boarded: where stay-out x positions are measured from
    studs: list  # stud centre positions from the wall start, end studs implied
    noggins: list  # one list of noggin centre heights per stud bay
    corner: Corner  # the corner between this wall and the next
    tiles: WallTiles
    stay_out: list
    where: str


@dataclass
class SheetSettings:
    size: tuple = (1200, 800)
    thickness: float = 12
    kerf: float = 3
    joint_gap: float = 3
    bottom_gap: float = 2
    top_gap: float = 0
    min_piece: float = 100
    noggin_joints: str = "prefer"  # prefer | require | ignore
    noggin_tolerance: float = 10
    stagger: float = 0  # set from the command line


@dataclass
class TileSettings:
    size: tuple  # width x height as laid
    thickness: float  # tile + adhesive
    grout: float  # nominal joint width
    grout_options: list  # widths the search may use, nominal included
    kerf: float = 2
    pattern: str = "grid"  # grid | brick
    offset: float = 0.5  # brick offset as a fraction of the tile width
    min_cut: float = 50
    min_mitre: float = 50
    rotate: bool = False
    bottom_gap: float = 0
    top_gap: float = 0
    outside_corners: str = "mitre"  # mitre | overlap | trim
    start: str | None = None  # wall or wall.opening the layout is set out from
    start_align: str = "either"  # tile (centred) | joint (half-centred) | either
    rows: list = field(default_factory=lambda: ["floor"])
    spare: float = 10  # percent extra to order


@dataclass
class Room:
    height: float
    closed: bool
    walls: list
    sheets: SheetSettings | None
    tiles: TileSettings | None
    source: str = ""

    def start_corner(self, i):
        """The corner at the start of wall i, and whether wall i runs through it."""
        if i == 0 and not self.closed:
            return Corner(), False
        c = self.walls[i - 1].corner
        return c, c.through == "next"

    def end_corner(self, i):
        """The corner at the end of wall i, and whether wall i runs through it."""
        c = self.walls[i].corner
        return c, c.through == "this"

    def next_wall(self, i):
        if i + 1 < len(self.walls):
            return self.walls[i + 1]
        return self.walls[0] if self.closed else None

    def wall(self, name, where):
        for w in self.walls:
            if w.name == name:
                return w
        raise ConfigError(where, f"there is no wall called {name!r}",
                          f"use one of: {', '.join(w.name for w in self.walls)}")

    def opening(self, ref, where):
        """Find 'Wall.opening' and return (wall, opening)."""
        if "." not in ref:
            raise ConfigError(where, f"{ref!r} does not name an opening",
                              "write it as WALL.OPENING, e.g. \"South.window\"")
        wall_name, name = ref.split(".", 1)
        wall = self.wall(wall_name, where)
        for o in wall.stay_out:
            if o.name == name:
                return wall, o
        names = [o.name for o in wall.stay_out if o.name]
        raise ConfigError(where, f"wall {wall.name!r} has no stay-out area called {name!r}",
                          f"use one of: {', '.join(names)}" if names else
                          f"give the area a name, e.g. name = \"{name}\", in walls.{wall.name}.stay_out")

    # --- per-mode checks -------------------------------------------------

    def require_sheets(self):
        if self.sheets is None:
            raise ConfigError(None, "the file has no [sheets] section",
                              "add a [sheets] section with at least the sheet size and thickness")
        for w in self.walls:
            if w.length is None:
                raise ConfigError(w.where, "sheet mode needs the bare framing length of every wall",
                                  "add length = ... (corner to corner, measured on the studs)")

    def require_tiles(self):
        if self.tiles is None:
            raise ConfigError(None, "the file has no [tiles] section",
                              "add a [tiles] section with at least size, thickness and grout")
        if self.sheets is None:
            raise ConfigError(None, "tile mode needs the sheet thickness to work out finished sizes",
                              "add a [sheets] section with thickness = ... (the sheets under the tiles)")
        t = self.tiles
        for w in self.walls:
            for o in w.stay_out:
                if o.applies("tiles") and not o.reveal_given:
                    raise ConfigError(o.where, "tile mode needs to know whether this area has tiled reveals",
                                      "add reveal = { depth = ... } (boarded face to window frame) "
                                      "or reveal = \"none\"")
            if w.tiles.centre_on is not None and isinstance(w.tiles.centre_on, str):
                self.opening(f"{w.name}.{w.tiles.centre_on}", f"{w.where}.tiles.centre_on")
        if t.start is not None:
            if "." in t.start:
                self.opening(t.start, "tiles.start")
            else:
                self.wall(t.start, "tiles.start")
        for i, ref in enumerate(t.rows):
            where = f"tiles.rows[{i}]"
            if ref in ("floor", "ceiling"):
                continue
            parts = ref.rsplit(".", 1)
            if len(parts) != 2 or parts[1] not in EDGES:
                raise ConfigError(where, f"{ref!r} is not a row goal",
                                  "use \"floor\", \"ceiling\" or WALL.OPENING.EDGE with EDGE one of "
                                  + ", ".join(EDGES))
            self.opening(parts[0], where)


EDGES = {"sill": "bottom", "bottom": "bottom", "head": "top", "top": "top"}


# --- reading --------------------------------------------------------------------

class _Table:
    """A TOML table with its location, typed getters and a check for unknown keys."""

    def __init__(self, data, where, allowed, hint=None):
        if not isinstance(data, dict):
            raise ConfigError(where, "must be a table", "write it as KEY = VALUE lines under a [section] "
                                                        "or as { key = value, ... }")
        unknown = sorted(set(data) - set(allowed))
        if unknown:
            raise ConfigError(where, f"unknown setting{'s' if len(unknown) > 1 else ''} "
                                     f"{', '.join(unknown)}",
                              hint or f"settings allowed here: {', '.join(allowed)}")
        self.data, self.where = data, where

    def at(self, key):
        return f"{self.where}.{key}" if self.where else key

    def raw(self, key, default=MISSING):
        if key in self.data:
            return self.data[key]
        if default is MISSING:
            raise ConfigError(self.where or None, f"{key} is required", f"add {key} = ...")
        return default

    def number(self, key, default=MISSING, minimum=None, positive=False):
        v = self.raw(key, default)
        if v is None or (v is default and default is not MISSING):
            return v
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ConfigError(self.at(key), f"must be a number, not {v!r}", f"write it as {key} = 123 (in mm)")
        if positive and v <= 0:
            raise ConfigError(self.at(key), f"must be greater than 0, not {v:g}", "use a positive size in mm")
        if minimum is not None and v < minimum:
            raise ConfigError(self.at(key), f"must be at least {minimum:g}, not {v:g}",
                              f"use {minimum:g} or more")
        return float(v)

    def string(self, key, default=MISSING, choices=None):
        v = self.raw(key, default)
        if v is None or (v is default and default is not MISSING):
            return v
        if not isinstance(v, str):
            raise ConfigError(self.at(key), f"must be text in quotes, not {v!r}")
        if choices and v not in choices:
            raise ConfigError(self.at(key), f"{v!r} is not allowed", f"use one of: {', '.join(choices)}")
        return v

    def boolean(self, key, default=MISSING):
        v = self.raw(key, default)
        if not isinstance(v, bool):
            raise ConfigError(self.at(key), f"must be true or false, not {v!r}")
        return v

    def numbers(self, key, default=MISSING, positive=False):
        v = self.raw(key, default)
        if v is default and default is not MISSING:
            return v
        if not isinstance(v, list) or any(isinstance(n, bool) or not isinstance(n, (int, float)) for n in v):
            raise ConfigError(self.at(key), f"must be a list of numbers, e.g. [1, 2], not {v!r}")
        if positive and any(n <= 0 for n in v):
            raise ConfigError(self.at(key), "all values must be greater than 0")
        return [float(n) for n in v]

    def pair(self, key, default=MISSING, increasing=False, positive=False):
        v = self.numbers(key, default, positive=positive)
        if v is default and default is not MISSING:
            return v
        if len(v) != 2:
            raise ConfigError(self.at(key), f"must have exactly two values, e.g. [600, 300], not {len(v)}")
        if increasing and v[0] >= v[1]:
            raise ConfigError(self.at(key), f"must be [from, to] with from < to, not [{v[0]:g}, {v[1]:g}]")
        return tuple(v)


TOP = ("height", "closed", "sheets", "tiles", "walls")
SHEETS = ("size", "thickness", "kerf", "joint_gap", "bottom_gap", "top_gap", "min_piece",
          "noggin_joints", "noggin_tolerance")
TILES = ("size", "thickness", "grout", "grout_options", "kerf", "pattern", "offset", "min_cut", "min_mitre",
         "rotate", "bottom_gap", "top_gap", "outside_corners", "start", "start_align", "rows", "spare")
WALL = ("name", "length", "measured_length", "measured_from", "studs", "noggins", "corner", "tiles", "stay_out")


def load(path):
    try:
        with open(path, "rb") as fh:
            text = fh.read().decode()
    except OSError as e:
        raise ConfigError(None, f"cannot read {path}: {e.strerror}", "check the file name and path") from e
    return loads(text, str(path))


def loads(text, source="<string>"):
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(source, f"is not valid TOML: {e}", "fix the syntax at the line and column given") from e
    top = _Table(data, "", TOP, "top-level settings are height and closed; sheet settings go in [sheets], "
                                "tile settings in [tiles] and each wall in a [[walls]] entry")
    height = top.number("height", positive=True)
    closed = top.boolean("closed", True)
    sheets = _sheets(_Table(data["sheets"], "sheets", SHEETS)) if "sheets" in data else None
    tiles = _tiles(_Table(data["tiles"], "tiles", TILES)) if "tiles" in data else None

    raw_walls = data.get("walls")
    if not raw_walls or not isinstance(raw_walls, list):
        raise ConfigError(None, "no walls defined", "add a [[walls]] entry for each wall, in order round the room")
    walls = [_wall(w, i, height) for i, w in enumerate(raw_walls)]
    names = [w.name for w in walls]
    for w in walls:
        if names.count(w.name) > 1:
            raise ConfigError(w.where, f"more than one wall is called {w.name!r}", "give each wall its own name")
    for w in walls:
        last = w.index == len(walls) - 1
        if last and not closed:
            if w.corner is not None and w.corner.type != "open":
                raise ConfigError(f"{w.where}.corner", "the last wall of an open room has no next wall",
                                  "remove its corner, or set closed = true if it meets the first wall")
        elif w.corner is None:
            nxt = walls[0] if last else walls[w.index + 1]
            raise ConfigError(w.where, f"no corner given between {w.name!r} and {nxt.name!r}",
                              'add corner = { type = "inside", through = "this" } (type: inside, outside or '
                              'open; through: this or next, the wall whose layers run to the corner line)')
    for w in walls:
        if w.corner is None:
            w.corner = Corner()
    priorities = [w.tiles.priority for w in walls if w.tiles.priority is not None]
    for w in walls:
        if w.tiles.priority is not None and priorities.count(w.tiles.priority) > 1:
            raise ConfigError(f"{w.where}.tiles.priority", f"priority {w.tiles.priority} is used more than once",
                              "give each wall a different priority: 1 is the most important")
    return Room(height, closed, walls, sheets, tiles, source)


def _sheets(t):
    s = SheetSettings(
        size=t.pair("size", (1200, 800), positive=True),
        thickness=t.number("thickness", positive=True),
        kerf=t.number("kerf", 3, minimum=0),
        joint_gap=t.number("joint_gap", 3, minimum=0),
        bottom_gap=t.number("bottom_gap", 2, minimum=0),
        top_gap=t.number("top_gap", 0, minimum=0),
        min_piece=t.number("min_piece", 100, minimum=0),
        noggin_joints=t.string("noggin_joints", "prefer", ("prefer", "require", "ignore")),
        noggin_tolerance=t.number("noggin_tolerance", 10, minimum=0),
    )
    return s


def _tiles(t):
    size = t.pair("size", positive=True)
    grout = t.number("grout", positive=True)
    options = sorted(set(t.numbers("grout_options", [], positive=True)) | {grout})
    min_cut = t.number("min_cut", 50, minimum=0)
    s = TileSettings(
        size=size,
        thickness=t.number("thickness", positive=True),
        grout=grout,
        grout_options=options,
        kerf=t.number("kerf", 2, minimum=0),
        pattern=t.string("pattern", "grid", ("grid", "brick")),
        offset=t.number("offset", 0.5),
        min_cut=min_cut,
        min_mitre=t.number("min_mitre", min_cut, minimum=0),
        rotate=t.boolean("rotate", False),
        bottom_gap=t.number("bottom_gap", 0, minimum=0),
        top_gap=t.number("top_gap", 0, minimum=0),
        outside_corners=t.string("outside_corners", "mitre", ("mitre", "overlap", "trim")),
        start=t.string("start", None),
        start_align=t.string("start_align", "either", ("tile", "joint", "either")),
        rows=t.raw("rows", ["floor"]),
        spare=t.number("spare", 10, minimum=0),
    )
    if not 0 < s.offset < 1:
        raise ConfigError(t.at("offset"), f"must be between 0 and 1 (a fraction of the tile width), not {s.offset:g}",
                          "use 0.5 for half-bond or 0.333 for third-bond")
    if not isinstance(s.rows, list) or not all(isinstance(r, str) for r in s.rows) or not s.rows:
        raise ConfigError(t.at("rows"), "must be a list of row goals, e.g. [\"South.window.sill\", \"floor\"]")
    for m in ("min_cut", "min_mitre"):
        if getattr(s, m) >= min(size):
            raise ConfigError(t.at(m), f"{getattr(s, m):g} mm is not smaller than the tile",
                              f"use less than {min(size):g}")
    return s


def _wall(data, i, height):
    where = f"walls[{i}]"
    t = _Table(data, where, WALL)
    name = t.string("name", f"Wall {i + 1}")
    where = f"walls.{name}"
    t.where = where
    if "." in name:
        raise ConfigError(where, f"wall names cannot contain '.' ({name!r})", "rename the wall")
    length = t.number("length", None, positive=True)
    measured = t.number("measured_length", None, positive=True)
    if length is None and measured is None:
        raise ConfigError(where, "the wall has no length",
                          "add length = ... (bare framing, corner to corner) and/or measured_length = ... "
                          "(boarded face, corner to corner, before tiling)")
    studs = t.numbers("studs", [])
    if studs:
        if length is None:
            raise ConfigError(t.at("studs"), "stud positions need the framing length",
                              "add length = ... (bare framing, corner to corner)")
        if any(b <= a for a, b in zip(studs, studs[1:])) or studs[0] <= 0 or studs[-1] >= length:
            raise ConfigError(t.at("studs"), "studs must be increasing positions inside the wall, measured from "
                                             "the wall start (the end studs are implied)",
                              f"list each stud centre's distance from the start corner, all between 0 and "
                              f"{length:g}, e.g. [600, 1200, 1800]")
    noggins = t.raw("noggins", None)
    bays = len(studs) + 1
    if noggins is None:
        noggins = [[] for _ in range(bays)]
    elif (not isinstance(noggins, list) or len(noggins) != bays
          or not all(isinstance(b, list) for b in noggins)):
        raise ConfigError(t.at("noggins"), f"must be a list of {bays} lists, one per stud bay",
                          "give each bay (gap between neighbouring studs) a list of noggin centre heights "
                          "from the floor, using [] for a bay without noggins")
    else:
        for b, bay in enumerate(noggins):
            for n in bay:
                if isinstance(n, bool) or not isinstance(n, (int, float)) or not 0 < n < height:
                    raise ConfigError(f"{t.at('noggins')}[{b}]", f"noggin height {n!r} is not inside the wall",
                                      f"use heights between 0 and {height:g}")
        noggins = [[float(n) for n in bay] for bay in noggins]
    corner = None
    if "corner" in data:
        c = _Table(data["corner"], t.at("corner"), ("type", "through", "tiles"))
        ctype = c.string("type", choices=("inside", "outside", "open"))
        through = c.string("through", None, ("this", "next"))
        if ctype != "open" and through is None:
            raise ConfigError(c.where, "an inside or outside corner needs to know which wall runs through",
                              'add through = "this" or "next": the wall whose sheets and tiles run to the corner '
                              'line (the other wall butts against it)')
        corner = Corner(ctype, through, c.string("tiles", "continue", ("continue", "fresh")))
    tiles = WallTiles()
    if "tiles" in data:
        wt = _Table(data["tiles"], t.at("tiles"), ("priority", "centre_on"))
        p = wt.raw("priority", None)
        if p is not None and (isinstance(p, bool) or not isinstance(p, int) or p < 1):
            raise ConfigError(wt.at("priority"), f"must be a whole number from 1 up, not {p!r}",
                              "1 is the most important wall after the start feature")
        c = wt.raw("centre_on", None)
        if c is not None and (isinstance(c, bool) or not isinstance(c, (str, int, float))):
            raise ConfigError(wt.at("centre_on"), "must be a stay-out area's name or an x position")
        tiles = WallTiles(p, float(c) if isinstance(c, (int, float)) else c)
    measured_from = t.string("measured_from", "framing", ("framing", "boarded"))
    stay_out = []
    raw = t.raw("stay_out", [])
    if not isinstance(raw, list):
        raise ConfigError(t.at("stay_out"), "must be a list of areas, e.g. [{ x = [..], y = [..] }]")
    for k, a in enumerate(raw):
        stay_out.append(_opening(a, f"{t.at('stay_out')}[{k}]", height))
    names = [o.name for o in stay_out if o.name]
    for o in stay_out:
        if o.name and names.count(o.name) > 1:
            raise ConfigError(o.where, f"more than one stay-out area on this wall is called {o.name!r}")
    return Wall(name, i, length, measured, measured_from, studs, noggins, corner, tiles, stay_out, where)


def _opening(data, where, height):
    t = _Table(data, where, ("name", "x", "y", "only", "reveal"))
    name = t.string("name", None)
    if name and "." in name:
        raise ConfigError(t.at("name"), f"names cannot contain '.' ({name!r})")
    x = t.pair("x", increasing=True)
    y = t.pair("y", increasing=True)
    if y[0] < 0 or y[1] > height + EPS:
        raise ConfigError(t.at("y"), f"must be between the floor (0) and the ceiling ({height:g})")
    reveal, given = None, "reveal" in data
    if given:
        r = data["reveal"]
        if r == "none":
            reveal = None
        else:
            rt = _Table(r, t.at("reveal"), ("depth",))
            reveal = rt.number("depth", positive=True)
    return Opening(name, x, y, t.string("only", None, ("sheets", "tiles")), reveal, given, where)
